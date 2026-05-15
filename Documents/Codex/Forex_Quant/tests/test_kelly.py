from __future__ import annotations

from systems.risk.kelly import kelly_full_fraction, kelly_quarter_fraction, prop_capped_risk_fraction


def test_q3_m04_example_fractions():
    full = kelly_full_fraction(win_rate=0.65, payoff_ratio=3.0)
    assert abs(full - 0.533333333) < 1e-6
    q = kelly_quarter_fraction(win_rate=0.65, payoff_ratio=3.0)
    assert abs(q - full / 4.0) < 1e-9
    capped = prop_capped_risk_fraction(win_rate=0.65, payoff_ratio=3.0, max_risk_fraction=0.02)
    assert capped == 0.02
