from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.models.regime import RegimeResult
from core.models.risk import HistoricalTrustProfile, PresentRiskSnapshot, RiskApproval
from core.models.signal import Signal, StrategyCandidate


@dataclass
class DecisionResult:
    decision_id: str
    symbol: str
    regime_result: RegimeResult
    candidate_strategies: list[StrategyCandidate] = field(default_factory=list)
    selected_signal: Signal | None = None
    historical_trust: HistoricalTrustProfile | None = None
    present_risk: PresentRiskSnapshot | None = None
    risk_approval: RiskApproval | None = None
    final_action: str = "no_trade"
    reasons: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

