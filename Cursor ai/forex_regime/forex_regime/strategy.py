from __future__ import annotations

import pandas as pd

from forex_regime.config import BacktestParams
from forex_regime.regime import REGIME_RANGE, REGIME_TREND_DOWN, REGIME_TREND_UP


def positions_from_regime(df: pd.DataFrame, bp: BacktestParams) -> pd.Series:
    """
    Map regime labels to target position: +1 long, -1 short, 0 flat.

    Uses same-bar regime (realistic only for research; live systems usually lag by 1 bar).
    """
    r = df["regime"]
    pos = pd.Series(0.0, index=df.index, dtype=float)
    pos = pos.mask(r == REGIME_TREND_UP, 1.0)
    if bp.allow_short:
        pos = pos.mask(r == REGIME_TREND_DOWN, -1.0)
    pos = pos.mask(r == REGIME_RANGE, 0.0)
    return pos
