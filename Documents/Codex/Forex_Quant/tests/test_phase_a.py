"""Phase A — regime primitives and session classification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.config_manager import ConfigManager
from core.time_utils import classify_session
from systems.regime.service import _ema, _kaufman_er, _wilder_adx, detect_regime_for_rows

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_a1_wilder_adx_uptrend() -> None:
    rows = [
        {"high": 1.0 + i * 0.001, "low": 0.999 + i * 0.001, "close": 1.0 + i * 0.001, "open": 1.0 + i * 0.001}
        for i in range(50)
    ]
    adx = _wilder_adx(rows)
    assert adx > 22, f"ADX on trend should be >22, got {adx:.1f}"


def test_a2_kaufman_er_linear_trend() -> None:
    closes = [1.0 + i * 0.0005 for i in range(50)]
    er = _kaufman_er(closes, 30)
    assert er > 0.80, f"ER on linear trend should be >0.80, got {er:.3f}"


def test_a3_ema_responds_to_late_jump() -> None:
    values = [1.0] * 20 + [2.0]
    ema = _ema(values, 14)
    assert ema > 1.0, f"EMA should respond to jump at bar 20, got {ema}"


def test_a4_q2_reachable_synthetic() -> None:
    """Trend + elevated vol (via high ATR%) qualifies as Q2 even if vol percentile is modest."""
    base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows: list[dict] = []
    price = 1.0
    for i in range(200):
        h, l, c = price + 0.0002, price - 0.0002, price
        rows.append(
            {
                "time": base + timedelta(minutes=15 * i),
                "open": price,
                "high": h,
                "low": l,
                "close": c,
                "spread": 1.0,
                "tick_volume": 100,
            }
        )
        price += 0.00001
    for i in range(200, 400):
        step = 0.0012
        o = price
        price += step
        rng = 0.01
        h, l = price + rng * 0.3, price - rng * 0.2
        rows.append(
            {
                "time": base + timedelta(minutes=15 * i),
                "open": o,
                "high": h,
                "low": l,
                "close": price,
                "spread": 1.0,
                "tick_volume": 5000,
            }
        )
    regime = detect_regime_for_rows(rows, "EURUSD", "M15")
    assert regime.base_regime == "Q2", f"Expected Q2 base, got {regime.regime_id}"


def test_a5_ny_open_session_1230_utc() -> None:
    cfg = ConfigManager(PROJECT_ROOT).load_yaml("config/sessions.yaml")
    r = classify_session("2026-05-15 12:30:00", cfg)
    assert r["modifier"] == "M04", f"12:30 UTC should be M04 (NY_Open), got {r['modifier']!r}"
    assert r["kill_zone_active"] is True


def test_a5_sessions_cover_full_utc_day() -> None:
    """Every minute in a UTC day maps to a defined session (no Unclassified gaps)."""
    cfg = ConfigManager(PROJECT_ROOT).load_yaml("config/sessions.yaml")
    base = datetime(2026, 6, 10, tzinfo=timezone.utc)
    for minute in range(0, 24 * 60, 1):
        dt = base + timedelta(minutes=minute)
        r = classify_session(dt, cfg)
        assert r.get("session") != "Unclassified", f"Gap at {dt.isoformat()}: {r}"
