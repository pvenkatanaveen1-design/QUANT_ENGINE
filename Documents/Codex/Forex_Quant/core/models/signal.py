from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StrategyCandidate:
    id: str
    name: str
    regime_id: str
    slot: str
    family: str
    status: str = "not_tested"
    enabled: bool = False
    description: str = ""
    logic_status: str = "name_only"
    live_allowed: bool = False


@dataclass
class Signal:
    strategy_id: str
    symbol: str
    direction: str
    entry: float
    stop: float
    target: float | None
    confidence: float
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalScore:
    signal: Signal
    score: float
    reasons: list[str] = field(default_factory=list)

