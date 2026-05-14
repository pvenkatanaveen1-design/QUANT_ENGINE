from __future__ import annotations

from core.models.risk import PresentRiskSnapshot, RiskApproval


def check_costs(snapshot: PresentRiskSnapshot, max_allowed_spread_percentile: float = 80) -> RiskApproval:
    if snapshot.spread_percentile > max_allowed_spread_percentile:
        return RiskApproval(
            approved=False,
            action="rejected",
            reasons=[f"Spread percentile {snapshot.spread_percentile:.1f} exceeds limit {max_allowed_spread_percentile:.1f}."],
        )
    return RiskApproval(approved=True, action="costs_ok", reasons=["Spread is within configured limits."])

