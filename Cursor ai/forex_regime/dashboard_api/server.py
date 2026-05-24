#!/usr/bin/env python3
"""
MT5-backed JSON API for dashboard-lite (stdlib only — no Flask).

  cd forex_regime
  python dashboard_api/server.py

  GET http://127.0.0.1:8766/api/snapshot?symbol=EURUSD&tf_minutes=60&bars=12000&regime_id=7

CORS: * — safe for local dev only.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
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


def main() -> int:
    host = "127.0.0.1"
    port = 8766
    print(f"Regime MT5 API  http://{host}:{port}/api/snapshot  (MT5 must be running)")
    HTTPServer((host, port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
