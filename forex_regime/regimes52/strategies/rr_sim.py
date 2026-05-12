from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RRResult:
    trades: int
    win_ge_1r: int
    win_ge_2r: int
    win_ge_3r: int
    win_ge_4r: int

    @property
    def rate_1r(self) -> float:
        return self.win_ge_1r / self.trades if self.trades else 0.0

    @property
    def rate_2r(self) -> float:
        return self.win_ge_2r / self.trades if self.trades else 0.0

    @property
    def rate_3r(self) -> float:
        return self.win_ge_3r / self.trades if self.trades else 0.0

    @property
    def rate_4r(self) -> float:
        return self.win_ge_4r / self.trades if self.trades else 0.0


def max_r_before_stop(
    high: np.ndarray,
    low: np.ndarray,
    entry_i: int,
    direction: int,
    entry_price: float,
    r_dist: float,
    max_bars: int,
) -> int:
    """
    Track running max favorable excursion in integer R (1..4) while stop not hit.
    Long: SL = entry - r_dist; k*R target = entry + k*r_dist.
    """
    if r_dist <= 0 or entry_i + max_bars >= len(high):
        return 0
    sl = entry_price - r_dist if direction == 1 else entry_price + r_dist
    max_r = 0
    for k in range(1, max_bars + 1):
        i = entry_i + k
        hi = float(high[i])
        lo = float(low[i])
        if direction == 1:
            if lo <= sl:
                break
            for R in (1, 2, 3, 4):
                if hi >= entry_price + R * r_dist:
                    max_r = max(max_r, R)
        else:
            if hi >= sl:
                break
            for R in (1, 2, 3, 4):
                if lo <= entry_price - R * r_dist:
                    max_r = max(max_r, R)
    return max_r


def score_strategy_trades(
    df: pd.DataFrame,
    *,
    entry_mask: pd.Series,
    directions: pd.Series,
    atr_sl_mult: float = 1.5,
    max_bars: int = 40,
    atr_col: str = "_sig_atr",
) -> RRResult:
    """
    entry_mask: bool Series aligned to df
    directions: +1 / -1 int Series (only rows where entry_mask True are used)
    """
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    atr = df[atr_col].to_numpy(dtype=float)
    idxs = np.flatnonzero(entry_mask.to_numpy() & np.isfinite(atr) & (atr > 0))
    if len(idxs) == 0:
        return RRResult(0, 0, 0, 0, 0)
    w1 = w2 = w3 = w4 = 0
    n = 0
    d = directions.reindex(df.index).fillna(0).to_numpy(dtype=int)
    for ei in idxs:
        if ei + max_bars >= len(c):
            continue
        dire = int(d[ei])
        if dire == 0:
            continue
        entry_price = float(c[ei])
        r_dist = float(atr[ei]) * float(atr_sl_mult)
        mr = max_r_before_stop(h, l, ei, dire, entry_price, r_dist, max_bars)
        n += 1
        if mr >= 1:
            w1 += 1
        if mr >= 2:
            w2 += 1
        if mr >= 3:
            w3 += 1
        if mr >= 4:
            w4 += 1
    return RRResult(trades=n, win_ge_1r=w1, win_ge_2r=w2, win_ge_3r=w3, win_ge_4r=w4)
