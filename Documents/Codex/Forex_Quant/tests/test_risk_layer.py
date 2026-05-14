from __future__ import annotations

from core.models.risk import AccountState, HistoricalTrustProfile, PresentRiskSnapshot
from systems.risk.cost_guard import check_costs
from systems.risk.kill_switch import check_kill_switch
from systems.risk.position_sizer import calculate_position_size
from systems.risk.shield import analyze_signal


def test_cost_guard_blocks_wide_spread():
    approval = check_costs(PresentRiskSnapshot(spread_percentile=90), max_allowed_spread_percentile=80)
    assert not approval.approved


def test_kill_switch_blocks_critical_data_quality():
    approval = check_kill_switch(PresentRiskSnapshot(data_quality_status="critical"))
    assert not approval.approved


def test_position_size_reduces_for_weak_trust():
    result = calculate_position_size(
        AccountState(equity=10000),
        entry_price=1.1000,
        stop_price=1.0990,
        pip_size=0.0001,
        regime_confidence=0.5,
        historical_trust=HistoricalTrustProfile(approved=False),
    )
    assert result.final_risk_percent < 0.25
    assert result.lot_size > 0


def test_shield_approves_only_when_all_checks_pass():
    approval = analyze_signal(
        account=AccountState(equity=10000),
        snapshot=PresentRiskSnapshot(spread_percentile=10, data_quality_status="ok"),
        entry_price=1.1000,
        stop_price=1.0990,
        pip_size=0.0001,
        regime_confidence=0.9,
        historical_trust=HistoricalTrustProfile(strategy_id="x", trades=150, profit_factor=1.3, expectancy_r=0.1, approved=True),
    )
    assert approval.approved
    assert approval.position_size is not None

