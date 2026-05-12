"""Pre-trade risk checks and rough lot sizing (FX / metals heuristic)."""

from __future__ import annotations

from typing import Any


def calculate_lot(
    equity: float,
    sl_pips: float,
    *,
    risk_pct: float = 0.005,
    pip_value: float = 10.0,
) -> float:
    """
    Lots ≈ (equity * risk_pct) / (sl_pips * pip_value_per_lot).
    pip_value default 10.0 matches many 1.0 pip/lot USD quotes on 0.01 lot FX;
    override per symbol when wiring execution.
    """
    try:
        eq = float(equity)
        sl = float(sl_pips)
        rv = float(risk_pct)
    except (TypeError, ValueError):
        return 0.0
    if eq <= 0 or sl <= 0 or rv <= 0:
        return 0.0
    denom = sl * float(pip_value)
    if denom <= 0:
        return 0.0
    lot = (eq * rv) / denom
    return float(max(0.01, min(1.0, round(lot, 2))))


def check_all(
    signal: dict[str, Any] | None,
    *,
    account_equity: float,
    daily_dd_pct: float,
    spread: float | None,
    session: str,
    news_blackout: bool,
    trades_today: int,
    kill_switch_active: bool,
    prop_daily_limit: float = 0.04,
) -> dict[str, Any]:
    """
    Aggregate gate. ``signal`` is a plain dict (from Signal asdict) or None.
    """
    chk: dict[str, bool] = {
        "score": False,
        "spread": False,
        "session": False,
        "news": False,
        "rr": False,
        "daily_dd": False,
        "trade_count": False,
        "kill_switch": False,
        "regime": False,
    }

    try:
        sp_raw = float(spread) if spread is not None else 999.0
    except (TypeError, ValueError):
        sp_raw = 999.0

    sess = (session or "").upper().strip()
    chk["session"] = sess in ("LONDON", "NEW_YORK", "OVERLAP")
    chk["spread"] = sp_raw < 2.0
    chk["news"] = not bool(news_blackout)
    chk["daily_dd"] = float(daily_dd_pct) < float(prop_daily_limit)
    chk["trade_count"] = int(trades_today) < 3
    chk["kill_switch"] = not bool(kill_switch_active)

    if signal is None:
        chk["regime"] = False
        chk["score"] = False
        chk["rr"] = False
        return {
            "approved": False,
            "checks": chk,
            "blocked_reason": "no signal",
            "lot_size": 0.0,
        }

    quad = str(signal.get("regime") or "").upper()
    chk["regime"] = quad != "Q4"
    sc = float(signal.get("score") or 0.0)
    chk["score"] = sc >= 60.0
    rr = float(signal.get("rr_ratio") or 0.0)
    chk["rr"] = rr >= 2.0

    approved = all(chk.values())
    blocked_reason = None if approved else next((f"failed:{k}" for k, v in chk.items() if not v), "failed")

    lot = 0.0
    if approved:
        sl_p = float(signal.get("sl_pips") or 0.0)
        lot = calculate_lot(float(account_equity), sl_pips=sl_p, risk_pct=0.005, pip_value=10.0)

    return {
        "approved": approved,
        "checks": chk,
        "blocked_reason": blocked_reason,
        "lot_size": lot,
    }
