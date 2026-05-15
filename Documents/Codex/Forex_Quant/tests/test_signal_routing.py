from __future__ import annotations

from core.models.regime import RegimeFeatureSet, RegimeResult, RegimeReason
from systems.strategy.signal_library_section5 import run_section5_signal
from systems.strategy.signal_routing import position_size_multiplier_for_regime, signal_code_for_regime


def test_signal_routing_q1_m09_sweep_reclaim():
    assert signal_code_for_regime("Q1_M09") == "S05_sweep_reclaim"


def test_signal_routing_q1_m03_carry_drift():
    assert signal_code_for_regime("Q1_M03") == "S07_carry_drift"


def test_signal_routing_q4_always_no_trade():
    assert signal_code_for_regime("Q4_M05") == "S08_no_trade"


def test_size_multiplier_q2_base():
    assert position_size_multiplier_for_regime("Q2_M01") == 0.5


def test_size_override_q2_m08():
    assert position_size_multiplier_for_regime("Q2_M08") == 0.35


def test_size_override_q1_m07_zero():
    assert position_size_multiplier_for_regime("Q1_M07") == 0.0


def test_section5_q4_returns_no_trade():
    regime = RegimeResult(
        base_regime="Q4",
        modifier="M01",
        regime_id="Q4_M01",
        confidence=0.5,
        tradable=False,
        risk_posture="block_new_orders",
        reasons=[RegimeReason("q4", "test")],
        features=RegimeFeatureSet(adx=20),
    )
    rows = [{"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0} for _ in range(60)]
    r = run_section5_signal(rows, regime)
    assert r.direction == "NONE"
    assert r.strategy_id == "S08_no_trade"

