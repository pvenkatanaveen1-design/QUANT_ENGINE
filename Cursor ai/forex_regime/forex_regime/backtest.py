from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from forex_regime.config import BacktestParams, RegimeParams
from forex_regime.regime import add_regime_columns
from forex_regime.strategy import positions_from_regime


@dataclass(frozen=True)
class BacktestResult:
    total_return: float
    sharpe_approx: float
    max_drawdown: float
    n_bars: int
    trades: int


def run_backtest_on_ohlc(
    df: pd.DataFrame,
    *,
    regime_params: RegimeParams,
    backtest_params: BacktestParams,
    point_size: float,
    sharpe_bars_per_year: float | None = None,
) -> tuple[pd.DataFrame, BacktestResult]:
    """
    Simple close-to-close PnL in price units, with spread cost in *points*.

    point_size: MT5 symbol point (e.g. 0.0001 for 5-digit FX).
    """
    if df.empty:
        raise ValueError("Empty OHLC DataFrame")

    d = add_regime_columns(df, regime_params).dropna().copy()
    d["position"] = positions_from_regime(d, backtest_params)
    d["ret"] = d["close"].pct_change().fillna(0.0)
    d["strategy_ret"] = d["position"].shift(1).fillna(0.0) * d["ret"]

    # Spread cost when position changes (assumes crossing spread on trade)
    spread_price = float(backtest_params.spread_points) * float(point_size)
    pos_prev = d["position"].shift(1).fillna(0.0)
    turnover = (d["position"] - pos_prev).abs()
    # Pay half-spread per unit change in exposure (conservative proxy)
    d["cost"] = turnover * spread_price / d["close"].replace(0.0, np.nan)
    d["net_ret"] = d["strategy_ret"] - d["cost"]

    equity = (1.0 + d["net_ret"]).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)

    r = d["net_ret"]
    ann = sharpe_bars_per_year if sharpe_bars_per_year is not None else 252.0 * 24.0
    if r.std() > 0:
        sharpe_approx = float(r.mean() / r.std() * np.sqrt(ann))
    else:
        sharpe_approx = 0.0

    peak = equity.cummax()
    dd = (equity / peak) - 1.0
    max_drawdown = float(dd.min())

    trades = int((d["position"].diff().fillna(0.0) != 0.0).sum())

    meta = BacktestResult(
        total_return=total_return,
        sharpe_approx=sharpe_approx,
        max_drawdown=max_drawdown,
        n_bars=len(d),
        trades=trades,
    )
    return d, meta
