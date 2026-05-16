from __future__ import annotations

import pytest

from core.models.signal import StrategyCandidate
from systems.strategy_router.service import StrategyRegistryError, get_candidates_for_regime, load_registry, validate_registry


def test_total_entries_and_regime_slots():
    registry = load_registry()
    assert len(registry) == 208
    assert sum(1 for item in registry if item.research_active) == 208
    assert all(item.logic_status == "template_executable" for item in registry)
    assert all(item.enabled for item in registry)
    assert not any(item.live_allowed for item in registry)
    q1_m01, reasons = get_candidates_for_regime("Q1_M01", mode="research")
    assert len(q1_m01) == 4
    assert q1_m01[0].slot == "primary"
    assert "Research mode" in reasons[0]


def test_live_mode_blocks_not_tested_entries():
    candidates, reasons = get_candidates_for_regime("Q1_M01", mode="live")
    assert candidates == []
    assert "no live-approved" in reasons[0]


def test_paper_mode_still_requires_paper_approved_status():
    """enabled=true alone does not promote strategies to paper routing."""
    candidates, reasons = get_candidates_for_regime("Q1_M01", mode="paper")
    assert candidates == []
    assert "paper-approved" in reasons[0].lower()
    candidates, reasons = get_candidates_for_regime("Q9_M99", mode="research")
    assert candidates == []
    assert "No strategy registry entries" in reasons[0]


def test_duplicate_id_fails_validation():
    candidate = StrategyCandidate(id="DUP", name="x", regime_id="Q1_M01", slot="primary", family="general")
    with pytest.raises(StrategyRegistryError):
        validate_registry([candidate] * 208)
