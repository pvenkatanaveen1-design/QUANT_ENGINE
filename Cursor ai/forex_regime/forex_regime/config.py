from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegimeParams:
    """Thresholds for labeling each bar (tweak these when testing)."""

    ema_fast: int = 12
    ema_slow: int = 26
    atr_period: int = 14
    # Distance between EMAs vs ATR to call a trend (higher = stricter trend)
    trend_atr_mult: float = 0.35
    # |EMA fast - EMA slow| below this * ATR → RANGE
    range_atr_mult: float = 0.15


@dataclass(frozen=True)
class BacktestParams:
    """Historical fetch + simple strategy toggles."""

    symbol: str = "EURUSD"
    timeframe_minutes: int = 60  # MT5 TIMEFRAME: 1=1m, 60=H1, etc.
    bars: int = 5000
    spread_points: float = 2.0  # charged on entry+exit in points (broker-specific)
    # Strategy: long in TREND_UP, short in TREND_DOWN, flat in RANGE
    allow_short: bool = True
