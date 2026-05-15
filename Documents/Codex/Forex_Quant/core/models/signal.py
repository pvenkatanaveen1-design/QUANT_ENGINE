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
    signal_fn: str = ""
    win_rate_low: float = 0.0
    win_rate_high: float = 0.0
    rrr: float = 0.0
    ev: float = 0.0
    evidence: str = ""
    size_override: float | None = None
    notes: str = ""


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

