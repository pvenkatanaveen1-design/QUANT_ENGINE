from __future__ import annotations

from datetime import datetime, timedelta, timezone

from systems.regime.service import detect_regime_for_rows


def _row(time, open_, high, low, close, spread=1.0):
    return {"time": time, "open": open_, "high": high, "low": low, "close": close, "tick_volume": 100, "spread": spread}


def trend_rows(count=90, high_vol=False, start_hour=7):
    base_time = datetime(2026, 1, 1, start_hour, 0, tzinfo=timezone.utc)
    price = 1.1000
    rows = []
    for index in range(count):
        price += 0.0002
        width = 0.0002
        if high_vol:
            width = 0.0007 + (index % 7) * 0.00015
        rows.append(_row(base_time + timedelta(minutes=15 * index), price - 0.00005, price + width, price - width, price, 1.0))
    return rows


def range_rows(count=90, start_hour=0):
    base_time = datetime(2026, 1, 1, start_hour, 0, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        close = 1.1000 + (0.00025 if index % 2 else -0.00025)
        rows.append(_row(base_time + timedelta(minutes=15 * index), 1.1000, close + 0.0002, close - 0.0002, close, 1.0))
    return rows


def test_trend_low_vol_classifies_q1():
    result = detect_regime_for_rows(trend_rows(high_vol=False), symbol="EURUSD", timeframe="M15")
    assert result.base_regime == "Q1"


def test_trend_high_vol_classifies_q2_not_q4_from_extreme_vol_branch():
    """High-vol uptrend must reach Q2 (trend + high vol) before extreme-vol → Q4."""
    result = detect_regime_for_rows(trend_rows(high_vol=True), symbol="EURUSD", timeframe="M15")
    assert result.base_regime == "Q2"


def test_range_classifies_q3():
    result = detect_regime_for_rows(range_rows(), symbol="EURUSD", timeframe="M15")
    assert result.base_regime == "Q3"


def test_extreme_spread_uses_m10():
    rows = trend_rows(high_vol=False)
    rows[-1]["spread"] = 50.0
    result = detect_regime_for_rows(rows, symbol="EURUSD", timeframe="M15")
    assert result.modifier == "M10"


def test_london_open_uses_m04_when_no_stronger_modifier():
    result = detect_regime_for_rows(trend_rows(count=40, high_vol=False, start_hour=22), symbol="EURUSD", timeframe="M15")
    assert result.modifier == "M04"


def test_liquidity_sweep_uses_m09():
    rows = range_rows(start_hour=11)
    last_time = rows[-1]["time"] + timedelta(minutes=15)
    rows.append(_row(last_time, 1.1000, 1.1002, 1.0980, 1.1001, 1.0))
    result = detect_regime_for_rows(rows, symbol="EURUSD", timeframe="M15")
    assert result.modifier == "M09"
