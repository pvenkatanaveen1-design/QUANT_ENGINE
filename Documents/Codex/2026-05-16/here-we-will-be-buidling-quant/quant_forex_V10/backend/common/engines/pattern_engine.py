from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _flag(value: Any) -> bool:
    return bool(int(_num(value, 0)))


def _body_ratio(row: pd.Series) -> float:
    rng = _num(row.get("high")) - _num(row.get("low"))
    if rng <= 0:
        return 0.0
    return abs(_num(row.get("close")) - _num(row.get("open"))) / rng


def _round_step(symbol: str, close: float, kind: str) -> float:
    symbol = (symbol or "").upper()
    if "JPY" in symbol:
        return 0.50 if kind == "half" else 1.00
    if "XAU" in symbol or "XAG" in symbol:
        return 5.0 if kind == "half" else 10.0
    return 0.0050 if kind == "half" else 0.0100


def _nearest_level(price: float, step: float) -> float:
    if step <= 0:
        return price
    return round(price / step) * step


def _recent_bool(df: pd.DataFrame, idx: int, col: str, lookback: int) -> bool:
    if col not in df:
        return False
    start = max(0, idx - lookback + 1)
    return bool(pd.to_numeric(df.iloc[start : idx + 1][col], errors="coerce").fillna(0).astype(int).any())


def _add_pattern(
    patterns: list[dict[str, Any]],
    pattern_id: str,
    pattern_name: str,
    direction: str,
    score: float,
    reason: str,
    **details: Any,
) -> None:
    patterns.append(
        {
            "pattern_id": pattern_id,
            "pattern_name": pattern_name,
            "direction": direction,
            "score": round(float(score), 2),
            "reason": reason,
            **{k: v for k, v in details.items() if v is not None},
        }
    )


def _detect_fvg(df: pd.DataFrame, idx: int, direction: str, options: dict[str, Any], patterns: list[dict[str, Any]]) -> None:
    age = int(options.get("fvg_max_age_bars", 30))
    min_size = float(options.get("fvg_min_size_atr", 0.20))
    row = df.iloc[idx]
    atr = max(_num(row.get("atr")), 1e-12)
    start = max(2, idx - age + 1)
    best: dict[str, Any] | None = None

    for j in range(start, idx + 1):
        c1 = df.iloc[j - 2]
        c3 = df.iloc[j]
        if _num(c1.get("high")) < _num(c3.get("low")):
            zone_low = _num(c1.get("high"))
            zone_high = _num(c3.get("low"))
            size_atr = (zone_high - zone_low) / atr
            touched = _num(row.get("low")) <= zone_high and _num(row.get("close")) >= zone_low
            if size_atr >= min_size and touched:
                best = {"id": "FVG_BULL", "name": "Bullish FVG Retest", "dir": "long", "zone_low": zone_low, "zone_high": zone_high, "size_atr": size_atr, "age": idx - j}
        if _num(c1.get("low")) > _num(c3.get("high")):
            zone_low = _num(c3.get("high"))
            zone_high = _num(c1.get("low"))
            size_atr = (zone_high - zone_low) / atr
            touched = _num(row.get("high")) >= zone_low and _num(row.get("close")) <= zone_high
            if size_atr >= min_size and touched:
                best = {"id": "FVG_BEAR", "name": "Bearish FVG Retest", "dir": "short", "zone_low": zone_low, "zone_high": zone_high, "size_atr": size_atr, "age": idx - j}

    if not best:
        return
    aligned = best["dir"] == direction
    score = 3 if aligned else -2
    _add_pattern(
        patterns,
        best["id"],
        best["name"],
        best["dir"],
        score,
        "Recent three-candle imbalance retested in trade direction." if aligned else "Opposing FVG is active near entry.",
        zone_low=round(best["zone_low"], 6),
        zone_high=round(best["zone_high"], 6),
        size_atr=round(best["size_atr"], 3),
        age_bars=best["age"],
    )


def _detect_order_block(df: pd.DataFrame, idx: int, direction: str, options: dict[str, Any], patterns: list[dict[str, Any]]) -> None:
    max_age = int(options.get("ob_max_age_bars", 60))
    min_body = float(options.get("ob_displacement_body_ratio_min", 0.60))
    min_range_atr = float(options.get("ob_displacement_candle_range_atr_min", 1.20))
    row = df.iloc[idx]
    start = max(1, idx - max_age)
    best: dict[str, Any] | None = None

    for j in range(start, idx + 1):
        disp = df.iloc[j]
        is_bull_disp = _num(disp.get("close")) > _num(disp.get("open")) and _body_ratio(disp) >= min_body and _num(disp.get("candle_range_atr")) >= min_range_atr
        is_bear_disp = _num(disp.get("close")) < _num(disp.get("open")) and _body_ratio(disp) >= min_body and _num(disp.get("candle_range_atr")) >= min_range_atr
        if not (is_bull_disp or is_bear_disp):
            continue
        for k in range(j - 1, max(start - 1, j - 6), -1):
            ob = df.iloc[k]
            if is_bull_disp and _num(ob.get("close")) < _num(ob.get("open")):
                zone_low, zone_high = _num(ob.get("low")), _num(ob.get("high"))
                if _num(row.get("low")) <= zone_high and _num(row.get("high")) >= zone_low:
                    best = {"id": "OB_BULL", "name": "Bullish Order Block Mitigation", "dir": "long", "zone_low": zone_low, "zone_high": zone_high, "age": idx - k}
                break
            if is_bear_disp and _num(ob.get("close")) > _num(ob.get("open")):
                zone_low, zone_high = _num(ob.get("low")), _num(ob.get("high"))
                if _num(row.get("low")) <= zone_high and _num(row.get("high")) >= zone_low:
                    best = {"id": "OB_BEAR", "name": "Bearish Order Block Mitigation", "dir": "short", "zone_low": zone_low, "zone_high": zone_high, "age": idx - k}
                break

    if not best:
        return
    aligned = best["dir"] == direction
    _add_pattern(
        patterns,
        best["id"],
        best["name"],
        best["dir"],
        3 if aligned else -2,
        "Last opposite candle before displacement is being mitigated." if aligned else "Opposing order-block zone is being mitigated.",
        zone_low=round(best["zone_low"], 6),
        zone_high=round(best["zone_high"], 6),
        age_bars=best["age"],
    )


def _detect_structure(df: pd.DataFrame, idx: int, direction: str, options: dict[str, Any], patterns: list[dict[str, Any]]) -> None:
    row = df.iloc[idx]
    atr = _num(row.get("atr"))
    buffer = atr * float(options.get("bos_atr_buffer", 0.10))
    close = _num(row.get("close"))
    swing_high = _num(row.get("prev_swing_high"), np.nan)
    swing_low = _num(row.get("prev_swing_low"), np.nan)
    if not np.isnan(swing_high) and close > swing_high + buffer:
        _add_pattern(patterns, "BOS_BULL", "Bullish Break of Structure", "long", 2 if direction == "long" else -2, "Candle close broke previous swing high with ATR buffer.", level=round(swing_high, 6))
    if not np.isnan(swing_low) and close < swing_low - buffer:
        _add_pattern(patterns, "BOS_BEAR", "Bearish Break of Structure", "short", 2 if direction == "short" else -2, "Candle close broke previous swing low with ATR buffer.", level=round(swing_low, 6))


def _detect_mss(df: pd.DataFrame, idx: int, direction: str, patterns: list[dict[str, Any]]) -> None:
    row = df.iloc[idx]
    sweep_low = _recent_bool(df, idx, "sweep_low_flag", 5)
    sweep_high = _recent_bool(df, idx, "sweep_high_flag", 5)
    bull_shift = sweep_low and _num(row.get("close")) > _num(row.get("ema20")) and _num(row.get("close")) > _num(row.get("open"))
    bear_shift = sweep_high and _num(row.get("close")) < _num(row.get("ema20")) and _num(row.get("close")) < _num(row.get("open"))
    if bull_shift:
        _add_pattern(patterns, "MSS_BULL", "Bullish Market Structure Shift", "long", 3 if direction == "long" else -2, "Downside sweep followed by bullish reclaim candle.")
    if bear_shift:
        _add_pattern(patterns, "MSS_BEAR", "Bearish Market Structure Shift", "short", 3 if direction == "short" else -2, "Upside sweep followed by bearish rejection candle.")


def _detect_liquidity(df: pd.DataFrame, idx: int, direction: str, patterns: list[dict[str, Any]]) -> None:
    row = df.iloc[idx]
    atr = max(_num(row.get("atr")), 1e-12)
    low = _num(row.get("low"))
    high = _num(row.get("high"))
    levels: list[str] = []
    if direction == "long":
        for label, value in [("prev_swing_low", row.get("prev_swing_low")), ("prev_day_low", row.get("prev_day_low")), ("asia_low", row.get("asia_low"))]:
            val = _num(value, np.nan)
            if not np.isnan(val) and abs(low - val) <= atr * 0.20:
                levels.append(label)
        if _recent_bool(df, idx, "sweep_low_flag", 5):
            levels.append("sweep_low")
        if levels:
            _add_pattern(patterns, "LIQ_POOL_LOW", "Downside Liquidity Pool / Sweep", "long", 2 if "sweep_low" in levels else 1, "Price interacted with downside liquidity pool.", levels=", ".join(sorted(set(levels))))
    if direction == "short":
        for label, value in [("prev_swing_high", row.get("prev_swing_high")), ("prev_day_high", row.get("prev_day_high")), ("asia_high", row.get("asia_high"))]:
            val = _num(value, np.nan)
            if not np.isnan(val) and abs(high - val) <= atr * 0.20:
                levels.append(label)
        if _recent_bool(df, idx, "sweep_high_flag", 5):
            levels.append("sweep_high")
        if levels:
            _add_pattern(patterns, "LIQ_POOL_HIGH", "Upside Liquidity Pool / Sweep", "short", 2 if "sweep_high" in levels else 1, "Price interacted with upside liquidity pool.", levels=", ".join(sorted(set(levels))))


def _detect_round_number(symbol: str, row: pd.Series, direction: str, options: dict[str, Any], patterns: list[dict[str, Any]]) -> None:
    close = _num(row.get("close"))
    atr = max(_num(row.get("atr")), 1e-12)
    tolerance = atr * float(options.get("round_number_tolerance_atr", 0.25))
    levels = [
        ("50", _nearest_level(close, _round_step(symbol, close, "half"))),
        ("100", _nearest_level(close, _round_step(symbol, close, "whole"))),
    ]
    for label, level in levels:
        near = abs(close - level) <= tolerance or _num(row.get("low")) <= level <= _num(row.get("high"))
        if not near:
            continue
        if direction == "long" and _num(row.get("low")) <= level and close > level and _num(row.get("lower_wick_ratio")) >= 0.25:
            _add_pattern(patterns, f"ROUND_{label}_LONG", f"{label}-Pip Round Number Reclaim", "long", 1, "Round-number reclaim with lower-wick rejection.", level=round(level, 6))
        elif direction == "short" and _num(row.get("high")) >= level and close < level and _num(row.get("upper_wick_ratio")) >= 0.25:
            _add_pattern(patterns, f"ROUND_{label}_SHORT", f"{label}-Pip Round Number Rejection", "short", 1, "Round-number rejection with upper-wick rejection.", level=round(level, 6))


def _detect_vwap(df: pd.DataFrame, idx: int, direction: str, options: dict[str, Any], patterns: list[dict[str, Any]]) -> None:
    row = df.iloc[idx]
    dist = _num(row.get("distance_from_vwap_atr"))
    vwap = _num(row.get("session_vwap"), np.nan)
    if np.isnan(vwap):
        return
    extreme = float(options.get("vwap_reversion_distance_atr", 1.50))
    if direction == "short" and dist >= extreme and _num(row.get("upper_wick_ratio")) >= 0.30:
        _add_pattern(patterns, "VWAP_HIGH_REVERSION", "VWAP High Mean-Reversion", "short", 2, "Price is stretched above session VWAP with rejection.", level=round(vwap, 6), distance_atr=round(dist, 3))
    if direction == "long" and dist <= -extreme and _num(row.get("lower_wick_ratio")) >= 0.30:
        _add_pattern(patterns, "VWAP_LOW_REVERSION", "VWAP Low Mean-Reversion", "long", 2, "Price is stretched below session VWAP with rejection.", level=round(vwap, 6), distance_atr=round(dist, 3))


def _detect_session_vwap(row: pd.Series, direction: str, patterns: list[dict[str, Any]]) -> None:
    vwap = _num(row.get("session_vwap"), np.nan)
    if np.isnan(vwap):
        return
    if direction == "long" and _num(row.get("low")) <= vwap and _num(row.get("close")) > vwap:
        _add_pattern(patterns, "SESSION_VWAP_RECLAIM_LONG", "Session VWAP Reclaim", "long", 2, "Candle reclaimed session VWAP in long direction.", level=round(vwap, 6))
    if direction == "short" and _num(row.get("high")) >= vwap and _num(row.get("close")) < vwap:
        _add_pattern(patterns, "SESSION_VWAP_REJECT_SHORT", "Session VWAP Rejection", "short", 2, "Candle rejected session VWAP in short direction.", level=round(vwap, 6))


def _detect_mvwap(df: pd.DataFrame, idx: int, direction: str, patterns: list[dict[str, Any]]) -> None:
    if idx < 50:
        return
    window = df.iloc[: idx + 1].copy()
    typical = (window["high"] + window["low"] + window["close"]) / 3
    volume = pd.to_numeric(window["tick_volume"], errors="coerce").replace(0, np.nan).fillna(1.0)
    pv = typical * volume
    mvwap20 = float(pv.tail(20).sum() / volume.tail(20).sum())
    mvwap50 = float(pv.tail(50).sum() / volume.tail(50).sum())
    row = df.iloc[idx]
    atr = max(_num(row.get("atr")), 1e-12)
    if direction == "long" and _num(row.get("close")) > mvwap20 > mvwap50 and _num(row.get("low")) <= mvwap20 + atr * 0.20:
        _add_pattern(patterns, "MVWAP_BULL_RECLAIM", "Bullish MVWAP Reclaim", "long", 2, "Price reclaimed MVWAP20 while MVWAP20 is above MVWAP50.", mvwap20=round(mvwap20, 6), mvwap50=round(mvwap50, 6))
    if direction == "short" and _num(row.get("close")) < mvwap20 < mvwap50 and _num(row.get("high")) >= mvwap20 - atr * 0.20:
        _add_pattern(patterns, "MVWAP_BEAR_REJECT", "Bearish MVWAP Rejection", "short", 2, "Price rejected MVWAP20 while MVWAP20 is below MVWAP50.", mvwap20=round(mvwap20, 6), mvwap50=round(mvwap50, 6))


def detect_patterns(df: pd.DataFrame, idx: int, signal: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    use_patterns = bool(options.get("use_patterns", True))
    direction = str(signal.get("direction") or "both").lower()
    if not use_patterns or direction not in {"long", "short"}:
        return {
            "patterns_detected": [],
            "pattern_score": 0.0,
            "pattern_decision": "OFF" if not use_patterns else "NO_DIRECTION",
            "pattern_summary": "Pattern engine disabled." if not use_patterns else "No directional signal for pattern validation.",
        }

    row = df.iloc[idx]
    symbol = str(signal.get("symbol") or row.get("symbol") or "")
    patterns: list[dict[str, Any]] = []

    if options.get("use_fvg", True):
        _detect_fvg(df, idx, direction, options, patterns)
    if options.get("use_order_blocks", True):
        _detect_order_block(df, idx, direction, options, patterns)
    if options.get("use_bos", True):
        _detect_structure(df, idx, direction, options, patterns)
    if options.get("use_mss", True):
        _detect_mss(df, idx, direction, patterns)
    if options.get("use_liquidity_pools", True) or options.get("use_ict", True):
        _detect_liquidity(df, idx, direction, patterns)
    if options.get("use_round_numbers", True):
        _detect_round_number(symbol, row, direction, options, patterns)
    if options.get("use_vwap", True):
        _detect_vwap(df, idx, direction, options, patterns)
    if options.get("use_session_vwap", True):
        _detect_session_vwap(row, direction, patterns)
    if options.get("use_mvwap", options.get("use_moving_vwap", True)):
        _detect_mvwap(df, idx, direction, patterns)

    score = sum(float(p.get("score") or 0) for p in patterns)
    min_score = float(options.get("min_pattern_score", 2))
    mode = str(options.get("pattern_score_mode", "score_only"))
    decision = "ALLOW" if score >= min_score else ("WATCH" if mode == "score_only" else "BLOCK")
    summary = ", ".join(p["pattern_id"] for p in patterns) if patterns else "No enabled pattern confirmed."
    return {
        "patterns_detected": patterns,
        "pattern_score": round(score, 2),
        "pattern_decision": decision,
        "pattern_summary": summary,
    }
