"""Suggested setups from live headline regime (read-only until execution layer)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class Signal:
    symbol: str
    direction: str  # "BUY" | "SELL"
    entry_price: float
    stop_loss: float
    take_profit: float
    sl_pips: float
    tp_pips: float
    rr_ratio: float
    strategy: str
    score: float
    regime: str
    timestamp: str  # ISO UTC
    status: str  # WATCHING | ARMED | NOT_READY


def _pip_size(info: Any) -> float:
    pt = float(getattr(info, "point", 0) or 0)
    if pt <= 0:
        return 1e-5
    d = int(getattr(info, "digits", 0) or 0)
    if d in (3, 5):
        return pt * 10.0
    return pt


def generate_alpha_sweep_signal(mt5_module: Any, symbol: str, live: dict[str, Any]) -> Signal | None:
    """Q3 liquidity sweep / reclaim on H1 vs prior daily range."""
    try:
        info = mt5_module.symbol_info(symbol)
        tick = mt5_module.symbol_info_tick(symbol)
        if info is None or tick is None:
            return None
        pip = _pip_size(info)
        d1 = mt5_module.copy_rates_from_pos(symbol, mt5_module.TIMEFRAME_D1, 0, 4)
        if d1 is None or len(d1) < 2:
            return None
        prev = d1[1]
        pdh = float(prev["high"])
        pdl = float(prev["low"])

        h1 = mt5_module.copy_rates_from_pos(symbol, mt5_module.TIMEFRAME_H1, 0, 8)
        if h1 is None or len(h1) < 1:
            return None
        last = h1[-1]
        hi = float(last["high"])
        lo = float(last["low"])
        cl = float(last["close"])

        buf = 3.0 * pip
        slip = 5.0 * pip
        conf = float(live.get("confidence") or 0)
        regime = str(live.get("quadrant") or "Q3")

        direction = ""
        entry = 0.0
        sl = 0.0
        tp = 0.0

        if hi > pdh + buf and cl < pdh:
            direction = "SELL"
            entry = float(tick.bid)
            sl = hi + slip
            risk = abs(sl - entry)
            if risk <= 0:
                return None
            tp = entry - 2.0 * risk
        elif lo < pdl - buf and cl > pdl:
            direction = "BUY"
            entry = float(tick.ask)
            sl = lo - slip
            risk = abs(entry - sl)
            if risk <= 0:
                return None
            tp = entry + 2.0 * risk
        else:
            return None

        sl_pips = abs(entry - sl) / pip if pip > 0 else 0.0
        tp_pips = abs(tp - entry) / pip if pip > 0 else 0.0
        rr_ratio = (tp_pips / sl_pips) if sl_pips > 0 else 0.0
        st = "WATCHING"
        if conf >= 70.0:
            st = "ARMED"
        elif conf < 50.0:
            st = "NOT_READY"

        return Signal(
            symbol=symbol,
            direction=direction,
            entry_price=round(entry, 6),
            stop_loss=round(sl, 6),
            take_profit=round(tp, 6),
            sl_pips=round(sl_pips, 2),
            tp_pips=round(tp_pips, 2),
            rr_ratio=round(rr_ratio, 3),
            strategy="alpha_sweep",
            score=round(conf, 2),
            regime=regime,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            status=st,
        )
    except Exception:
        return None


def generate_breakout_signal_stub(_mt5_module: Any, _symbol: str, _live: dict[str, Any]) -> Signal | None:
    """Placeholder until breakout rules are specified."""
    return None


def generate_signal(live: dict[str, Any], mt5_module: Any, symbol: str) -> Signal | None:
    """Route by live headline quadrant."""
    if not live.get("mt5_connected"):
        return None
    q = str(live.get("quadrant") or "Q4").upper()
    if q == "Q4":
        return None
    if q == "Q3":
        return generate_alpha_sweep_signal(mt5_module, symbol, live)
    if q in ("Q1", "Q2"):
        return generate_breakout_signal_stub(mt5_module, symbol, live)
    return None


def signal_to_dict(sig: Signal | None) -> dict[str, Any] | None:
    if sig is None:
        return None
    return asdict(sig)


def build_signal_checks(
    sig: Signal | None,
    live: dict[str, Any],
    session: str,
) -> dict[str, bool]:
    spread = live.get("spread")
    try:
        sp = float(spread) if spread is not None else 999.0
    except (TypeError, ValueError):
        sp = 999.0
    quad = str(live.get("quadrant") or "Q4").upper()
    sess = (session or "").upper().strip()
    sess_ok = sess in ("LONDON", "NEW_YORK", "OVERLAP")
    if sig is None:
        return {
            "score_ok": False,
            "spread_ok": sp < 2.0,
            "session_ok": sess_ok,
            "rr_ok": False,
            "regime_ok": quad != "Q4",
        }
    sc = float(sig.score)
    return {
        "score_ok": sc >= 60.0,
        "spread_ok": sp < 2.0,
        "session_ok": sess_ok,
        "rr_ok": float(sig.rr_ratio) >= 2.0,
        "regime_ok": quad != "Q4" and sig.regime != "Q4",
    }
