#!/usr/bin/env python3
"""
MT5-backed JSON API for dashboard-lite (stdlib only — no Flask).

  cd forex_regime
  python dashboard_api/server.py

  GET http://127.0.0.1:8766/api/snapshot?symbol=EURUSD&tf_minutes=60&bars=12000&regime_id=7
  GET http://127.0.0.1:8766/api/report/bundle?symbol=EURUSD&tf_minutes=60&bars=12000
  GET http://127.0.0.1:8766/api/report/warm?symbol=EURUSD&tf_minutes=60&bars=8000
  POST http://127.0.0.1:8766/api/report/warm  (JSON — Research panel; stores full payload on session)
  GET http://127.0.0.1:8766/api/report/session/<sid>/pdf/cover
  GET http://127.0.0.1:8766/api/report/session/<sid>/pdf/regime/7
  GET http://127.0.0.1:8766/api/report/session/<sid>/bundle/regime/7
  GET http://127.0.0.1:8766/api/report/session/<sid>/client-request
  GET http://127.0.0.1:8766/api/report/pdf?...  (monolithic; may timeout)

  POST http://127.0.0.1:8766/api/execute  (JSON: symbol, signal, approved_by)

CORS: * — safe for local dev only.
"""

from __future__ import annotations

import functools
import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex_regime.live_detector import detect as live_detect

# MetaTrader5's Python binding is not thread-safe. ThreadingHTTPServer + overlapping
# /api/snapshot polls and /api/report/warm was causing dropped connections ("Failed to fetch").
MT5_CALL_LOCK = threading.RLock()


def _mt5_serialized(fn: object) -> object:
    @functools.wraps(fn)  # type: ignore[misc]
    def wrapped(*a, **kw):  # type: ignore[no-untyped-def]
        with MT5_CALL_LOCK:
            return fn(*a, **kw)

    return wrapped


def _append_execution_journal(row: dict) -> None:
    import csv

    path = ROOT / "reports" / "execution_journal.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    keys = sorted(row.keys())
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        if not exists:
            w.writeheader()
        w.writerow(row)


def _enrich_quant_engine(out: dict, mt5, symbol: str, live: dict) -> None:
    """Phase 2–5: selector, suggested signal, risk gate (mutates out)."""
    from forex_regime.risk.risk_gate import check_all
    from forex_regime.session_util import utc_session_label
    from forex_regime.signals.signal_generator import (
        build_signal_checks,
        generate_signal,
        signal_to_dict,
    )
    from forex_regime.strategy_selector import get_active_strategies, get_strategy_scores

    session = utc_session_label()
    out["session"] = session
    quad = str(live.get("quadrant") or "Q4").upper()
    conf = float(live.get("confidence") or 0.0)
    spr = live.get("spread")

    sig_obj = None
    try:
        if live.get("mt5_connected"):
            sig_obj = generate_signal(live, mt5, symbol)
    except Exception:
        sig_obj = None

    sig_d = signal_to_dict(sig_obj)
    checks = build_signal_checks(sig_obj, live, session)
    out["signal_checks"] = checks
    out["current_signal"] = sig_d

    sig_met = {}
    if sig_obj is not None:
        sig_met[sig_obj.strategy] = True

    try:
        out["strategy_scores"] = get_strategy_scores(quad, conf, spr, session, symbol=symbol)
        out["strategy_selection"] = get_active_strategies(
            quad, conf, spr, session, symbol=symbol, signal_conditions_met=sig_met or None
        )
    except Exception:
        out["strategy_scores"] = []
        out["strategy_selection"] = {
            "trade_allowed": False,
            "reason": "selector error",
            "size_multiplier": 0.0,
            "strategies": [],
        }

    equity = 0.0
    try:
        ai = mt5.account_info()
        if ai is not None:
            equity = float(getattr(ai, "equity", 0) or 0)
    except Exception:
        pass

    risk = check_all(
        sig_d,
        account_equity=equity,
        daily_dd_pct=0.0,
        spread=spr,
        session=session,
        news_blackout=False,
        trades_today=0,
        kill_switch_active=False,
    )
    out["risk_gate"] = risk
    out["lot_size"] = float(risk.get("lot_size") or 0.0)


def _live_fallback_dict() -> dict:
    """Safe live payload if live_detect is unavailable or raises."""
    return {
        "last_price": None,
        "spread": None,
        "adx_14": None,
        "atr_14": None,
        "atr_pct": None,
        "ema50": None,
        "ema200": None,
        "quadrant": None,
        "confidence": None,
        "label": None,
        "direction": None,
        "mt5_connected": False,
        "last_update": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _parse_iso_utc(s: str | None) -> datetime | None:
    if not s:
        return None
    t = str(s).strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(t).astimezone(timezone.utc)
    except ValueError:
        return None


@_mt5_serialized
def run_execute(body: dict) -> tuple[int, dict]:
    """POST /api/execute — re-validate signal, risk, single-position, journal."""
    from forex_regime.execution.order_sender import send_order
    from forex_regime.live_detector import detect as live_detect
    from forex_regime.mt5_setup import initialize_mt5, shutdown_mt5
    from forex_regime.risk.risk_gate import check_all
    from forex_regime.session_util import utc_session_label
    from forex_regime.signals.signal_generator import generate_signal, signal_to_dict

    client = body.get("signal")
    if not isinstance(client, dict):
        return 400, {"success": False, "error": "missing signal object"}

    symbol = str(body.get("symbol") or client.get("symbol") or "EURUSD")
    approved_by = str(body.get("approved_by") or "operator")

    sig_time = _parse_iso_utc(client.get("timestamp"))
    if sig_time is not None:
        age = (datetime.now(timezone.utc) - sig_time).total_seconds()
        if age > 60 or age < -10:
            return 400, {"success": False, "error": "stale_signal", "age_sec": age}

    mt5 = initialize_mt5(ROOT)
    try:
        if not mt5.symbol_select(symbol, True):
            return 502, {"success": False, "error": "symbol_select failed"}
        try:
            live = live_detect(symbol, mt5_module=mt5)
        except Exception:
            live = _live_fallback_dict()

        if not live.get("mt5_connected"):
            return 503, {"success": False, "error": "mt5 not connected"}

        fresh = generate_signal(live, mt5, symbol)
        if fresh is None:
            return 409, {"success": False, "error": "no fresh signal"}

        fd = signal_to_dict(fresh)
        assert fd is not None

        def r2(x) -> float | None:
            try:
                return round(float(x), 2)
            except (TypeError, ValueError):
                return None

        if str(client.get("direction") or "").upper() != str(fd["direction"]).upper():
            return 409, {"success": False, "error": "direction_mismatch"}
        if str(client.get("strategy") or "") != str(fd["strategy"]):
            return 409, {"success": False, "error": "strategy_mismatch"}
        ce = r2(client.get("entry_price"))
        fe = r2(fd["entry_price"])
        if ce is None or fe is None or ce != fe:
            return 409, {"success": False, "error": "entry_mismatch", "client_entry": ce, "fresh_entry": fe}

        session = utc_session_label()
        equity = 0.0
        try:
            ai = mt5.account_info()
            if ai is not None:
                equity = float(getattr(ai, "equity", 0) or 0)
        except Exception:
            pass

        risk = check_all(
            fd,
            account_equity=equity,
            daily_dd_pct=0.0,
            spread=live.get("spread"),
            session=session,
            news_blackout=False,
            trades_today=0,
            kill_switch_active=False,
        )
        if not risk.get("approved"):
            return 403, {"success": False, "error": "risk_blocked", "risk_gate": risk}

        lot = float(risk.get("lot_size") or 0.0)
        if lot <= 0:
            return 403, {"success": False, "error": "zero_lot", "risk_gate": risk}

        pos = mt5.positions_get(symbol=symbol)
        if pos is not None and len(pos) > 0:
            return 409, {"success": False, "error": "position_exists"}

        cmt = f"QE:{approved_by}"[:31]
        exec_res = send_order(mt5, fd, lot, comment=cmt)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _append_execution_journal(
            {
                "ts_utc": now_iso,
                "symbol": symbol,
                "strategy": fd["strategy"],
                "direction": fd["direction"],
                "lot": lot,
                "ticket": exec_res.get("ticket"),
                "success": exec_res.get("success"),
                "retcode": exec_res.get("retcode"),
                "approved_by": approved_by,
                "comment": exec_res.get("comment"),
            }
        )
        return 200, {"success": bool(exec_res.get("success")), "execution": exec_res, "risk_gate": risk}
    finally:
        shutdown_mt5(mt5)


def _json_handler(obj):
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            pass
    if isinstance(obj, dict):
        return {k: _json_handler(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_handler(x) for x in obj]
    return obj


@_mt5_serialized
def build_snapshot(
    *,
    symbol: str,
    tf_minutes: int,
    bars: int,
    regime_id: int | None,
    atr_sl_mult: float,
    max_bars: int,
) -> dict:
    from forex_regime.mt5_setup import initialize_mt5, shutdown_mt5
    from forex_regime.snapshot_core import compute_regime_detail_dict, run_scorecard_with_mt5

    mt5 = initialize_mt5(ROOT)
    try:
        res = run_scorecard_with_mt5(
            mt5,
            symbol=symbol,
            tf_minutes=tf_minutes,
            bars=bars,
            atr_sl_mult=atr_sl_mult,
            max_bars=max_bars,
        )
        if not res.get("ok"):
            err: dict = {"error": str(res.get("error", "pipeline failed"))}
            if res.get("error_type"):
                err["error_type"] = res["error_type"]
            return err

        df = res["df"]
        tbl = res["tbl"]
        live = res["live"]
        regime_counts = res["regime_counts"]
        n_all = res["n_all"]
        q_bar = res["quadrant_bars"]

        out: dict = {
            "meta": res["meta"],
            "regime_counts": regime_counts,
            "quadrant_bars": q_bar,
            "total_bars": n_all,
        }
        out.update(live)
        _enrich_quant_engine(out, mt5, symbol, live)

        if regime_id is None:
            return out

        rid = int(regime_id)
        out["regime_detail"] = compute_regime_detail_dict(
            df=df, tbl=tbl, regime_id=rid, n_all=n_all, regime_counts=regime_counts
        )
        return out
    finally:
        shutdown_mt5(mt5)


@_mt5_serialized
def build_full_pdf_bytes(
    *,
    symbol: str,
    tf_minutes: int,
    bars: int,
    atr_sl_mult: float,
    max_bars: int,
) -> tuple[bytes | None, str | None]:
    """Returns (pdf_bytes, error_message)."""
    import os
    import tempfile

    import matplotlib

    matplotlib.use("Agg")
    from forex_regime.mt5_setup import initialize_mt5, shutdown_mt5
    from forex_regime.regimes52.reporting.regime_pdf import write_institutional_regime52_pdf
    from forex_regime.snapshot_core import run_scorecard_with_mt5

    mt5 = initialize_mt5(ROOT)
    try:
        res = run_scorecard_with_mt5(
            mt5,
            symbol=symbol,
            tf_minutes=tf_minutes,
            bars=bars,
            atr_sl_mult=atr_sl_mult,
            max_bars=max_bars,
        )
        if not res.get("ok"):
            return None, str(res.get("error", "pipeline failed"))

        live = res["live"]
        gen = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        spr = live.get("spread")
        spread_s = str(spr) if spr is not None else None

        fd, tmp_path = tempfile.mkstemp(suffix=".pdf", prefix="regime52_")
        os.close(fd)
        out_path = Path(tmp_path)
        try:
            write_institutional_regime52_pdf(
                out_path,
                df=res["df"],
                scorecard=res["tbl"],
                symbol=symbol,
                tf_minutes=tf_minutes,
                live_quadrant=str(live.get("quadrant") or "") or None,
                live_label=str(live.get("label") or "") or None,
                spread=spread_s,
                generated_iso=gen,
                max_months_chart=48,
            )
            data = out_path.read_bytes()
            return data, None
        finally:
            try:
                out_path.unlink()
            except OSError:
                pass
    finally:
        shutdown_mt5(mt5)


@_mt5_serialized
def build_report_bundle_json(
    *,
    symbol: str,
    tf_minutes: int,
    bars: int,
    atr_sl_mult: float,
    max_bars: int,
) -> tuple[dict | None, str | None]:
    """Returns (bundle_dict, error_message)."""
    from forex_regime.mt5_setup import initialize_mt5, shutdown_mt5
    from forex_regime.snapshot_core import build_full_report_bundle, run_scorecard_with_mt5

    mt5 = initialize_mt5(ROOT)
    try:
        res = run_scorecard_with_mt5(
            mt5,
            symbol=symbol,
            tf_minutes=tf_minutes,
            bars=bars,
            atr_sl_mult=atr_sl_mult,
            max_bars=max_bars,
        )
        if not res.get("ok"):
            return None, str(res.get("error", "pipeline failed"))
        live = res["live"]
        gen = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        base = build_full_report_bundle(
            df=res["df"],
            tbl=res["tbl"],
            live=live,
            meta=res["meta"],
            regime_counts=res["regime_counts"],
            quadrant_bars=res["quadrant_bars"],
            n_all=res["n_all"],
            generated_note=gen,
        )
        out_enrich: dict = {"meta": base["meta"], "total_bars": base["total_bars"]}
        out_enrich.update(live)
        _enrich_quant_engine(out_enrich, mt5, symbol, live)
        base["selector_summary"] = {
            "strategy_selection": out_enrich.get("strategy_selection"),
            "session": out_enrich.get("session"),
        }
        return base, None
    finally:
        shutdown_mt5(mt5)


REPORT_SESSION_LOCK = threading.RLock()
REPORT_SESSIONS: dict[str, dict] = {}
REPORT_SESSION_TTL = 3600.0
REPORT_SESSION_MAX = 12


def _report_sessions_prune() -> None:
    now = time.time()
    with REPORT_SESSION_LOCK:
        dead = [k for k, v in REPORT_SESSIONS.items() if now > float(v["expires_at"])]
        for k in dead:
            del REPORT_SESSIONS[k]
        if len(REPORT_SESSIONS) <= REPORT_SESSION_MAX:
            return
        sorted_keys = sorted(REPORT_SESSIONS.keys(), key=lambda k: REPORT_SESSIONS[k]["created_at"])
        for k in sorted_keys[: max(0, len(REPORT_SESSIONS) - REPORT_SESSION_MAX)]:
            REPORT_SESSIONS.pop(k, None)


@_mt5_serialized
def report_warm_and_store(
    *,
    client_request: dict | None = None,
    **rq: str | int | float,
) -> tuple[dict | None, str | None]:
    """One MT5 pull + scorecard; store df/tbl for chunked PDF/JSON (no matplotlib yet)."""
    from forex_regime.mt5_setup import initialize_mt5, shutdown_mt5
    from forex_regime.snapshot_core import run_scorecard_with_mt5

    sys.stderr.write(
        "[report/warm] start symbol=%s tf=%s bars=%s\n"
        % (rq.get("symbol"), rq.get("tf_minutes"), rq.get("bars"))
    )
    mt5 = initialize_mt5(ROOT)
    try:
        res = run_scorecard_with_mt5(
            mt5,
            symbol=str(rq["symbol"]),
            tf_minutes=int(rq["tf_minutes"]),
            bars=int(rq["bars"]),
            atr_sl_mult=float(rq["atr_sl_mult"]),
            max_bars=int(rq["max_bars"]),
        )
        if not res.get("ok"):
            return None, str(res.get("error", "pipeline failed"))
        gen = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sid = uuid.uuid4().hex
        with REPORT_SESSION_LOCK:
            _report_sessions_prune()
            REPORT_SESSIONS[sid] = {
                "df": res["df"],
                "tbl": res["tbl"],
                "live": res["live"],
                "meta": res["meta"],
                "regime_counts": res["regime_counts"],
                "quadrant_bars": res["quadrant_bars"],
                "n_all": res["n_all"],
                "generated_iso": gen,
                "created_at": time.time(),
                "expires_at": time.time() + REPORT_SESSION_TTL,
                "client_request": dict(client_request) if isinstance(client_request, dict) else {},
            }
        liv = res["live"]
        sys.stderr.write("[report/warm] ok session_id=%s…\n" % (sid[:16],))
        return {
            "session_id": sid,
            "ttl_seconds": int(REPORT_SESSION_TTL),
            "generated_utc": gen,
            "scorecard_request": {
                "symbol": str(rq["symbol"]),
                "tf_minutes": int(rq["tf_minutes"]),
                "bars": int(rq["bars"]),
                "atr_sl_mult": float(rq["atr_sl_mult"]),
                "max_bars": int(rq["max_bars"]),
            },
            "multi_timeframe_note": (
                "This warm ran one MT5/scorecard pass using only the first entry in client_request.timeframes[]. "
                "Run additional POST /api/report/warm calls (or the dashboard loop) for other TFs."
                if isinstance(client_request, dict)
                and isinstance(client_request.get("timeframes"), list)
                and len(client_request["timeframes"]) > 1
                else None
            ),
            "meta": res["meta"],
            "regime_count": 52,
            "live_context": {
                "quadrant": liv.get("quadrant"),
                "label": liv.get("label"),
                "spread": liv.get("spread"),
                "mt5_connected": liv.get("mt5_connected"),
            },
            "endpoints": {
                "pdf_cover": f"/api/report/session/{sid}/pdf/cover",
                "pdf_regime": f"/api/report/session/{sid}/pdf/regime/{{1..52}}",
                "json_regime": f"/api/report/session/{sid}/bundle/regime/{{1..52}}",
            },
            "format": {
                "warm": "One row per call: (symbol, tf_minutes, bars_requested). Session holds classified df + scorecard for that single timeframe.",
                "json_regime": "regime_detail-compatible dict under key 'regime' (four strategy rows).",
                "multi_timeframe": "Today: N timeframes ⇒ N warm calls (N session_ids). Same regime_ids 1..52 in each.",
            },
        }, None
    finally:
        shutdown_mt5(mt5)


def _report_session_row(sid: str) -> dict | None:
    with REPORT_SESSION_LOCK:
        _report_sessions_prune()
        row = REPORT_SESSIONS.get(sid)
        if row is None or time.time() > float(row["expires_at"]):
            return None
        row["expires_at"] = time.time() + REPORT_SESSION_TTL
        return row


def report_session_pdf_cover(sid: str) -> tuple[bytes | None, str | None]:
    import matplotlib

    matplotlib.use("Agg")
    from forex_regime.regimes52.reporting.regime_pdf import pdf_bytes_cover_and_freq

    row = _report_session_row(sid)
    if row is None:
        return None, "session expired or unknown id"
    live = row["live"]
    spr = live.get("spread")
    try:
        data = pdf_bytes_cover_and_freq(
            df=row["df"],
            scorecard=row["tbl"],
            symbol=str(row["meta"]["symbol"]),
            tf_minutes=int(row["meta"]["tf_minutes"]),
            live_quadrant=str(live.get("quadrant") or "") or None,
            live_label=str(live.get("label") or "") or None,
            spread=str(spr) if spr is not None else None,
            generated_iso=str(row["generated_iso"]),
        )
        return data, None
    except Exception as e:
        import traceback

        traceback.print_exc(file=sys.stderr)
        return None, f"{type(e).__name__}: {e}"


def report_session_pdf_regime(sid: str, regime_id: int) -> tuple[bytes | None, str | None]:
    import matplotlib

    matplotlib.use("Agg")
    from forex_regime.regimes52.reporting.regime_pdf import pdf_bytes_single_regime

    row = _report_session_row(sid)
    if row is None:
        return None, "session expired or unknown id"
    rid = int(regime_id)
    if rid < 1 or rid > 52:
        return None, "regime_id must be 1..52"
    try:
        data = pdf_bytes_single_regime(
            df=row["df"],
            scorecard=row["tbl"],
            regime_id=rid,
            symbol=str(row["meta"]["symbol"]),
            tf_minutes=int(row["meta"]["tf_minutes"]),
            include_classifier_params=(rid == 1),
            max_months_chart=48,
        )
        return data, None
    except Exception as e:
        import traceback

        traceback.print_exc(file=sys.stderr)
        return None, f"{type(e).__name__}: {e}"


def report_session_bundle_regime(sid: str, regime_id: int) -> tuple[dict | None, str | None]:
    from forex_regime.snapshot_core import compute_regime_detail_dict

    row = _report_session_row(sid)
    if row is None:
        return None, "session expired or unknown id"
    rid = int(regime_id)
    if rid < 1 or rid > 52:
        return None, "regime_id must be 1..52"
    try:
        detail = compute_regime_detail_dict(
            df=row["df"],
            tbl=row["tbl"],
            regime_id=rid,
            n_all=int(row["n_all"]),
            regime_counts=row["regime_counts"],
        )
        return {
            "bundle_version": 1,
            "session_id": sid,
            "meta": row["meta"],
            "generated_utc": row["generated_iso"],
            "regime": detail,
        }, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def handle_report_session_request(handler: BaseHTTPRequestHandler, path: str) -> bool:
    parts = [p for p in path.split("/") if p]
    if len(parts) < 6 or parts[0] != "api" or parts[1] != "report" or parts[2] != "session":
        return False
    sid = parts[3]
    try:
        if parts[4] == "client-request" and len(parts) == 5:
            row = _report_session_row(sid)
            if row is None:
                body = json.dumps({"error": "session expired or unknown id"}).encode()
                handler.send_response(404)
                handler.send_header("Content-Type", "application/json")
                handler._cors()
                handler.end_headers()
                handler.wfile.write(body)
                return True
            payload = row.get("client_request") or {}
            body = json.dumps(_json_handler(payload), indent=None).encode()
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler._cors()
            handler.end_headers()
            handler.wfile.write(body)
            return True
        if parts[4] == "pdf" and parts[5] == "cover" and len(parts) == 6:
            pdf_bytes, err = report_session_pdf_cover(sid)
            if err or not pdf_bytes:
                body = json.dumps({"error": err or "empty pdf"}).encode()
                handler.send_response(502)
                handler.send_header("Content-Type", "application/json")
                handler._cors()
                handler.end_headers()
                handler.wfile.write(body)
                return True
            handler.send_response(200)
            handler.send_header("Content-Type", "application/pdf")
            handler.send_header("Content-Length", str(len(pdf_bytes)))
            handler.send_header("Content-Disposition", f'attachment; filename="cover_{sid[:8]}.pdf"')
            handler._cors()
            handler.end_headers()
            handler.wfile.write(pdf_bytes)
            return True
        if parts[4] == "pdf" and parts[5] == "regime" and len(parts) == 7:
            rid = int(parts[6])
            pdf_bytes, err = report_session_pdf_regime(sid, rid)
            if err or not pdf_bytes:
                body = json.dumps({"error": err or "empty pdf"}).encode()
                handler.send_response(502)
                handler.send_header("Content-Type", "application/json")
                handler._cors()
                handler.end_headers()
                handler.wfile.write(body)
                return True
            handler.send_response(200)
            handler.send_header("Content-Type", "application/pdf")
            handler.send_header("Content-Length", str(len(pdf_bytes)))
            handler.send_header("Content-Disposition", f'attachment; filename="R{rid:02d}_{sid[:8]}.pdf"')
            handler._cors()
            handler.end_headers()
            handler.wfile.write(pdf_bytes)
            return True
        if parts[4] == "bundle" and parts[5] == "regime" and len(parts) == 7:
            rid = int(parts[6])
            payload, err = report_session_bundle_regime(sid, rid)
            if err or payload is None:
                body = json.dumps({"error": err or "bundle failed"}).encode()
                handler.send_response(502)
                handler.send_header("Content-Type", "application/json")
                handler._cors()
                handler.end_headers()
                handler.wfile.write(body)
                return True
            body = json.dumps(_json_handler(payload), indent=None).encode()
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler._cors()
            handler.end_headers()
            handler.wfile.write(body)
            return True
    except ValueError:
        handler.send_response(400)
        handler.send_header("Content-Type", "application/json")
        handler._cors()
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": "bad regime id"}).encode())
        return True
    return False


def _warm_body_to_rq(body: object) -> tuple[dict[str, str | int | float], dict[str, Any]]:
    """Split JSON into (scorecard kwargs, full client copy for session storage)."""
    if not isinstance(body, dict):
        raise ValueError("JSON body must be an object")
    symbol = str(body.get("symbol") or "EURUSD")
    tf_minutes = int(body.get("tf_minutes") if body.get("tf_minutes") is not None else 60)
    bars = int(body.get("bars") if body.get("bars") is not None else 12000)
    atr_sl_mult = float(body.get("atr_sl_mult") if body.get("atr_sl_mult") is not None else 1.5)
    max_bars = int(body.get("max_bars") if body.get("max_bars") is not None else 40)
    tfs = body.get("timeframes")
    if isinstance(tfs, list) and len(tfs) > 0 and isinstance(tfs[0], dict):
        z = tfs[0]
        if z.get("tf_minutes") is not None:
            tf_minutes = int(z["tf_minutes"])
        if z.get("bars") is not None:
            bars = int(z["bars"])
    rq: dict[str, str | int | float] = {
        "symbol": symbol,
        "tf_minutes": tf_minutes,
        "bars": bars,
        "atr_sl_mult": atr_sl_mult,
        "max_bars": max_bars,
    }
    return rq, dict(body)


def _parse_report_query(qs: dict[str, list[str]]) -> dict[str, str | int | float]:
    symbol = (qs.get("symbol") or ["EURUSD"])[0]
    tf_minutes = int((qs.get("tf_minutes") or ["60"])[0])
    bars = int((qs.get("bars") or ["12000"])[0])
    atr_sl_mult = float((qs.get("atr_sl_mult") or ["1.5"])[0])
    max_bars_rr = int((qs.get("max_bars") or ["40"])[0])
    return {
        "symbol": symbol,
        "tf_minutes": tf_minutes,
        "bars": bars,
        "atr_sl_mult": atr_sl_mult,
        "max_bars": max_bars_rr,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            body = json.dumps({"ok": True, "service": "regime-dashboard-api"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return

        if handle_report_session_request(self, parsed.path):
            return

        qs = parse_qs(parsed.query)

        if parsed.path == "/api/report/warm":
            rq = _parse_report_query(qs)
            try:
                warm, err = report_warm_and_store(client_request=None, **rq)
            except Exception as e:
                import traceback

                traceback.print_exc(file=sys.stderr)
                warm, err = None, f"{type(e).__name__}: {e}"
            if err or warm is None:
                body = json.dumps({"error": err or "warm failed"}).encode()
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self._cors()
                self.end_headers()
                self.wfile.write(body)
                return
            body = json.dumps(_json_handler(warm), indent=None).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/report/bundle":
            rq = _parse_report_query(qs)
            try:
                bundle, err = build_report_bundle_json(**rq)
            except Exception as e:
                bundle, err = None, f"{type(e).__name__}: {e}"
            if err or bundle is None:
                body = json.dumps({"error": err or "bundle failed"}).encode()
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self._cors()
                self.end_headers()
                self.wfile.write(body)
                return
            body = json.dumps(_json_handler(bundle), indent=None).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/report/pdf":
            rq = _parse_report_query(qs)
            try:
                pdf_bytes, err = build_full_pdf_bytes(**rq)
            except Exception as e:
                import traceback

                traceback.print_exc(file=sys.stderr)
                pdf_bytes, err = None, f"{type(e).__name__}: {e}"
            if err or not pdf_bytes:
                body = json.dumps({"error": err or "empty pdf"}).encode()
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self._cors()
                self.end_headers()
                self.wfile.write(body)
                return
            sym_safe = str(rq["symbol"]).replace("/", "_").replace("\\", "_")
            fname = f"regime52_{sym_safe}_{rq['tf_minutes']}m.pdf"
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(pdf_bytes)))
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self._cors()
            self.end_headers()
            self.wfile.write(pdf_bytes)
            return

        if parsed.path != "/api/snapshot":
            self.send_error(404, "Not Found")
            return

        symbol = (qs.get("symbol") or ["EURUSD"])[0]
        tf_minutes = int((qs.get("tf_minutes") or ["60"])[0])
        bars = int((qs.get("bars") or ["12000"])[0])
        atr_sl_mult = float((qs.get("atr_sl_mult") or ["1.5"])[0])
        max_bars_rr = int((qs.get("max_bars") or ["40"])[0])
        regime_raw = qs.get("regime_id")
        regime_id: int | None = None
        if regime_raw:
            try:
                regime_id = int(regime_raw[0])
            except ValueError:
                regime_id = None

        try:
            data = build_snapshot(
                symbol=symbol,
                tf_minutes=tf_minutes,
                bars=bars,
                regime_id=regime_id,
                atr_sl_mult=atr_sl_mult,
                max_bars=max_bars_rr,
            )
        except Exception as e:
            data = {"error": str(e), "error_type": type(e).__name__}

        body = json.dumps(_json_handler(data), indent=None).encode()
        self.send_response(200 if "error" not in data else 502)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/api/report/warm":
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(max(0, length)) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                body = None
            if not isinstance(body, dict):
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self._cors()
                self.end_headers()
                self.wfile.write(json.dumps({"error": "invalid JSON object"}).encode())
                return
            try:
                rq, client_copy = _warm_body_to_rq(body)
            except (ValueError, TypeError) as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self._cors()
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
                return
            try:
                warm, err = report_warm_and_store(client_request=client_copy, **rq)
            except Exception as e:
                import traceback

                traceback.print_exc(file=sys.stderr)
                warm, err = None, f"{type(e).__name__}: {e}"
            if err or warm is None:
                body_out = json.dumps({"error": err or "warm failed"}).encode()
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self._cors()
                self.end_headers()
                self.wfile.write(body_out)
                return
            body_out = json.dumps(_json_handler(warm), indent=None).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(body_out)
            return

        if parsed.path != "/api/execute":
            self.send_error(404, "Not Found")
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(max(0, length)) if length > 0 else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = {}

        try:
            status, payload = run_execute(body if isinstance(body, dict) else {})
        except Exception as e:
            status = 502
            payload = {"success": False, "error": str(e), "error_type": type(e).__name__}

        out = json.dumps(_json_handler(payload), indent=None).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(out)


def main() -> int:
    host = os.environ.get("FOREX_REGIME_API_BIND", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.environ.get("FOREX_REGIME_API_PORT", "8766"))
    print(
        f"Regime MT5 API  http://{host}:{port}/api/snapshot  "
        f"GET /api/report/warm  POST /api/report/warm  GET /api/report/session/<sid>/pdf/…  "
        f"GET /api/report/pdf  GET /api/report/bundle  POST /api/execute  (MT5 must be running)"
    )
    if host == "0.0.0.0":
        print("  Listening on all interfaces (FOREX_REGIME_API_BIND=0.0.0.0).")
    try:
        from http.server import ThreadingHTTPServer

        srv = ThreadingHTTPServer((host, port), Handler)
    except ImportError:
        srv = HTTPServer((host, port), Handler)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
