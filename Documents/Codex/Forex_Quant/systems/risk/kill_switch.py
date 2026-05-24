from __future__ import annotations

from core.models.risk import PresentRiskSnapshot, RiskApproval


def check_kill_switch(snapshot: PresentRiskSnapshot) -> RiskApproval:
    reasons: list[str] = []
    if snapshot.manual_kill_switch:
        reasons.append("Manual kill switch is active.")
    if snapshot.data_quality_status == "critical":
        reasons.append("Data quality is critical.")
    if snapshot.spread_percentile >= 95:
        reasons.append("Spread percentile is at kill-switch level.")
    if reasons:
        return RiskApproval(approved=False, action="blocked", reasons=reasons)
    return RiskApproval(approved=True, action="kill_switch_clear", reasons=["Kill switch is clear."])

