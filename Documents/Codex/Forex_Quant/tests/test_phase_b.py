"""Phase B — signal engine + decision wiring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from orchestrator.decision_engine import decide_from_rows
from systems.strategy.signals import compute_signal


def _asian_sweep_fixture() -> list[dict]:
    base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows: list[dict] = []
    for i in range(40):
        rows.append(
            {
                "open": 1.1000,
                "high": 1.1010,
                "low": 1.0930,
                "close": 1.1000,
                "session_label": "Asia",
                "kill_zone_active": False,
                "time": base + timedelta(minutes=15 * i),
                "spread": 1.0,
                "tick_volume": 100,
            }
        )
    rows.append(
        {
            "open": 1.1008,
            "high": 1.1025,
            "low": 1.0998,
            "close": 1.1005,
            "session_label": "London_Open",
            "kill_zone_active": True,
            "time": base + timedelta(minutes=15 * 40),
            "spread": 1.0,
            "tick_volume": 100,
        }
    )
    return rows


def test_b1_asian_sweep_synthetic_q3_m04() -> None:
    rows = _asian_sweep_fixture()
    signal = compute_signal(rows, "Q3_M04")
    assert signal.strategy_id == "S04_asian_sweep"
    assert signal.direction == "SELL"
    assert signal.rr_ratio >= 2.0


def test_b2_no_trade_signal_q4() -> None:
    rows = _asian_sweep_fixture()
    signal_q4 = compute_signal(rows, "Q4_M01")
    assert signal_q4.direction == "NONE"
    assert signal_q4.strategy_id == "S08_no_trade"


def test_b3_decision_engine_metadata_signal_direction() -> None:
    base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows: list[dict] = []
    price = 1.0
    for i in range(120):
        o = price
        price += 0.0003
        rows.append(
            {
                "time": base + timedelta(minutes=15 * i),
                "open": o,
                "high": price + 0.00015,
                "low": o - 0.00005,
                "close": price,
                "spread": 1.0,
                "tick_volume": 100,
            }
        )
    result = decide_from_rows(rows, "EURUSD", "M15", mode="research")
    assert "signal_direction" in result.metadata
