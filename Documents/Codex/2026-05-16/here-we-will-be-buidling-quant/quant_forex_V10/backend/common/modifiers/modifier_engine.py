from __future__ import annotations

import math
from typing import Any


def _num(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def detect_modifiers(row: dict[str, Any], trade_direction: str | None = None) -> dict[str, Any]:
    modifiers: list[str] = []
    reasons: list[str] = []
    hard_block_reasons: list[str] = []

    required = ["adx", "er", "atr_percentile", "bb_width_percentile", "prev_swing_high", "prev_swing_low"]
    if any(row.get(key) is None or (isinstance(row.get(key), float) and math.isnan(row.get(key))) for key in required):
        modifiers.append("M00")
        hard_block_reasons.append("Not enough bars to calculate ADX, ER, ATR/BB percentiles, and swings.")

    session = row.get("session")
    htf = row.get("htf_bias")
    ltf = row.get("ltf_bias")
    spread_percentile = _num(row, "spread_percentile")
    distance = abs(_num(row, "distance_from_ema20_atr"))
    upper_wick = _num(row, "upper_wick_ratio")
    lower_wick = _num(row, "lower_wick_ratio")
    sentiment = row.get("sentiment", "NEUTRAL")

    if spread_percentile < 70 and not row.get("news_flag") and session != "Rollover" and distance < 2.5:
        modifiers.append("M01")
        reasons.append("Clean condition: spread is normal, no news flag, not rollover, and price is not overextended.")
    if row.get("compression_flag"):
        modifiers.append("M02")
        reasons.append("Compression is active.")
    if row.get("volatility_expansion_flag"):
        modifiers.append("M03")
        reasons.append("Volatility expansion is active.")
    if session == "London":
        modifiers.append("M04")
        reasons.append("London kill zone active.")
    if session == "NewYork":
        modifiers.append("M05")
        reasons.append("New York kill zone active.")
    if session == "Asia":
        modifiers.append("M06")
        reasons.append("Asia range window active.")
    if row.get("news_flag"):
        modifiers.append("M07")
        hard_block_reasons.append("News risk is active.")
    if htf != ltf and htf != "neutral" and ltf != "neutral":
        modifiers.append("M08")
        reasons.append("HTF and LTF bias conflict.")
    if row.get("sweep_high_flag") or row.get("sweep_low_flag"):
        modifiers.append("M09")
        reasons.append("Liquidity sweep detected.")
    if spread_percentile >= 90:
        modifiers.append("M10")
        hard_block_reasons.append("Spread percentile is 90 or higher.")
    if distance >= 2.5 and max(upper_wick, lower_wick) >= 0.45:
        modifiers.append("M11")
        reasons.append("Exhaustion risk: extension from EMA20 plus large wick.")
    if htf == ltf and htf != "neutral":
        modifiers.append("M12")
        reasons.append("HTF and LTF are aligned.")
    if session == "Rollover":
        modifiers.append("M13")
        hard_block_reasons.append("Rollover / low liquidity window.")
    if trade_direction == "long" and sentiment == "BULLISH":
        modifiers.append("M14")
        reasons.append("Sentiment aligns with long direction.")
    if trade_direction == "short" and sentiment == "BEARISH":
        modifiers.append("M14")
        reasons.append("Sentiment aligns with short direction.")
    if trade_direction == "long" and sentiment == "BEARISH":
        modifiers.append("M15")
        reasons.append("Sentiment conflicts with long direction.")
    if trade_direction == "short" and sentiment == "BULLISH":
        modifiers.append("M15")
        reasons.append("Sentiment conflicts with short direction.")

    return {
        "modifiers": list(dict.fromkeys(modifiers)),
        "hard_block": bool(hard_block_reasons),
        "hard_block_reasons": hard_block_reasons,
        "reasons": reasons,
    }
