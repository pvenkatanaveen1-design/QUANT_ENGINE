#!/usr/bin/env python3
"""
MT5-backed JSON API for dashboard-lite (stdlib only — no Flask).

  cd forex_regime
  python dashboard_api/server.py

  GET http://127.0.0.1:8766/api/snapshot?symbol=EURUSD&tf_minutes=60&bars=12000&regime_id=7

  POST http://127.0.0.1:8766/api/execute  (JSON: symbol, signal, approved_by)

CORS: * — safe for local dev only.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex_regime.live_detector import detect as live_detect


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


def build_snapshot(
    *,
    symbol: str,
    tf_minutes: int,
    bars: int,
    regime_id: int | None,
    atr_sl_mult: float,
    max_bars: int,
) -> dict:
    import numpy as np
    import pandas as pd

    from forex_regime.mt5_setup import (
        copy_rates_batched,
        initialize_mt5,
        rates_to_dataframe,
        shutdown_mt5,
        timeframe_from_minutes,
    )
    from forex_regime.regimes52.analysis.scoring import add_rank_columns
    from forex_regime.regimes52.classify import Regime52Params
    from forex_regime.regimes52.strategies.runner import (
        build_scorecard_table,
        prepare_regime_and_signals,
    )
    from forex_regime.regimes52.taxonomy import REGIME_NAME, quadrant_for_id

    mt5 = initialize_mt5(ROOT)
    try:
        if not mt5.symbol_select(symbol, True):
            return {"error": "symbol_select failed"}
        tf = timeframe_from_minutes(mt5, tf_minutes)
        raw = copy_rates_batched(mt5, symbol, tf, bars)
        df = rates_to_dataframe(raw).sort_values("time").reset_index(drop=True)
        if df.empty:
            return {"error": "no OHLC data from MT5"}
        live = _live_fallback_dict()
        try:
            live = live_detect(symbol, mt5_module=mt5)
        except Exception:
            pass
        p = Regime52Params()
        df = prepare_regime_and_signals(df, p)
        tbl = add_rank_columns(
            build_scorecard_table(df, p=p, atr_sl_mult=atr_sl_mult, max_bars=max_bars)
        )
        freq = df["regime52_id"].value_counts().sort_index()
        regime_counts = {str(int(k)): int(v) for k, v in freq.items()}
        n_all = len(df)

        q_bar: dict[str, int] = {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0}
        for rid, c in freq.items():
            qtag = quadrant_for_id(int(rid))
            if qtag in q_bar:
                q_bar[qtag] += int(c)

        out: dict = {
            "meta": {
                "symbol": symbol,
                "tf_minutes": tf_minutes,
                "bars_requested": bars,
                "bars_loaded": n_all,
                "source": "mt5",
            },
            "regime_counts": regime_counts,
            "quadrant_bars": q_bar,
            "total_bars": n_all,
        }
        out.update(live)
        _enrich_quant_engine(out, mt5, symbol, live)

        if regime_id is None:
            return out

        rid = int(regime_id)
        mask = df["regime52_id"] == rid
        n_reg = int(mask.sum())

        monthly: list[dict] = []
        sub = df.loc[mask, "time"]
        if not sub.empty:
            ts = pd.to_datetime(sub, utc=True)
            if getattr(ts.dt, "tz", None) is not None:
                ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
            mc = ts.dt.to_period("M").value_counts().sort_index()
            monthly = [{"period": str(period), "count": int(cnt)} for period, cnt in mc.items()]

        arr = mask.to_numpy()
        cum = arr.cumsum()
        if len(cum) == 0:
            line_x, line_y = [], []
        else:
            npts = min(120, len(cum))
            idx = np.linspace(0, len(cum) - 1, npts, dtype=int)
            line_x = idx.tolist()
            line_y = [round(float(cum[i]) / float(i + 1) * 100.0, 4) for i in idx]

        q = quadrant_for_id(rid)
        in_quadrant = sum(
            int(regime_counts.get(str(r), 0)) for r in range(1, 53) if quadrant_for_id(r) == q
        )
        same_q_not_reg = max(0, in_quadrant - n_reg)
        other_quadrants = max(0, n_all - in_quadrant)

        sc = tbl[tbl["regime_id"] == rid]
        strategies = []
        for _, row in sc.iterrows():
            strategies.append(
                {
                    "strategy_key": row["strategy_key"],
                    "strategy_title": row["strategy_title"],
                    "signal_kind": row["signal_kind"],
                    "side_rule": int(row["side_rule"]),
                    "trades": int(row["trades"]),
                    "wr_1r": float(row["wr_1r"]),
                    "wr_2r": float(row["wr_2r"]),
                    "wr_3r": float(row["wr_3r"]),
                    "wr_4r": float(row["wr_4r"]),
                    "rank_score": float(row["rank_score"]),
                    "score_wr_blend": float(row["score_wr_blend"]),
                }
            )

        out["regime_detail"] = {
            "regime_id": rid,
            "regime_name": REGIME_NAME.get(rid, ""),
            "quadrant": q,
            "bars_in_regime": n_reg,
            "pct_of_sample": round(100.0 * n_reg / n_all, 4) if n_all else 0.0,
            "pie_three_way": {
                "labels": [
                    "This regime",
                    "Same quadrant (other ids)",
                    "Other quadrants",
                ],
                "values": [n_reg, same_q_not_reg, other_quadrants],
            },
            "monthly": monthly,
            "line_series": {
                "x": line_x,
                "y": line_y,
                "label": "Cumulative % of bars (so far) = this regime",
            },
            "strategies": strategies,
        }
        return out
    finally:
        shutdown_mt5(mt5)


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

        if parsed.path != "/api/snapshot":
            self.send_error(404, "Not Found")
            return

        qs = parse_qs(parsed.query)
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
    host = "127.0.0.1"
    port = 8766
    print(f"Regime MT5 API  http://{host}:{port}/api/snapshot  POST /api/execute  (MT5 must be running)")
    HTTPServer((host, port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
