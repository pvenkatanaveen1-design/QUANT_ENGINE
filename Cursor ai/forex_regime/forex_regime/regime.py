from __future__ import annotations

import numpy as np
import pandas as pd

from forex_regime.config import RegimeParams

REGIME_TREND_UP = "TREND_UP"
REGIME_TREND_DOWN = "TREND_DOWN"
REGIME_RANGE = "RANGE"


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def add_regime_columns(df: pd.DataFrame, p: RegimeParams) -> pd.DataFrame:
    """
    Add columns: ema_fast, ema_slow, atr, ema_spread, regime.

    Expects columns: open, high, low, close, tick_volume (volume optional).
    """
    out = df.copy()
    c = out["close"].astype(float)
    out["ema_fast"] = c.ewm(span=p.ema_fast, adjust=False).mean()
    out["ema_slow"] = c.ewm(span=p.ema_slow, adjust=False).mean()
    out["atr"] = _atr(out["high"].astype(float), out["low"].astype(float), c, p.atr_period)
    out["ema_spread"] = out["ema_fast"] - out["ema_slow"]
    atr = out["atr"].replace(0.0, np.nan)
    spread_n = out["ema_spread"] / atr

    regime = pd.Series(REGIME_RANGE, index=out.index, dtype="object")
    regime = regime.mask(spread_n > p.trend_atr_mult, REGIME_TREND_UP)
    regime = regime.mask(spread_n < -p.trend_atr_mult, REGIME_TREND_DOWN)
    regime = regime.where(spread_n.abs() >= p.range_atr_mult, REGIME_RANGE)

    out["regime"] = regime
    return out
