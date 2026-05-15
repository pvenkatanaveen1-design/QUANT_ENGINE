"""
Section 5 — signal function library (S01–S08).
Primary-slot logic per master spec; invoked from systems.strategy.signals.compute_signal.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any, Callable

from core.models.regime import RegimeResult
from systems.strategy.signal_routing import signal_code_for_regime


@dataclass
class SignalResult:
    direction: str  # "BUY" | "SELL" | "NONE"
    entry_price: float
    stop_price: float
    tp_price: float
    rr_ratio: float
    confidence: float
    reason: str
    strategy_id: str
    size_override: float = -1.0


def _closes(rows: list[dict[str, Any]]) -> list[float]:
    return [float(r["close"]) for r in rows]


def _ema_last(values: list[float], period: int) -> float:
    """SMA-seeded EMA (aligned with systems.strategy.signals._ema)."""
    if not values:
        return 0.0
    if len(values) < period:
        return mean(values)
    multiplier = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for value in values[period:]:
        ema = (value - ema) * multiplier + ema
    return ema


def _atr(rows: list[dict[str, Any]], period: int = 14) -> float:
    if len(rows) < 2:
        return 0.0
    trs: list[float] = []
    for i, r in enumerate(rows):
        h, l = float(r["high"]), float(r["low"])
        if i == 0:
            trs.append(h - l)
        else:
            pc = float(rows[i - 1]["close"])
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    window = trs[-period:] if len(trs) >= period else trs
    return mean(window) if window else 0.0


def _bb(closes: list[float], period: int = 20, n_std: float = 2.0) -> tuple[float, float, float]:
    """Returns (upper, lower, mid)."""
    if len(closes) < period:
        c = closes[-1] if closes else 0.0
        return c, c, c
    window = closes[-period:]
    mid = mean(window)
    sd = pstdev(window) if len(window) > 1 else 0.0
    return mid + n_std * sd, mid - n_std * sd, mid


def _rolling_max(values: list[float], period: int) -> float:
    return max(values[-period:]) if len(values) >= period else max(values)


def _rolling_min(values: list[float], period: int) -> float:
    return min(values[-period:]) if len(values) >= period else min(values)


def _is_asia_session_row(row: dict[str, Any]) -> bool:
    lab = str(row.get("session_label") or "").lower()
    return lab in {"asia", "tokyo", "sydney", "asian"} or "asia" in lab


def ema_pullback_signal(rows: list[dict[str, Any]], regime_id: str, *, adx: float = 0.0) -> SignalResult:
    _ = adx
    sid = "S01_ema_pullback"
    if len(rows) < 55:
        return SignalResult("NONE", 0, 0, 0, 0, 0, "Insufficient bars (<55)", sid)
    closes = _closes(rows)
    ema20 = _ema_last(closes[-35:], 20)
    ema50 = _ema_last(closes[-80:], 50)
    atr = _atr(rows)
    if atr <= 0:
        return SignalResult("NONE", 0, 0, 0, 0, 0, "ATR=0", sid)
    last = rows[-1]
    low, high, close = float(last["low"]), float(last["high"]), float(last["close"])

    is_q2 = regime_id.upper().startswith("Q2")
    rr_target = 2.5
    atr_stop_mult = 0.75 if is_q2 else 0.5

    if ema20 > ema50 and close > ema20 and low <= ema20 * 1.0008:
        stop = low - atr * atr_stop_mult
        tp = close + (close - stop) * rr_target
        sz = 0.35 if regime_id.upper() == "Q2_M08" else -1.0
        return SignalResult(
            "BUY",
            close,
            stop,
            tp,
            (tp - close) / max(close - stop, 1e-10),
            0.70,
            f"EMA20 pullback uptrend. EMA20={ema20:.5f} EMA50={ema50:.5f}",
            sid,
            size_override=sz,
        )

    if ema20 < ema50 and close < ema20 and high >= ema20 * 0.9992:
        stop = high + atr * atr_stop_mult
        tp = close - (stop - close) * rr_target
        sz = 0.35 if regime_id.upper() == "Q2_M08" else -1.0
        return SignalResult(
            "SELL",
            close,
            stop,
            tp,
            (close - tp) / max(stop - close, 1e-10),
            0.70,
            f"EMA20 pullback downtrend. EMA20={ema20:.5f} EMA50={ema50:.5f}",
            sid,
            size_override=sz,
        )

    return SignalResult("NONE", 0, 0, 0, 0, 0, f"No EMA20 pullback. EMA20={ema20:.5f} ema50={ema50:.5f} close={close:.5f}", sid)


def donchian_continuation_signal(rows: list[dict[str, Any]], regime_id: str, *, adx: float = 0.0) -> SignalResult:
    _ = adx
    sid = "S02_donchian"
    if len(rows) < 55:
        return SignalResult("NONE", 0, 0, 0, 0, 0, "Insufficient bars", sid)
    closes = _closes(rows)
    highs = [float(r["high"]) for r in rows]
    lows = [float(r["low"]) for r in rows]
    atr = _atr(rows)
    ema50 = _ema_last(closes[-80:], 50)
    don_hi = _rolling_max(highs[:-1], 20)
    don_lo = _rolling_min(lows[:-1], 20)
    close = float(rows[-1]["close"])
    high = float(rows[-1]["high"])
    low = float(rows[-1]["low"])
    if atr <= 0:
        return SignalResult("NONE", 0, 0, 0, 0, 0, "ATR=0", sid)

    stop_mult = 0.4 if regime_id.upper().startswith("Q2") else 0.3
    rr = 3.0

    if close > don_hi and close > ema50:
        stop = low - atr * stop_mult
        tp = close + (close - stop) * rr
        return SignalResult(
            "BUY",
            close,
            stop,
            tp,
            (tp - close) / max(close - stop, 1e-10),
            0.65,
            f"Donchian 20-bar break above {don_hi:.5f}. EMA50={ema50:.5f}",
            sid,
        )

    if close < don_lo and close < ema50:
        stop = high + atr * stop_mult
        tp = close - (stop - close) * rr
        return SignalResult(
            "SELL",
            close,
            stop,
            tp,
            (close - tp) / max(stop - close, 1e-10),
            0.65,
            f"Donchian 20-bar break below {don_lo:.5f}. EMA50={ema50:.5f}",
            sid,
        )

    return SignalResult("NONE", 0, 0, 0, 0, 0, f"No Donchian break. don_hi={don_hi:.5f} don_lo={don_lo:.5f} close={close:.5f}", sid)


def bollinger_fade_signal(rows: list[dict[str, Any]], regime_id: str, *, adx: float = 0.0) -> SignalResult:
    sid = "S03_bb_fade"
    if len(rows) < 25:
        return SignalResult("NONE", 0, 0, 0, 0, 0, "Insufficient bars (<25)", sid)
    if adx > 20:
        return SignalResult("NONE", 0, 0, 0, 0, 0, f"ADX {adx:.1f} > 20 — range fade blocked", sid)
    closes = _closes(rows)
    upper, lower, mid = _bb(closes)
    atr = _atr(rows)
    close = float(rows[-1]["close"])
    high = float(rows[-1]["high"])
    low = float(rows[-1]["low"])
    if atr <= 0:
        return SignalResult("NONE", 0, 0, 0, 0, 0, "ATR=0", sid)

    if abs(close - mid) > 2.5 * atr:
        return SignalResult("NONE", 0, 0, 0, 0, 0, f"Price {abs(close - mid):.5f} from mid — too extended for range fade", sid)

    rr = 1.5 if regime_id.upper() == "Q3_M02" else 1.8

    if close >= upper * 0.999:
        stop = high + atr * 0.30
        tp = mid
        return SignalResult(
            "SELL",
            close,
            stop,
            tp,
            (close - tp) / max(stop - close, 1e-10),
            0.67,
            f"Close at upper BB {upper:.5f}. Target mid {mid:.5f}. ADX<20 confirmed range fade.",
            sid,
        )

    if close <= lower * 1.001:
        stop = low - atr * 0.30
        tp = mid
        return SignalResult(
            "BUY",
            close,
            stop,
            tp,
            (tp - close) / max(close - stop, 1e-10),
            0.67,
            f"Close at lower BB {lower:.5f}. Target mid {mid:.5f}. ADX<20 confirmed range fade.",
            sid,
        )

    return SignalResult("NONE", 0, 0, 0, 0, 0, f"Price not at BB extreme. upper={upper:.5f} lower={lower:.5f} close={close:.5f}", sid)


def asian_sweep_reversal_signal(rows: list[dict[str, Any]], regime_id: str, *, adx: float = 0.0) -> SignalResult:
    _ = adx
    sid = "S04_asian_sweep"
    if len(rows) < 40:
        return SignalResult("NONE", 0, 0, 0, 0, 0, "Insufficient bars (<40)", sid)

    atr = _atr(rows)
    last = rows[-1]
    close = float(last["close"])
    high = float(last["high"])
    low = float(last["low"])
    open_ = float(last["open"])
    if atr <= 0:
        return SignalResult("NONE", 0, 0, 0, 0, 0, "ATR=0", sid)

    asia_bars = [r for r in rows[-40:] if _is_asia_session_row(r)]
    if len(asia_bars) < 4:
        asia_bars = rows[-32:-16]
    if not asia_bars:
        return SignalResult("NONE", 0, 0, 0, 0, 0, "No Asian session bars found", sid)

    asia_high = max(float(b["high"]) for b in asia_bars)
    asia_low = min(float(b["low"]) for b in asia_bars)
    candle_range = max(high - low, 1e-10)
    body = abs(close - open_)
    body_ratio = body / candle_range

    if high > asia_high and close < asia_high and body_ratio < 0.5:
        stop = high + atr * 0.20
        tp = asia_low
        rr = (close - tp) / max(stop - close, 1e-10)
        if rr < 2.0:
            return SignalResult("NONE", 0, 0, 0, 0, 0, f"RR {rr:.2f} below 2.0 minimum. Asia high={asia_high:.5f}", sid)
        return SignalResult(
            "SELL",
            close,
            stop,
            tp,
            rr,
            0.75,
            f"Asia high {asia_high:.5f} swept by wick. Body back inside. SHORT to asia_low {tp:.5f}. body_ratio={body_ratio:.2f}",
            sid,
        )

    if low < asia_low and close > asia_low and body_ratio < 0.5:
        stop = low - atr * 0.20
        tp = asia_high
        rr = (tp - close) / max(close - stop, 1e-10)
        if rr < 2.0:
            return SignalResult("NONE", 0, 0, 0, 0, 0, f"RR {rr:.2f} below 2.0 minimum. Asia low={asia_low:.5f}", sid)
        return SignalResult(
            "BUY",
            close,
            stop,
            tp,
            rr,
            0.75,
            f"Asia low {asia_low:.5f} swept by wick. Body back inside. LONG to asia_high {tp:.5f}. body_ratio={body_ratio:.2f}",
            sid,
        )

    return SignalResult(
        "NONE",
        0,
        0,
        0,
        0,
        0,
        f"No Asian sweep pattern. asia_high={asia_high:.5f} asia_low={asia_low:.5f} high={high:.5f} low={low:.5f} body_ratio={body_ratio:.2f}",
        sid,
    )


def sweep_reclaim_signal(rows: list[dict[str, Any]], regime_id: str, *, adx: float = 0.0) -> SignalResult:
    _ = adx
    sid = "S05_sweep_reclaim"
    if len(rows) < 22:
        return SignalResult("NONE", 0, 0, 0, 0, 0, "Insufficient bars (<22)", sid)
    atr = _atr(rows)
    last = rows[-1]
    close = float(last["close"])
    high = float(last["high"])
    low = float(last["low"])
    open_ = float(last["open"])
    if atr <= 0:
        return SignalResult("NONE", 0, 0, 0, 0, 0, "ATR=0", sid)

    prior_high = max(float(r["high"]) for r in rows[-21:-1])
    prior_low = min(float(r["low"]) for r in rows[-21:-1])
    candle_range = max(high - low, 1e-10)
    body_top = max(open_, close)
    body_bot = min(open_, close)
    upper_wick = (high - body_top) / candle_range
    lower_wick = (body_bot - low) / candle_range

    stop_mult = 0.35 if regime_id.upper().startswith("Q2") else 0.25
    rr = 3.0

    if high > prior_high and close < prior_high and upper_wick > 0.45:
        stop = high + atr * stop_mult
        tp = close - (stop - close) * rr
        sz = 0.35 if regime_id.upper() == "Q2_M09" else -1.0
        return SignalResult(
            "SELL",
            close,
            stop,
            tp,
            (close - tp) / max(stop - close, 1e-10),
            0.70,
            f"Prior 20-bar high {prior_high:.5f} swept. Upper wick {upper_wick:.0%}. SHORT.",
            sid,
            size_override=sz,
        )

    if low < prior_low and close > prior_low and lower_wick > 0.45:
        stop = low - atr * stop_mult
        tp = close + (close - stop) * rr
        sz = 0.35 if regime_id.upper() == "Q2_M09" else -1.0
        return SignalResult(
            "BUY",
            close,
            stop,
            tp,
            (tp - close) / max(close - stop, 1e-10),
            0.70,
            f"Prior 20-bar low {prior_low:.5f} swept. Lower wick {lower_wick:.0%}. LONG.",
            sid,
            size_override=sz,
        )

    return SignalResult(
        "NONE",
        0,
        0,
        0,
        0,
        0,
        f"No sweep+reclaim. prior_high={prior_high:.5f} prior_low={prior_low:.5f} wick_up={upper_wick:.0%} wick_dn={lower_wick:.0%}",
        sid,
    )


def failed_breakout_fade_signal(rows: list[dict[str, Any]], regime_id: str, *, adx: float = 0.0) -> SignalResult:
    _ = adx
    sid = "S06_failed_bo_fade"
    if len(rows) < 25:
        return SignalResult("NONE", 0, 0, 0, 0, 0, "Insufficient bars (<25)", sid)
    closes = _closes(rows)
    highs = [float(r["high"]) for r in rows]
    lows = [float(r["low"]) for r in rows]
    atr = _atr(rows)
    close = float(rows[-1]["close"])
    high = float(rows[-1]["high"])
    low = float(rows[-1]["low"])
    if atr <= 0:
        return SignalResult("NONE", 0, 0, 0, 0, 0, "ATR=0", sid)

    range_high = max(highs[-20:-1])
    range_low = min(lows[-20:-1])
    _, _, mid = _bb(closes)
    prev_high = float(rows[-2]["high"])
    prev_low = float(rows[-2]["low"])

    if prev_high > range_high and close < range_high:
        stop = high + atr * 0.30
        tp = mid
        return SignalResult(
            "SELL",
            close,
            stop,
            tp,
            (close - tp) / max(stop - close, 1e-10),
            0.63,
            f"Failed breakout above {range_high:.5f}. Fade to mid={mid:.5f}",
            sid,
        )

    if prev_low < range_low and close > range_low:
        stop = low - atr * 0.30
        tp = mid
        return SignalResult(
            "BUY",
            close,
            stop,
            tp,
            (tp - close) / max(close - stop, 1e-10),
            0.63,
            f"Failed breakout below {range_low:.5f}. Fade to mid={mid:.5f}",
            sid,
        )

    return SignalResult("NONE", 0, 0, 0, 0, 0, f"No failed breakout. range_high={range_high:.5f} range_low={range_low:.5f}", sid)


def carry_drift_signal(rows: list[dict[str, Any]], regime_id: str, *, adx: float = 0.0) -> SignalResult:
    _ = adx
    sid = "S07_carry_drift"
    if len(rows) < 30:
        return SignalResult("NONE", 0, 0, 0, 0, 0, "Insufficient bars (<30)", sid)

    closes = _closes(rows)
    ema20 = _ema_last(closes[-35:], 20)
    ema50 = _ema_last(closes[-80:], 50)
    atr = _atr(rows)
    close = float(rows[-1]["close"])
    last = rows[-1]
    high = float(last["high"])
    low = float(last["low"])

    spreads = [float(r.get("spread") or 0) for r in rows[-30:]]
    spread = float(rows[-1].get("spread") or 0)
    spread_avg = mean([s for s in spreads if s > 0]) if any(s > 0 for s in spreads) else 0.0
    if spread_avg > 0 and spread > spread_avg * 1.5:
        return SignalResult("NONE", 0, 0, 0, 0, 0, f"Spread {spread:.1f} > 1.5x avg {spread_avg:.1f}. Asia carry skipped.", sid)

    if ema20 > ema50 and close > ema20:
        stop = low - atr * 0.50
        tp = close + (close - stop) * 2.0
        return SignalResult(
            "BUY",
            close,
            stop,
            tp,
            (tp - close) / max(close - stop, 1e-10),
            0.55,
            f"Asia carry drift BUY. EMA20={ema20:.5f} > EMA50={ema50:.5f}. 0.5x size.",
            sid,
            size_override=0.5,
        )

    if ema20 < ema50 and close < ema20:
        stop = high + atr * 0.50
        tp = close - (stop - close) * 2.0
        return SignalResult(
            "SELL",
            close,
            stop,
            tp,
            (close - tp) / max(stop - close, 1e-10),
            0.55,
            f"Asia carry drift SELL. EMA20={ema20:.5f} < EMA50={ema50:.5f}. 0.5x size.",
            sid,
            size_override=0.5,
        )

    return SignalResult("NONE", 0, 0, 0, 0, 0, f"No carry drift setup. EMA20={ema20:.5f} EMA50={ema50:.5f}", sid)


def no_trade_signal(rows: list[dict[str, Any]], regime_id: str, *, adx: float = 0.0) -> SignalResult:
    _ = adx
    _ = rows
    sid = "S08_no_trade"
    reasons: dict[str, str] = {
        "Q1_M06": "Late session — trail only, no new entries",
        "Q1_M07": "Pre-news — reduce size 50%, no new entries",
        "Q1_M10": "High spread — edge is negative after cost",
        "Q2_M03": "Asia + high vol — thin liquidity + noise = skip",
        "Q2_M06": "Late session + high vol — close all risk",
        "Q2_M07": "Pre-news + high vol — HARD NO TRADE",
        "Q2_M10": "High vol + high spread — KILL SWITCH candidate",
        "Q2_M11": "High vol exhaustion — protect profits, trail only",
        "Q3_M06": "Late range — spread eats all profit potential",
        "Q3_M07": "Pre-news — news will break any range. Cancel pending orders.",
        "Q3_M10": "Range profit too small to overcome high spread",
    }
    rid = regime_id.upper()
    base = rid[:2]
    if base == "Q4":
        reason = "Q4 defensive: ambiguous regime. Trading EV negative after spread."
    else:
        reason = reasons.get(rid, f"No trade condition for {rid}")
    return SignalResult("NONE", 0, 0, 0, 0, 0, reason, sid)


CODE_TO_FN: dict[str, Callable[..., SignalResult]] = {
    "S01_ema_pullback": ema_pullback_signal,
    "S02_donchian": donchian_continuation_signal,
    "S03_bb_fade": bollinger_fade_signal,
    "S04_asian_sweep": asian_sweep_reversal_signal,
    "S05_sweep_reclaim": sweep_reclaim_signal,
    "S06_failed_bo_fade": failed_breakout_fade_signal,
    "S07_carry_drift": carry_drift_signal,
    "S08_no_trade": no_trade_signal,
}


def run_section5_signal(rows: list[dict[str, Any]], regime: RegimeResult) -> SignalResult:
    """Dispatch Section 5 signal using config/signal_routing.yaml (signal_code_for_regime)."""
    rid = regime.regime_id.upper()
    code = signal_code_for_regime(rid)
    fn = CODE_TO_FN.get(code, no_trade_signal)
    adx = float(regime.features.adx or 0.0)
    return fn(rows, rid, adx=adx)


def compute_signal_section5(rows: list[dict[str, Any]], regime_id: str) -> SignalResult:
    """Standalone API: regime_id only (ADX unavailable → Bollinger ADX gate uses 0)."""
    rid = regime_id.upper()
    code = signal_code_for_regime(rid)
    fn = CODE_TO_FN.get(code, no_trade_signal)
    return fn(rows, rid, adx=0.0)
