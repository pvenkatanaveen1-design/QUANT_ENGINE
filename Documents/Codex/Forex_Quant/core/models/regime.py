from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RegimeReason:
    code: str
    message: str
    severity: str = "info"


@dataclass
class RegimeFeatureSet:
    atr: float = 0.0
    atr_percent: float = 0.0
    volatility_percentile: float = 0.0
    efficiency_ratio: float = 0.0
    adx: float = 0.0
    #: OLS slope of close over the ER lookback window, divided by ATR (dimensionless trend tilt). Observability only; not used in quadrant routing.
    slope_score: float = 0.0
    spread_percentile: float = 0.0
    jump_z: float = 0.0
    compression_percentile: float = 100.0
    body_ratio: float = 0.0
    upper_wick_ratio: float = 0.0
    lower_wick_ratio: float = 0.0
    session_label: str = "Unclassified"
    sweep_high: bool = False
    sweep_low: bool = False
    data_quality_bad: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RegimeResult:
    base_regime: str
    modifier: str
    regime_id: str
    confidence: float
    tradable: bool
    risk_posture: str
    reasons: list[RegimeReason] = field(default_factory=list)
    features: RegimeFeatureSet = field(default_factory=RegimeFeatureSet)

