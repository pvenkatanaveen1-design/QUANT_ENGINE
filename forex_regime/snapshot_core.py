"""
Shared MT5 → OHLC → regime52 classify → scorecard pipeline.

Used by dashboard_api/server.py and report builders so one implementation
owns the heavy path (single MT5 pull + single classify pass).
"""

from __future__ import annotations

from typing import Any

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from forex_regime.live_detector import detect as live_detect
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


def live_fallback_dict() -> dict:
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


def compute_regime_detail_dict(
    *,
    df: pd.DataFrame,
    tbl: pd.DataFrame,
    regime_id: int,
    n_all: int,
    regime_counts: dict[str, int],
) -> dict:
    """Same shape as dashboard snapshot ``regime_detail`` for one id."""
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
    strategies: list[dict] = []
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

    return {
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


def build_full_report_bundle(
    *,
    df: pd.DataFrame,
    tbl: pd.DataFrame,
    live: dict,
    meta: dict,
    regime_counts: dict[str, int],
    quadrant_bars: dict[str, int],
    n_all: int,
    generated_note: str = "",
) -> dict:
    """Serializable JSON bundle: all 52 regimes with strategy rows."""
    regimes = [compute_regime_detail_dict(df=df, tbl=tbl, regime_id=r, n_all=n_all, regime_counts=regime_counts) for r in range(1, 53)]
    return {
        "bundle_version": 1,
        "generated_utc": generated_note,
        "meta": meta,
        "live_context": {
            k: live.get(k)
            for k in (
                "last_price",
                "spread",
                "adx_14",
                "atr_14",
                "atr_pct",
                "ema50",
                "ema200",
                "quadrant",
                "confidence",
                "label",
                "direction",
                "mt5_connected",
                "last_update",
            )
            if k in live
        },
        "regime_counts": regime_counts,
        "quadrant_bars": quadrant_bars,
        "total_bars": n_all,
        "regimes": regimes,
    }


def run_scorecard_with_mt5(
    mt5: Any,
    *,
    symbol: str,
    tf_minutes: int,
    bars: int,
    atr_sl_mult: float,
    max_bars: int,
) -> dict[str, Any]:
    """
    Assumes ``mt5`` is initialized and caller will shut down.
    Same return shape as ``run_scorecard_pipeline`` success / error.
    """
    try:
        if not mt5.symbol_select(symbol, True):
            return {"ok": False, "error": "symbol_select failed"}
        tf = timeframe_from_minutes(mt5, tf_minutes)
        raw = copy_rates_batched(mt5, symbol, tf, bars)
        df = rates_to_dataframe(raw).sort_values("time").reset_index(drop=True)
        if df.empty:
            return {"ok": False, "error": "no OHLC data from MT5"}
        live = live_fallback_dict()
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

        meta = {
            "symbol": symbol,
            "tf_minutes": tf_minutes,
            "bars_requested": bars,
            "bars_loaded": n_all,
            "source": "mt5",
        }
        return {
            "ok": True,
            "df": df,
            "tbl": tbl,
            "live": live,
            "meta": meta,
            "regime_counts": regime_counts,
            "quadrant_bars": q_bar,
            "n_all": n_all,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "error_type": type(e).__name__}


def run_scorecard_pipeline(
    *,
    project_root: Path,
    symbol: str,
    tf_minutes: int,
    bars: int,
    atr_sl_mult: float,
    max_bars: int,
) -> dict[str, Any]:
    """
    Single MT5 session: fetch bars, classify, scorecard table.

    Returns on success:
        ``{"ok": True, "df", "tbl", "live", "meta", "regime_counts", "quadrant_bars", "n_all"}``

    On failure: ``{"ok": False, "error": str}``
    """
    mt5 = initialize_mt5(project_root)
    try:
        return run_scorecard_with_mt5(
            mt5,
            symbol=symbol,
            tf_minutes=tf_minutes,
            bars=bars,
            atr_sl_mult=atr_sl_mult,
            max_bars=max_bars,
        )
    finally:
        shutdown_mt5(mt5)