from __future__ import annotations

import numpy as np
import pandas as pd

from forex_regime.regimes52.classify import Regime52Params, add_regime52_columns
from forex_regime.regimes52.strategies.registry import all_strategy_specs
from forex_regime.regimes52.strategies.rr_sim import score_strategy_trades
from forex_regime.regimes52.strategies.signals import build_signal_context, strategy_signal
from forex_regime.regimes52.taxonomy import REGIME_NAME, quadrant_for_id


def prepare_regime_and_signals(df: pd.DataFrame, p: Regime52Params | None = None) -> pd.DataFrame:
    """Attach `regime52_*`, signal ATR column for R-multiple sim."""
    if p is None:
        p = Regime52Params()
    out = add_regime52_columns(df, p)
    ctx = build_signal_context(out, p)
    out["_sig_atr"] = ctx.atr
    return out


def regime_bar_counts(df: pd.DataFrame) -> pd.Series:
    """Series index regime_id -> number of bars with that primary regime."""
    return df["regime52_id"].value_counts().sort_index()


def build_scorecard_table(
    df: pd.DataFrame,
    *,
    p: Regime52Params | None = None,
    atr_sl_mult: float = 1.5,
    max_bars: int = 40,
) -> pd.DataFrame:
    """
    For each (regime × strategy blueprint) spec: count trades where regime matches and signal fired,
    then win-rates for max favorable excursion >= 1R..4R before stop (ATR-based stop).
    """
    if "regime52_id" not in df.columns or "_sig_atr" not in df.columns:
        df = prepare_regime_and_signals(df, p)
        ctx = build_signal_context(df, p or Regime52Params())
    else:
        ctx = build_signal_context(df, p or Regime52Params())
    freq = regime_bar_counts(df)
    rows: list[dict] = []
    for spec in all_strategy_specs():
        sig = strategy_signal(ctx, spec.signal_kind, spec.side)
        m = (df["regime52_id"] == spec.regime_id) & (sig != 0)
        rr = score_strategy_trades(
            df,
            entry_mask=m,
            directions=sig.astype(int),
            atr_sl_mult=atr_sl_mult,
            max_bars=max_bars,
            atr_col="_sig_atr",
        )
        rid = spec.regime_id
        rows.append(
            {
                "regime_id": rid,
                "regime_name": REGIME_NAME[rid],
                "quadrant": quadrant_for_id(rid),
                "bars_in_regime": int(freq.get(rid, 0)),
                "strategy_key": spec.key,
                "strategy_title": spec.title,
                "signal_kind": spec.signal_kind,
                "side_rule": spec.side,
                "trades": rr.trades,
                "wr_1r": round(rr.rate_1r, 4),
                "wr_2r": round(rr.rate_2r, 4),
                "wr_3r": round(rr.rate_3r, 4),
                "wr_4r": round(rr.rate_4r, 4),
            }
        )
    return pd.DataFrame(rows)


def attach_strategy_hits_per_bar(df: pd.DataFrame, p: Regime52Params | None = None) -> pd.DataFrame:
    """
    After regime detection, evaluate all 208 strategy blueprints each bar.
    Adds `strategy_keys_fired`: list of `Rxx-Syy` keys where regime matches and signal != 0.
    """
    out = prepare_regime_and_signals(df, p)
    ctx = build_signal_context(out, p or Regime52Params())
    n = len(out)
    hits: list[list[str]] = [[] for _ in range(n)]
    rid_arr = out["regime52_id"].to_numpy()
    for spec in all_strategy_specs():
        sig = strategy_signal(ctx, spec.signal_kind, spec.side)
        sgn = sig.to_numpy()
        m = (rid_arr == spec.regime_id) & (sgn != 0)
        for i in np.flatnonzero(m):
            hits[int(i)].append(spec.key)
    out = out.copy()
    out["strategy_keys_fired"] = hits
    return out
