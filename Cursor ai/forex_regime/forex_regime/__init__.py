"""Forex regime detection and simple MT5-backed backtests."""

from forex_regime.config import BacktestParams, RegimeParams
from forex_regime.regimes52 import (
    REGIME_DOC,
    REGIME_NAME,
    Regime52Params,
    add_regime52_columns,
    quadrant_for_id,
)

__all__ = [
    "RegimeParams",
    "BacktestParams",
    "Regime52Params",
    "add_regime52_columns",
    "REGIME_DOC",
    "REGIME_NAME",
    "quadrant_for_id",
    "__version__",
]

__version__ = "0.1.0"
