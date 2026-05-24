from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.models.regime import RegimeFeatureSet, RegimeReason, RegimeResult


@dataclass(frozen=True)
class RegimeDetectionRequest:
    symbol: str
    timeframe: str
    rows: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class ModifierResult:
    modifier: str
    reason: str
    priority: int


@dataclass(frozen=True)
class SessionLabel:
    name: str
    modifier: str
    notes: str | None = None


@dataclass
class RegimeDetectionResult(RegimeResult):
    history: list[RegimeResult] = field(default_factory=list)


__all__ = [
    "RegimeDetectionRequest",
    "RegimeDetectionResult",
    "RegimeFeatureSet",
    "RegimeReason",
    "RegimeResult",
    "ModifierResult",
    "SessionLabel",
]

