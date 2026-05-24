from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config_manager import ConfigManager
from core.models.risk import AccountState, HistoricalTrustProfile, PresentRiskSnapshot, RiskApproval
from systems.risk.correlation_guard import check_correlation
from systems.risk.cost_guard import check_costs
from systems.risk.funded_rules_engine import check_funded_rules
from systems.risk.kill_switch import check_kill_switch
from systems.risk.position_sizer import calculate_position_size
from systems.strategy.signal_routing import position_size_multiplier_for_regime


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _rules() -> dict[str, Any]:
    return ConfigManager(PROJECT_ROOT).load_yaml("config/risk_rules.yaml")


def analyze_signal(
    account: AccountState,
    snapshot: PresentRiskSnapshot,
    entry_price: float,
    stop_price: float,
    pip_size: float,
    regime_confidence: float,
    historical_trust: HistoricalTrustProfile | None = None,
    regime_id: str | None = None,
    regime_size_multiplier: float | None = None,
) -> RiskApproval:
    rules = _rules()
    checks = [
        check_kill_switch(snapshot),
        check_costs(snapshot, float(rules.get("max_allowed_spread_percentile", 80))),
        check_funded_rules(account, snapshot, rules),
        check_correlation(account, int(rules.get("max_correlated_trades", 2))),
    ]
    failed = [check for check in checks if not check.approved]
    if failed:
        reasons = [reason for check in failed for reason in check.reasons]
        return RiskApproval(approved=False, action="rejected", reasons=reasons)

    rsm = regime_size_multiplier if regime_size_multiplier is not None else None
    if rsm is None and regime_id:
        rsm = position_size_multiplier_for_regime(regime_id)
    if rsm is None:
        rsm = 1.0

    position = calculate_position_size(
        account=account,
        entry_price=entry_price,
        stop_price=stop_price,
        pip_size=pip_size,
        base_risk_percent=float(rules.get("base_risk_per_trade_percent", 0.25)),
        max_risk_percent=float(rules.get("max_risk_per_trade_percent", 0.5)),
        regime_confidence=regime_confidence,
        historical_trust=historical_trust,
        regime_size_multiplier=float(rsm),
    )
    reasons = [reason for check in checks for reason in check.reasons] + position.reasons
    if position.lot_size <= 0:
        return RiskApproval(approved=False, action="rejected", reasons=reasons + ["Position size is zero."], position_size=position)
    return RiskApproval(approved=True, action="approved_paper", reasons=reasons, position_size=position)

