from __future__ import annotations

import math
from typing import Any

from backend.common.config_loader import load_regimes
from backend.common.modifiers.modifier_engine import detect_modifiers


REGIME_BY_ID = {item["regime_id"]: item for item in load_regimes()}


def _num(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _cal(row: dict[str, Any], regime_id: str, key: str, default: float) -> float:
    return _num(row, f"cal_{regime_id.lower()}_{key}", default)


def _confidence_ok(row: dict[str, Any], regime_id: str, confidence: float, default: float) -> bool:
    return confidence >= _cal(row, regime_id, "confidence_min", default)


def _has_value(row: dict[str, Any], key: str) -> bool:
    value = row.get(key)
    try:
        return value is not None and not math.isnan(float(value))
    except (TypeError, ValueError):
        return value is not None


def _condition(label: str, passed: bool, reasons: list[str], failures: list[str]) -> bool:
    (reasons if passed else failures).append(label)
    return passed


def _base_result(regime_id: str, passed: int, total: int, reasons: list[str], failures: list[str], active: bool) -> dict[str, Any]:
    cfg = REGIME_BY_ID[regime_id]
    confidence = round(passed / total if total else 0, 4)
    return {
        "regime_id": cfg["regime_id"],
        "regime_name": cfg["regime_name"],
        "confidence": confidence,
        "is_active": active,
        "direction": cfg["direction"],
        "conditions_passed": reasons,
        "conditions_failed": failures,
        "reasons": reasons,
        "failed_conditions": failures,
        "allowed_strategies": cfg["allowed_strategies"],
        "blocked_strategies": cfg.get("blocked_strategies", []),
        "risk_range": cfg.get("risk", {}).get("funded_suggested", ""),
        "reason": f"{cfg['regime_name']} evaluated with confidence {confidence}.",
    }


def _missing_critical(row: dict[str, Any]) -> bool:
    required = ["adx", "er", "atr", "atr_percentile", "bb_width_percentile", "prev_swing_high", "prev_swing_low"]
    return any(not _has_value(row, key) for key in required)


def _hour(row: dict[str, Any]) -> int:
    ts = row.get("timestamp")
    try:
        return int(getattr(ts, "hour"))
    except Exception:
        return -1


def _dayofweek(row: dict[str, Any]) -> int:
    ts = row.get("timestamp")
    try:
        return int(getattr(ts, "dayofweek"))
    except Exception:
        return -1


def _opening_range_exists(row: dict[str, Any]) -> bool:
    return _has_value(row, "opening_range_high") and _has_value(row, "opening_range_low")


def _usd_direction(row: dict[str, Any], usd_bias: str) -> str | None:
    symbol = str(row.get("symbol", "")).upper()
    if not symbol or "USD" not in symbol:
        return None
    usd_is_base = symbol.startswith("USD")
    usd_is_quote = symbol.endswith("USD")
    if usd_bias == "USD_BULLISH":
        if usd_is_base:
            return "long"
        if usd_is_quote:
            return "short"
    if usd_bias == "USD_BEARISH":
        if usd_is_base:
            return "short"
        if usd_is_quote:
            return "long"
    return None


def _bias_agrees(row: dict[str, Any], direction: str | None) -> bool:
    if direction == "long":
        return row.get("htf_bias") == "bullish"
    if direction == "short":
        return row.get("htf_bias") == "bearish"
    return False


def _ltf_agrees(row: dict[str, Any], direction: str | None) -> bool:
    if direction == "long":
        return row.get("ltf_bias") == "bullish"
    if direction == "short":
        return row.get("ltf_bias") == "bearish"
    return False


def _ema_slope_agrees(row: dict[str, Any], direction: str | None) -> bool:
    if direction == "long":
        return _num(row, "ema_slope") > 0
    if direction == "short":
        return _num(row, "ema_slope") < 0
    return False


def _macro_source_is_evidence(row: dict[str, Any]) -> bool:
    return str(row.get("macro_source", "")).lower() in {"evidence", "macro_data"}


def _macro_confidence(row: dict[str, Any], key: str) -> float:
    return _num(row, key, 0.0)


def _macro_gate(row: dict[str, Any], confidence_key: str, minimum: float = 0.50) -> bool:
    return _macro_source_is_evidence(row) and _macro_confidence(row, confidence_key) >= minimum


def detect_r10(row: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    spread_stress = _cal(row, "R10", "spread_stress_min", 90)
    atr_shock = _cal(row, "R10", "atr_percentile_shock_min", 90)
    candle_shock = _cal(row, "R10", "candle_range_atr_shock_min", 2.5)
    adx_chop_max = _cal(row, "R10", "adx_chop_max", 18)
    er_chop_max = _cal(row, "R10", "er_chop_max", 0.20)
    atr_chop_min = _cal(row, "R10", "atr_chop_min", 80)
    conflict = row.get("htf_bias") != row.get("ltf_bias") and row.get("htf_bias") != "neutral" and row.get("ltf_bias") != "neutral"
    clear_edge = bool(row.get("sweep_high_flag") or row.get("sweep_low_flag") or row.get("false_upside_breakout") or row.get("false_downside_breakout"))
    triggers = [
        _condition("Not enough feature data.", _missing_critical(row), reasons, failures),
        _condition(f"Spread percentile is at least {spread_stress:g}.", _num(row, "spread_percentile") >= spread_stress, reasons, failures),
        _condition("Session is rollover.", row.get("session") == "Rollover", reasons, failures),
        _condition("News shock is active.", bool(row.get("news_flag")) and (_num(row, "candle_range_atr") >= candle_shock or _num(row, "spread_percentile") >= spread_stress), reasons, failures),
        _condition(f"ATR percentile is at least {atr_shock:g}.", _num(row, "atr_percentile") >= atr_shock, reasons, failures),
        _condition(f"Candle range is at least {candle_shock:g} ATR.", _num(row, "candle_range_atr") >= candle_shock, reasons, failures),
        _condition("Noisy high-vol chop is active.", _num(row, "adx") <= adx_chop_max and _num(row, "er") <= er_chop_max and _num(row, "atr_percentile") >= atr_chop_min, reasons, failures),
        _condition("HTF/LTF conflict has no clear range edge.", conflict and not clear_edge, reasons, failures),
    ]
    active = any(triggers)
    result = _base_result("R10", sum(triggers), len(triggers), reasons, failures, active)
    result["confidence"] = 1.0 if active else result["confidence"]
    result["reason"] = "Defensive no-trade regime active because execution or market structure is unsafe." if active else result["reason"]
    return result


def detect_r09(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    candle_shock = _cal(row, "R09", "candle_range_atr_shock_min", 2.0)
    atr_shock = _cal(row, "R09", "atr_percentile_shock_min", 85)
    candle_cool = _cal(row, "R09", "candle_range_atr_cool_max", 2.0)
    spread_max = _cal(row, "R09", "max_spread_percentile", 80)
    shock_context = bool(row.get("news_flag")) or _num(row, "candle_range_atr") >= candle_shock or _num(row, "atr_percentile") >= atr_shock
    checks = [
        _condition("News flag is true or shock volatility recently appeared.", shock_context, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g} for post-news testing.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition(f"Candle range has cooled below {candle_cool:g} ATR.", _num(row, "candle_range_atr") < candle_cool, reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R09", sum(checks), len(checks), reasons, failures, shock_context and _confidence_ok(row, "R09", confidence, 0.75) and not hard_block)


def detect_r30(row: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    spread_max = _cal(row, "R30", "max_spread_percentile", 90)
    distortion = bool(row.get("is_month_end") or row.get("is_fixing_window"))
    checks = [
        _condition("Month-end flag is true.", bool(row.get("is_month_end")), reasons, failures),
        _condition("Fixing window flag is true.", bool(row.get("is_fixing_window")), reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g} or tagged for monitoring.", _num(row, "spread_percentile") < spread_max, reasons, failures),
    ]
    result = _base_result("R30", sum(checks), len(checks), reasons, failures, distortion)
    result["confidence"] = 1.0 if distortion else result["confidence"]
    result["reason"] = "Month-end or fixing-window distortion tag is active." if distortion else result["reason"]
    return result


def detect_r23(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_max = _cal(row, "R23", "adx_max", 18)
    er_max = _cal(row, "R23", "er_max", 0.20)
    atr_min = _cal(row, "R23", "atr_percentile_min", 75)
    candle_min = _cal(row, "R23", "candle_range_atr_min", 1.2)
    cross_min = _cal(row, "R23", "ema50_cross_count_min", 4)
    spread_max = _cal(row, "R23", "max_spread_percentile", 90)
    chop_min = _cal(row, "R23", "chop_score_min", 4)
    checks = [
        _condition(f"ADX is {adx_max:g} or lower.", _num(row, "adx") <= adx_max, reasons, failures),
        _condition(f"ER is {er_max:g} or lower.", _num(row, "er") <= er_max, reasons, failures),
        _condition(f"ATR percentile is at least {atr_min:g}.", _num(row, "atr_percentile") >= atr_min, reasons, failures),
        _condition(f"Candle range is at least {candle_min:g} ATR.", _num(row, "candle_range_atr") >= candle_min, reasons, failures),
        _condition(f"EMA50 cross count is at least {cross_min:g}.", _num(row, "ema50_cross_count") >= cross_min, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R23", sum(checks), len(checks), reasons, failures, _num(row, "chop_score") >= chop_min and _confidence_ok(row, "R23", confidence, 0.70) and not hard_block)


def detect_r24(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    atr_max = _cal(row, "R24", "atr_percentile_max", 15)
    bb_max = _cal(row, "R24", "bb_width_percentile_max", 15)
    adx_max = _cal(row, "R24", "adx_max", 15)
    candle_max = _cal(row, "R24", "candle_range_atr_max", 0.70)
    dead_min = _cal(row, "R24", "dead_market_score_min", 3)
    checks = [
        _condition(f"ATR percentile is below {atr_max:g}.", _num(row, "atr_percentile") < atr_max, reasons, failures),
        _condition(f"BB width percentile is below {bb_max:g}.", _num(row, "bb_width_percentile") < bb_max, reasons, failures),
        _condition(f"ADX is below {adx_max:g}.", _num(row, "adx") < adx_max, reasons, failures),
        _condition(f"Candle range is below {candle_max:g} ATR.", _num(row, "candle_range_atr") < candle_max, reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R24", sum(checks), len(checks), reasons, failures, _num(row, "dead_market_score") >= dead_min and _confidence_ok(row, "R24", confidence, 0.75) and not hard_block)


def detect_r25(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    macro_min = _cal(row, "R25", "macro_confidence_min", 0.50)
    adx_min = _cal(row, "R25", "adx_min", 18)
    er_min = _cal(row, "R25", "er_min", 0.20)
    spread_max = _cal(row, "R25", "max_spread_percentile", 70)
    direction = _usd_direction(row, str(row.get("usd_bias", "NEUTRAL")))
    checks = [
        _condition("USD bias is USD_BULLISH.", row.get("usd_bias") == "USD_BULLISH", reasons, failures),
        _condition(f"USD macro evidence confidence is at least {macro_min:g}.", _macro_gate(row, "macro_usd_confidence", macro_min), reasons, failures),
        _condition("Pair direction agrees with USD strength.", direction is not None and _bias_agrees(row, direction), reasons, failures),
        _condition("LTF pullback aligns with USD strength.", direction is not None and _ltf_agrees(row, direction), reasons, failures),
        _condition(f"ADX is at least {adx_min:g}.", _num(row, "adx") >= adx_min, reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
    ]
    if row.get("usd_bias", "NEUTRAL") == "NEUTRAL":
        failures.append("Macro placeholder is neutral, so macro regime not active.")
    if not _macro_source_is_evidence(row):
        failures.append("R25 requires imported or evidence-mode macro data; manual bias alone is not enough.")
    confidence = sum(checks) / len(checks)
    result = _base_result("R25", sum(checks), len(checks), reasons, failures, direction is not None and _macro_gate(row, "macro_usd_confidence", macro_min) and _confidence_ok(row, "R25", confidence, 0.75) and not hard_block)
    result["direction"] = direction or "none"
    return result


def detect_r26(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    macro_min = _cal(row, "R26", "macro_confidence_min", 0.50)
    adx_min = _cal(row, "R26", "adx_min", 18)
    er_min = _cal(row, "R26", "er_min", 0.20)
    spread_max = _cal(row, "R26", "max_spread_percentile", 70)
    direction = _usd_direction(row, str(row.get("usd_bias", "NEUTRAL")))
    checks = [
        _condition("USD bias is USD_BEARISH.", row.get("usd_bias") == "USD_BEARISH", reasons, failures),
        _condition(f"USD macro evidence confidence is at least {macro_min:g}.", _macro_gate(row, "macro_usd_confidence", macro_min), reasons, failures),
        _condition("Pair direction agrees with USD weakness.", direction is not None and _bias_agrees(row, direction), reasons, failures),
        _condition("LTF pullback aligns with USD weakness.", direction is not None and _ltf_agrees(row, direction), reasons, failures),
        _condition(f"ADX is at least {adx_min:g}.", _num(row, "adx") >= adx_min, reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
    ]
    if row.get("usd_bias", "NEUTRAL") == "NEUTRAL":
        failures.append("Macro placeholder is neutral, so macro regime not active.")
    if not _macro_source_is_evidence(row):
        failures.append("R26 requires imported or evidence-mode macro data; manual bias alone is not enough.")
    confidence = sum(checks) / len(checks)
    result = _base_result("R26", sum(checks), len(checks), reasons, failures, direction is not None and row.get("usd_bias") == "USD_BEARISH" and _macro_gate(row, "macro_usd_confidence", macro_min) and _confidence_ok(row, "R26", confidence, 0.75) and not hard_block)
    result["direction"] = direction or "none"
    return result


def detect_r27(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    macro_min = _cal(row, "R27", "macro_confidence_min", 0.50)
    atr_max = _cal(row, "R27", "atr_percentile_max", 90)
    spread_max = _cal(row, "R27", "max_spread_percentile", 70)
    adx_min = _cal(row, "R27", "adx_min", 18)
    er_min = _cal(row, "R27", "er_min", 0.20)
    checks = [
        _condition("Risk sentiment is RISK_ON.", row.get("risk_sentiment") == "RISK_ON", reasons, failures),
        _condition(f"Risk sentiment evidence confidence is at least {macro_min:g}.", _macro_gate(row, "macro_risk_confidence", macro_min), reasons, failures),
        _condition(f"ATR percentile is below {atr_max:g}.", _num(row, "atr_percentile") < atr_max, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("HTF/LTF trend is bullish.", row.get("htf_bias") == "bullish" and row.get("ltf_bias") == "bullish", reasons, failures),
        _condition(f"ADX is at least {adx_min:g}.", _num(row, "adx") >= adx_min, reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
    ]
    if row.get("risk_sentiment", "NEUTRAL") == "NEUTRAL":
        failures.append("Macro placeholder is neutral, so macro regime not active.")
    if not _macro_source_is_evidence(row):
        failures.append("R27 requires imported or evidence-mode macro data; manual risk tone alone is not enough.")
    confidence = sum(checks) / len(checks)
    return _base_result("R27", sum(checks), len(checks), reasons, failures, row.get("risk_sentiment") == "RISK_ON" and _macro_gate(row, "macro_risk_confidence", macro_min) and _confidence_ok(row, "R27", confidence, 0.75) and not hard_block)


def detect_r28(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    macro_min = _cal(row, "R28", "macro_confidence_min", 0.50)
    atr_max = _cal(row, "R28", "atr_percentile_max", 90)
    spread_max = _cal(row, "R28", "max_spread_percentile", 80)
    adx_min = _cal(row, "R28", "adx_min", 18)
    er_min = _cal(row, "R28", "er_min", 0.20)
    checks = [
        _condition("Risk sentiment is RISK_OFF.", row.get("risk_sentiment") == "RISK_OFF", reasons, failures),
        _condition(f"Risk sentiment evidence confidence is at least {macro_min:g}.", _macro_gate(row, "macro_risk_confidence", macro_min), reasons, failures),
        _condition(f"ATR percentile is below {atr_max:g}.", _num(row, "atr_percentile") < atr_max, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("HTF/LTF trend is bearish.", row.get("htf_bias") == "bearish" and row.get("ltf_bias") == "bearish", reasons, failures),
        _condition(f"ADX is at least {adx_min:g}.", _num(row, "adx") >= adx_min, reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
    ]
    if row.get("risk_sentiment", "NEUTRAL") == "NEUTRAL":
        failures.append("Macro placeholder is neutral, so macro regime not active.")
    if not _macro_source_is_evidence(row):
        failures.append("R28 requires imported or evidence-mode macro data; manual risk tone alone is not enough.")
    confidence = sum(checks) / len(checks)
    return _base_result("R28", sum(checks), len(checks), reasons, failures, row.get("risk_sentiment") == "RISK_OFF" and _macro_gate(row, "macro_risk_confidence", macro_min) and _confidence_ok(row, "R28", confidence, 0.75) and not hard_block)


def detect_r29(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    macro_min = _cal(row, "R29", "macro_confidence_min", 0.50)
    adx_min = _cal(row, "R29", "adx_min", 18)
    er_min = _cal(row, "R29", "er_min", 0.25)
    atr_min = _cal(row, "R29", "atr_percentile_min", 25)
    atr_max = _cal(row, "R29", "atr_percentile_max", 90)
    spread_max = _cal(row, "R29", "max_spread_percentile", 70)
    cb = row.get("cb_divergence", "NEUTRAL")
    direction = "long" if cb == "BULLISH_BASE" else "short" if cb == "BEARISH_BASE" else None
    checks = [
        _condition("Central-bank divergence is not neutral.", cb != "NEUTRAL", reasons, failures),
        _condition(f"Central-bank evidence confidence is at least {macro_min:g}.", _macro_gate(row, "macro_cb_confidence", macro_min), reasons, failures),
        _condition("HTF trend agrees with divergence direction.", _bias_agrees(row, direction), reasons, failures),
        _condition(f"ADX is at least {adx_min:g}.", _num(row, "adx") >= adx_min, reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
    ]
    if cb == "NEUTRAL":
        failures.append("Macro placeholder is neutral, so macro regime not active.")
    if not _macro_source_is_evidence(row):
        failures.append("R29 requires imported or evidence-mode central-bank data; manual divergence alone is not enough.")
    confidence = sum(checks) / len(checks)
    result = _base_result("R29", sum(checks), len(checks), reasons, failures, direction is not None and _macro_gate(row, "macro_cb_confidence", macro_min) and _confidence_ok(row, "R29", confidence, 0.75) and not hard_block)
    result["direction"] = direction or "none"
    return result


def detect_r07(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    distance20 = _cal(row, "R07", "distance_ema20_min", 2.5)
    distance50 = _cal(row, "R07", "distance_ema50_min", 2.5)
    adx_min = _cal(row, "R07", "adx_min", 25)
    wick_min = _cal(row, "R07", "upper_wick_min", 0.45)
    atr_min = _cal(row, "R07", "atr_percentile_min", 75)
    spread_max = _cal(row, "R07", "max_spread_percentile", 80)
    extended = _num(row, "distance_from_ema20_atr") >= distance20 or _num(row, "distance_from_ema50_atr") >= distance50
    checks = [
        _condition("HTF bias is bullish.", row.get("htf_bias") == "bullish", reasons, failures),
        _condition(f"Price is extended above EMA20 or EMA50 by at least {min(distance20, distance50):g} ATR.", extended, reasons, failures),
        _condition(f"ADX is at least {adx_min:g}.", _num(row, "adx") >= adx_min, reasons, failures),
        _condition(f"Upper wick ratio is at least {wick_min:g}.", _num(row, "upper_wick_ratio") >= wick_min, reasons, failures),
        _condition(f"ATR percentile is at least {atr_min:g}.", _num(row, "atr_percentile") >= atr_min, reasons, failures),
        _condition("+DI is still above -DI or momentum is slowing.", _num(row, "plus_di") > _num(row, "minus_di") or _num(row, "ema_slope") <= 0, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R07", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R07", confidence, 0.70) and not hard_block)


def detect_r08(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    distance20 = _cal(row, "R08", "distance_ema20_max", -2.5)
    distance50 = _cal(row, "R08", "distance_ema50_max", -2.5)
    adx_min = _cal(row, "R08", "adx_min", 25)
    wick_min = _cal(row, "R08", "lower_wick_min", 0.45)
    atr_min = _cal(row, "R08", "atr_percentile_min", 75)
    spread_max = _cal(row, "R08", "max_spread_percentile", 80)
    extended = _num(row, "distance_from_ema20_atr") <= distance20 or _num(row, "distance_from_ema50_atr") <= distance50
    checks = [
        _condition("HTF bias is bearish.", row.get("htf_bias") == "bearish", reasons, failures),
        _condition(f"Price is extended below EMA20 or EMA50 by at least {abs(max(distance20, distance50)):g} ATR.", extended, reasons, failures),
        _condition(f"ADX is at least {adx_min:g}.", _num(row, "adx") >= adx_min, reasons, failures),
        _condition(f"Lower wick ratio is at least {wick_min:g}.", _num(row, "lower_wick_ratio") >= wick_min, reasons, failures),
        _condition(f"ATR percentile is at least {atr_min:g}.", _num(row, "atr_percentile") >= atr_min, reasons, failures),
        _condition("-DI is still above +DI or momentum is slowing.", _num(row, "minus_di") > _num(row, "plus_di") or _num(row, "ema_slope") >= 0, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R08", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R08", confidence, 0.70) and not hard_block)


def detect_r19(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    hour = _hour(row)
    start_hour = _cal(row, "R19", "start_hour_utc", 7)
    end_hour = _cal(row, "R19", "end_hour_utc", 10)
    atr_min = _cal(row, "R19", "atr_percentile_min", 40)
    candle_min = _cal(row, "R19", "candle_range_atr_min", 1.0)
    spread_max = _cal(row, "R19", "max_spread_percentile", 70)
    opening_break = bool(row.get("orb_up") or row.get("orb_down") or row.get("sweep_high_flag") or row.get("sweep_low_flag"))
    checks = [
        _condition("Session is London.", row.get("session") == "London", reasons, failures),
        _condition(f"Time is between {start_hour:g}:00 and {end_hour:g}:00 UTC.", start_hour <= hour < end_hour, reasons, failures),
        _condition(f"ATR percentile is at least {atr_min:g}.", _num(row, "atr_percentile") >= atr_min, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("Opening range exists.", _opening_range_exists(row), reasons, failures),
        _condition("Price breaks opening range or sweeps liquidity.", opening_break, reasons, failures),
        _condition(f"Candle range is at least {candle_min:g} ATR.", _num(row, "candle_range_atr") >= candle_min, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    london_context = row.get("session") == "London" and start_hour <= hour < end_hour
    return _base_result("R19", sum(checks), len(checks), reasons, failures, london_context and _confidence_ok(row, "R19", confidence, 0.70) and not hard_block)


def detect_r20(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    hour = _hour(row)
    start_hour = _cal(row, "R20", "start_hour_utc", 12)
    end_hour = _cal(row, "R20", "end_hour_utc", 15)
    atr_min = _cal(row, "R20", "atr_percentile_min", 40)
    candle_min = _cal(row, "R20", "candle_range_atr_min", 1.0)
    spread_max = _cal(row, "R20", "max_spread_percentile", 70)
    opening_break = bool(row.get("orb_up") or row.get("orb_down") or row.get("sweep_high_flag") or row.get("sweep_low_flag"))
    checks = [
        _condition("Session is NewYork or Overlap.", row.get("session") in {"NewYork", "Overlap"}, reasons, failures),
        _condition(f"Time is between {start_hour:g}:00 and {end_hour:g}:00 UTC.", start_hour <= hour < end_hour, reasons, failures),
        _condition(f"ATR percentile is at least {atr_min:g}.", _num(row, "atr_percentile") >= atr_min, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("Opening range exists.", _opening_range_exists(row), reasons, failures),
        _condition("Price breaks New York opening range or sweeps liquidity.", opening_break, reasons, failures),
        _condition(f"Candle range is at least {candle_min:g} ATR.", _num(row, "candle_range_atr") >= candle_min, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    ny_context = row.get("session") in {"NewYork", "Overlap"} and start_hour <= hour < end_hour
    return _base_result("R20", sum(checks), len(checks), reasons, failures, ny_context and _confidence_ok(row, "R20", confidence, 0.70) and not hard_block)


def detect_r21(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_min = _cal(row, "R21", "adx_min", 18)
    er_min = _cal(row, "R21", "er_min", 0.25)
    atr_min = _cal(row, "R21", "atr_percentile_min", 25)
    atr_max = _cal(row, "R21", "atr_percentile_max", 90)
    spread_max = _cal(row, "R21", "max_spread_percentile", 70)
    direction = "long" if row.get("htf_bias") == "bullish" and row.get("ltf_bias") == "bullish" else "short" if row.get("htf_bias") == "bearish" and row.get("ltf_bias") == "bearish" else None
    checks = [
        _condition("Session is Overlap.", row.get("session") == "Overlap", reasons, failures),
        _condition("HTF and LTF agree.", direction is not None, reasons, failures),
        _condition(f"ADX is at least {adx_min:g}.", _num(row, "adx") >= adx_min, reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("EMA slope agrees with direction.", _ema_slope_agrees(row, direction), reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    result = _base_result("R21", sum(checks), len(checks), reasons, failures, row.get("session") == "Overlap" and direction is not None and _confidence_ok(row, "R21", confidence, 0.75) and not hard_block)
    result["direction"] = direction or "none"
    return result


def detect_r06(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    atr_max = _cal(row, "R06", "atr_percentile_max", 25)
    bb_max = _cal(row, "R06", "bb_width_percentile_max", 25)
    adx_max = _cal(row, "R06", "adx_max", 18)
    er_max = _cal(row, "R06", "er_max", 0.25)
    candle_max = _cal(row, "R06", "candle_range_atr_max", 1.0)
    spread_max = _cal(row, "R06", "max_spread_percentile", 70)
    compression = _num(row, "atr_percentile") < atr_max or _num(row, "bb_width_percentile") < bb_max or bool(row.get("compression_flag"))
    checks = [
        _condition("ATR or BB width percentile shows compression.", compression, reasons, failures),
        _condition(f"ADX is {adx_max:g} or lower.", _num(row, "adx") <= adx_max, reasons, failures),
        _condition(f"ER is {er_max:g} or lower.", _num(row, "er") <= er_max, reasons, failures),
        _condition(f"Candle range is below {candle_max:g} ATR.", _num(row, "candle_range_atr") < candle_max, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R06", sum(checks), len(checks), reasons, failures, compression and _confidence_ok(row, "R06", confidence, 0.70) and not hard_block)


def detect_r17(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    wick_min = _cal(row, "R17", "upper_wick_min", 0.35)
    spread_max = _cal(row, "R17", "max_spread_percentile", 70)
    atr_max = _cal(row, "R17", "atr_percentile_max", 90)
    false_break = bool(row.get("false_upside_breakout"))
    checks = [
        _condition("False upside breakout flag is true.", false_break, reasons, failures),
        _condition(f"Upper wick ratio is at least {wick_min:g}.", _num(row, "upper_wick_ratio") >= wick_min, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition(f"ATR percentile is below {atr_max:g}.", _num(row, "atr_percentile") < atr_max, reasons, failures),
        _condition("HTF bias is not bullish.", row.get("htf_bias") != "bullish", reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R17", sum(checks), len(checks), reasons, failures, false_break and _confidence_ok(row, "R17", confidence, 0.70) and not hard_block)


def detect_r18(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    wick_min = _cal(row, "R18", "lower_wick_min", 0.35)
    spread_max = _cal(row, "R18", "max_spread_percentile", 70)
    atr_max = _cal(row, "R18", "atr_percentile_max", 90)
    false_break = bool(row.get("false_downside_breakout"))
    checks = [
        _condition("False downside breakout flag is true.", false_break, reasons, failures),
        _condition(f"Lower wick ratio is at least {wick_min:g}.", _num(row, "lower_wick_ratio") >= wick_min, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition(f"ATR percentile is below {atr_max:g}.", _num(row, "atr_percentile") < atr_max, reasons, failures),
        _condition("HTF bias is not bearish.", row.get("htf_bias") != "bearish", reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R18", sum(checks), len(checks), reasons, failures, false_break and _confidence_ok(row, "R18", confidence, 0.70) and not hard_block)


def detect_r15(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    wick_min = _cal(row, "R15", "upper_wick_min", 0.35)
    adx_max = _cal(row, "R15", "adx_max", 25)
    er_max = _cal(row, "R15", "er_max", 0.30)
    spread_max = _cal(row, "R15", "max_spread_percentile", 70)
    checks = [
        _condition("Price is near range high.", bool(row.get("near_range_high")), reasons, failures),
        _condition(f"Upper wick ratio is at least {wick_min:g}.", _num(row, "upper_wick_ratio") >= wick_min, reasons, failures),
        _condition("Close is below previous swing high.", _num(row, "close") < _num(row, "prev_swing_high"), reasons, failures),
        _condition(f"ADX is {adx_max:g} or lower.", _num(row, "adx") <= adx_max, reasons, failures),
        _condition(f"ER is {er_max:g} or lower.", _num(row, "er") <= er_max, reasons, failures),
        _condition("HTF bias is not bullish.", row.get("htf_bias") != "bullish", reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R15", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R15", confidence, 0.75) and not hard_block)


def detect_r16(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    wick_min = _cal(row, "R16", "lower_wick_min", 0.35)
    adx_max = _cal(row, "R16", "adx_max", 25)
    er_max = _cal(row, "R16", "er_max", 0.30)
    spread_max = _cal(row, "R16", "max_spread_percentile", 70)
    checks = [
        _condition("Price is near range low.", bool(row.get("near_range_low")), reasons, failures),
        _condition(f"Lower wick ratio is at least {wick_min:g}.", _num(row, "lower_wick_ratio") >= wick_min, reasons, failures),
        _condition("Close is above previous swing low.", _num(row, "close") > _num(row, "prev_swing_low"), reasons, failures),
        _condition(f"ADX is {adx_max:g} or lower.", _num(row, "adx") <= adx_max, reasons, failures),
        _condition(f"ER is {er_max:g} or lower.", _num(row, "er") <= er_max, reasons, failures),
        _condition("HTF bias is not bearish.", row.get("htf_bias") != "bearish", reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R16", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R16", confidence, 0.75) and not hard_block)


def detect_r04(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_min = _cal(row, "R04", "adx_min", 22)
    er_min = _cal(row, "R04", "er_min", 0.25)
    atr_min = _cal(row, "R04", "atr_percentile_min", 75)
    atr_max = _cal(row, "R04", "atr_percentile_max", 90)
    candle_min = _cal(row, "R04", "candle_range_atr_min", 1.2)
    spread_max = _cal(row, "R04", "max_spread_percentile", 80)
    checks = [
        _condition("HTF bias is bullish.", row.get("htf_bias") == "bullish", reasons, failures),
        _condition("LTF bias is bullish.", row.get("ltf_bias") == "bullish", reasons, failures),
        _condition(f"ADX is at least {adx_min:g}.", _num(row, "adx") >= adx_min, reasons, failures),
        _condition("+DI is above -DI.", _num(row, "plus_di") > _num(row, "minus_di"), reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") < atr_max, reasons, failures),
        _condition(f"Candle range is at least {candle_min:g} ATR.", _num(row, "candle_range_atr") >= candle_min, reasons, failures),
        _condition("Volatility expansion flag is true.", bool(row.get("volatility_expansion_flag")), reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R04", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R04", confidence, 0.75) and not hard_block)


def detect_r05(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_min = _cal(row, "R05", "adx_min", 22)
    er_min = _cal(row, "R05", "er_min", 0.25)
    atr_min = _cal(row, "R05", "atr_percentile_min", 75)
    atr_max = _cal(row, "R05", "atr_percentile_max", 90)
    candle_min = _cal(row, "R05", "candle_range_atr_min", 1.2)
    spread_max = _cal(row, "R05", "max_spread_percentile", 80)
    checks = [
        _condition("HTF bias is bearish.", row.get("htf_bias") == "bearish", reasons, failures),
        _condition("LTF bias is bearish.", row.get("ltf_bias") == "bearish", reasons, failures),
        _condition(f"ADX is at least {adx_min:g}.", _num(row, "adx") >= adx_min, reasons, failures),
        _condition("-DI is above +DI.", _num(row, "minus_di") > _num(row, "plus_di"), reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") < atr_max, reasons, failures),
        _condition(f"Candle range is at least {candle_min:g} ATR.", _num(row, "candle_range_atr") >= candle_min, reasons, failures),
        _condition("Volatility expansion flag is true.", bool(row.get("volatility_expansion_flag")), reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R05", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R05", confidence, 0.75) and not hard_block)


def detect_r13(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    slope_min = _cal(row, "R13", "channel_slope_min", 0.02)
    adx_min = _cal(row, "R13", "adx_min", 15)
    adx_max = _cal(row, "R13", "adx_max", 30)
    er_min = _cal(row, "R13", "er_min", 0.20)
    atr_min = _cal(row, "R13", "atr_percentile_min", 25)
    atr_max = _cal(row, "R13", "atr_percentile_max", 75)
    spread_max = _cal(row, "R13", "max_spread_percentile", 70)
    channel_valid = _has_value(row, "channel_slope") and _num(row, "channel_slope") > slope_min
    checks = [
        _condition("HTF bias is bullish.", row.get("htf_bias") == "bullish", reasons, failures),
        _condition("LTF bias is bullish.", row.get("ltf_bias") == "bullish", reasons, failures),
        _condition(f"Channel slope is above {slope_min:g}.", channel_valid, reasons, failures),
        _condition(f"ADX is inside {adx_min:g}-{adx_max:g}.", adx_min <= _num(row, "adx") <= adx_max, reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition("Close is above EMA50.", _num(row, "close") > _num(row, "ema50"), reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    result = _base_result("R13", sum(checks), len(checks), reasons, failures, channel_valid and _confidence_ok(row, "R13", confidence, 0.75) and not hard_block)
    result["reason"] = "Approximation used: channel calculated using linear regression over 50 bars."
    return result


def detect_r14(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    slope_max = _cal(row, "R14", "channel_slope_max", -0.02)
    adx_min = _cal(row, "R14", "adx_min", 15)
    adx_max = _cal(row, "R14", "adx_max", 30)
    er_min = _cal(row, "R14", "er_min", 0.20)
    atr_min = _cal(row, "R14", "atr_percentile_min", 25)
    atr_max = _cal(row, "R14", "atr_percentile_max", 75)
    spread_max = _cal(row, "R14", "max_spread_percentile", 70)
    channel_valid = _has_value(row, "channel_slope") and _num(row, "channel_slope") < slope_max
    checks = [
        _condition("HTF bias is bearish.", row.get("htf_bias") == "bearish", reasons, failures),
        _condition("LTF bias is bearish.", row.get("ltf_bias") == "bearish", reasons, failures),
        _condition(f"Channel slope is below {slope_max:g}.", channel_valid, reasons, failures),
        _condition(f"ADX is inside {adx_min:g}-{adx_max:g}.", adx_min <= _num(row, "adx") <= adx_max, reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition("Close is below EMA50.", _num(row, "close") < _num(row, "ema50"), reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    result = _base_result("R14", sum(checks), len(checks), reasons, failures, channel_valid and _confidence_ok(row, "R14", confidence, 0.75) and not hard_block)
    result["reason"] = "Approximation used: channel calculated using linear regression over 50 bars."
    return result


def detect_r11(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_min = _cal(row, "R11", "adx_min", 14)
    adx_max = _cal(row, "R11", "adx_max", 25)
    er_min = _cal(row, "R11", "er_min", 0.20)
    atr_min = _cal(row, "R11", "atr_percentile_min", 15)
    atr_max = _cal(row, "R11", "atr_percentile_max", 35)
    candle_max = _cal(row, "R11", "candle_range_atr_max", 1.2)
    spread_max = _cal(row, "R11", "max_spread_percentile", 70)
    distance_max = _cal(row, "R11", "max_distance_ema20_atr", 2.0)
    low_vol_drift = atr_min <= _num(row, "atr_percentile") <= atr_max and adx_min <= _num(row, "adx") <= adx_max and _num(row, "er") >= er_min
    checks = [
        _condition("HTF bias is bullish.", row.get("htf_bias") == "bullish", reasons, failures),
        _condition("LTF bias is bullish.", row.get("ltf_bias") == "bullish", reasons, failures),
        _condition(f"ADX is inside {adx_min:g}-{adx_max:g}.", adx_min <= _num(row, "adx") <= adx_max, reasons, failures),
        _condition("+DI is above -DI.", _num(row, "plus_di") > _num(row, "minus_di"), reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition("EMA slope is positive.", _num(row, "ema_slope") > 0, reasons, failures),
        _condition(f"Candle range is below {candle_max:g} ATR.", _num(row, "candle_range_atr") < candle_max, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition(f"Price is less than {distance_max:g} ATR above EMA20.", _num(row, "distance_from_ema20_atr") < distance_max, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R11", sum(checks), len(checks), reasons, failures, low_vol_drift and _confidence_ok(row, "R11", confidence, 0.75) and not hard_block)


def detect_r12(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_min = _cal(row, "R12", "adx_min", 14)
    adx_max = _cal(row, "R12", "adx_max", 25)
    er_min = _cal(row, "R12", "er_min", 0.20)
    atr_min = _cal(row, "R12", "atr_percentile_min", 15)
    atr_max = _cal(row, "R12", "atr_percentile_max", 35)
    candle_max = _cal(row, "R12", "candle_range_atr_max", 1.2)
    spread_max = _cal(row, "R12", "max_spread_percentile", 70)
    distance_max = _cal(row, "R12", "max_distance_ema20_atr", 2.0)
    low_vol_drift = atr_min <= _num(row, "atr_percentile") <= atr_max and adx_min <= _num(row, "adx") <= adx_max and _num(row, "er") >= er_min
    checks = [
        _condition("HTF bias is bearish.", row.get("htf_bias") == "bearish", reasons, failures),
        _condition("LTF bias is bearish.", row.get("ltf_bias") == "bearish", reasons, failures),
        _condition(f"ADX is inside {adx_min:g}-{adx_max:g}.", adx_min <= _num(row, "adx") <= adx_max, reasons, failures),
        _condition("-DI is above +DI.", _num(row, "minus_di") > _num(row, "plus_di"), reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition("EMA slope is negative.", _num(row, "ema_slope") < 0, reasons, failures),
        _condition(f"Candle range is below {candle_max:g} ATR.", _num(row, "candle_range_atr") < candle_max, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition(f"Price is less than {distance_max:g} ATR below EMA20.", _num(row, "distance_from_ema20_atr") > -distance_max, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R12", sum(checks), len(checks), reasons, failures, low_vol_drift and _confidence_ok(row, "R12", confidence, 0.75) and not hard_block)


def detect_r01(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_min = _cal(row, "R01", "adx_min", 18)
    adx_max = _cal(row, "R01", "adx_max", 35)
    er_min = _cal(row, "R01", "er_min", 0.25)
    atr_min = _cal(row, "R01", "atr_percentile_min", 25)
    atr_max = _cal(row, "R01", "atr_percentile_max", 80)
    spread_max = _cal(row, "R01", "max_spread_percentile", 70)
    distance_max = _cal(row, "R01", "max_distance_ema20_atr", 2.5)
    checks = [
        _condition("HTF bias is bullish.", row.get("htf_bias") == "bullish", reasons, failures),
        _condition("LTF bias is bullish.", row.get("ltf_bias") == "bullish", reasons, failures),
        _condition(f"ADX is inside {adx_min:g}-{adx_max:g}.", adx_min <= _num(row, "adx") <= adx_max, reasons, failures),
        _condition("+DI is above -DI.", _num(row, "plus_di") > _num(row, "minus_di"), reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition("EMA slope is positive.", _num(row, "ema_slope") > 0, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition(f"Price is not more than {distance_max:g} ATR above EMA20.", _num(row, "distance_from_ema20_atr") < distance_max, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R01", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R01", confidence, 0.75) and not hard_block)


def detect_r02(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_min = _cal(row, "R02", "adx_min", 18)
    adx_max = _cal(row, "R02", "adx_max", 35)
    er_min = _cal(row, "R02", "er_min", 0.25)
    atr_min = _cal(row, "R02", "atr_percentile_min", 25)
    atr_max = _cal(row, "R02", "atr_percentile_max", 80)
    spread_max = _cal(row, "R02", "max_spread_percentile", 70)
    distance_max = _cal(row, "R02", "max_distance_ema20_atr", 2.5)
    checks = [
        _condition("HTF bias is bearish.", row.get("htf_bias") == "bearish", reasons, failures),
        _condition("LTF bias is bearish.", row.get("ltf_bias") == "bearish", reasons, failures),
        _condition(f"ADX is inside {adx_min:g}-{adx_max:g}.", adx_min <= _num(row, "adx") <= adx_max, reasons, failures),
        _condition("-DI is above +DI.", _num(row, "minus_di") > _num(row, "plus_di"), reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition("EMA slope is negative.", _num(row, "ema_slope") < 0, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition(f"Price is not more than {distance_max:g} ATR below EMA20.", _num(row, "distance_from_ema20_atr") > -distance_max, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R02", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R02", confidence, 0.75) and not hard_block)


def detect_r03(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_max = _cal(row, "R03", "adx_max", 18)
    er_max = _cal(row, "R03", "er_max", 0.25)
    atr_min = _cal(row, "R03", "atr_percentile_min", 25)
    atr_max = _cal(row, "R03", "atr_percentile_max", 75)
    spread_max = _cal(row, "R03", "max_spread_percentile", 70)
    cross_min = _cal(row, "R03", "ema50_cross_count_min", 3)
    checks = [
        _condition(f"ADX is {adx_max:g} or lower.", _num(row, "adx") <= adx_max, reasons, failures),
        _condition(f"ER is {er_max:g} or lower.", _num(row, "er") <= er_max, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition(f"Price crossed EMA50 at least {cross_min:g} times in last 30 bars.", _num(row, "ema50_cross_count_30") >= cross_min, reasons, failures),
        _condition("Previous swing high exists.", _has_value(row, "prev_swing_high"), reasons, failures),
        _condition("Previous swing low exists.", _has_value(row, "prev_swing_low"), reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    sweep = bool(row.get("sweep_high_flag") or row.get("sweep_low_flag"))
    if sweep:
        reasons.append("Liquidity sweep path is active.")
    confidence = max(sum(checks) / len(checks), 1.0 if sweep else 0.0)
    return _base_result("R03", sum(checks), len(checks), reasons, failures, (_confidence_ok(row, "R03", confidence, 0.70) or sweep) and not hard_block) | {"confidence": round(confidence, 4)}


def detect_r22(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_max = _cal(row, "R22", "adx_max", 18)
    er_max = _cal(row, "R22", "er_max", 0.25)
    atr_max = _cal(row, "R22", "atr_percentile_max", 75)
    spread_max = _cal(row, "R22", "max_spread_percentile", 70)
    checks = [
        _condition("Session is Asia.", row.get("session") == "Asia", reasons, failures),
        _condition(f"ADX is {adx_max:g} or lower.", _num(row, "adx") <= adx_max, reasons, failures),
        _condition(f"ER is {er_max:g} or lower.", _num(row, "er") <= er_max, reasons, failures),
        _condition(f"ATR percentile is {atr_max:g} or lower.", _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("Previous swing high exists.", _has_value(row, "prev_swing_high"), reasons, failures),
        _condition("Previous swing low exists.", _has_value(row, "prev_swing_low"), reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R22", sum(checks), len(checks), reasons, failures, bool(row.get("asia_range")) and _confidence_ok(row, "R22", confidence, 0.75) and not hard_block)


def detect_r40(row: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    checks = [
        _condition("Missing OHLC data flag is true.", _num(row, "missing_ohlc") == 1, reasons, failures),
        _condition("Invalid OHLC flag is true.", _num(row, "invalid_ohlc") == 1, reasons, failures),
        _condition("Zero-range candle flag is true.", _num(row, "zero_range") == 1, reasons, failures),
        _condition("Duplicate timestamp flag is true.", _num(row, "duplicate_timestamp") == 1, reasons, failures),
        _condition("Spread missing flag is true.", _num(row, "spread_missing") == 1, reasons, failures),
        _condition("HTF unavailable flag is true.", _num(row, "htf_unavailable") == 1, reasons, failures),
        _condition("Warmup/not enough bars flag is true.", _num(row, "feature_nan_required") == 1 or _missing_critical(row), reasons, failures),
    ]
    active = any(checks) or _num(row, "data_quality_flag") == 1
    result = _base_result("R40", sum(checks), len(checks), reasons, failures, active)
    result["confidence"] = 1.0 if active else result["confidence"]
    category = (row.get("data_quality_category") or "R40-BAD-DATA") if active else "OK"
    if active and category == "OK":
        category = "R40-BAD-DATA"
    result["regime_subtype"] = category
    result["data_quality_category"] = category
    result["data_quality_warmup_reasons"] = row.get("data_quality_warmup_reasons") or ""
    result["data_quality_bad_data_reasons"] = row.get("data_quality_bad_data_reasons") or ""
    if category == "R40-WARMUP":
        result["reason"] = f"Warmup only: {row.get('data_quality_warmup_reasons') or 'not enough bars for required indicators.'}"
    elif row.get("data_quality_reasons"):
        result["reason"] = f"Manual review required: {row.get('data_quality_reasons')}"
    elif active:
        result["reason"] = "Manual review required because data quality or feature completeness failed."
    return result


def detect_r39(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    gap_min = _cal(row, "R39", "gap_atr_min", 0.75)
    monday_gap_min = _cal(row, "R39", "monday_gap_atr_min", 0.50)
    spread_max = _cal(row, "R39", "max_spread_percentile", 90)
    monday_early_gap = _dayofweek(row) == 0 and _hour(row) < 3 and _num(row, "gap_atr") >= monday_gap_min
    checks = [
        _condition(f"Gap size is at least {gap_min:g} ATR.", _num(row, "gap_atr") >= gap_min, reasons, failures),
        _condition("Monday early-session gap context is present.", monday_early_gap, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g} for monitoring.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    active = (_num(row, "gap_flag") == 1 or monday_early_gap) and not hard_block
    result = _base_result("R39", sum(checks), len(checks), reasons, failures, active)
    result["confidence"] = 1.0 if active else result["confidence"]
    return result


def detect_r38(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    spread_stress_min = _cal(row, "R38", "spread_stress_min", 90)
    spread_max = _cal(row, "R38", "spread_normalized_max", 70)
    candle_max = _cal(row, "R38", "candle_range_atr_max", 2.0)
    wait_bars = _cal(row, "R38", "post_stress_wait_bars", 3)
    checks = [
        _condition(f"Spread was stressed above {spread_stress_min:g} in the last 10 bars.", _num(row, "spread_was_stressed") == 1, reasons, failures),
        _condition(f"Spread percentile is now below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition(f"Candle range is below {candle_max:g} ATR.", _num(row, "candle_range_atr") < candle_max, reasons, failures),
        _condition(f"At least {wait_bars:g} bars passed after stress.", _num(row, "spread_stress_bars_ago", wait_bars) >= wait_bars, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R38", sum(checks), len(checks), reasons, failures, _num(row, "post_stress_normalization") == 1 and _confidence_ok(row, "R38", confidence, 0.75) and not hard_block)


def detect_r32(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_min = _cal(row, "R32", "adx_min", 18)
    adx_slope_max = _cal(row, "R32", "adx_slope_max", 0)
    er_slope_max = _cal(row, "R32", "er_slope_max", 0)
    atr_min = _cal(row, "R32", "atr_percentile_min", 25)
    atr_max = _cal(row, "R32", "atr_percentile_max", 90)
    spread_max = _cal(row, "R32", "max_spread_percentile", 70)
    checks = [
        _condition("HTF bias is bullish.", row.get("htf_bias") == "bullish", reasons, failures),
        _condition("LTF bias is bullish or neutral.", row.get("ltf_bias") in {"bullish", "neutral"}, reasons, failures),
        _condition(f"ADX is at least {adx_min:g}.", _num(row, "adx") >= adx_min, reasons, failures),
        _condition(f"ADX slope is below {adx_slope_max:g}.", _num(row, "adx_slope") < adx_slope_max, reasons, failures),
        _condition(f"ER slope is below {er_slope_max:g}.", _num(row, "er_slope") < er_slope_max, reasons, failures),
        _condition("Close is below EMA20.", _num(row, "close") < _num(row, "ema20"), reasons, failures),
        _condition("+DI is above -DI.", _num(row, "plus_di") > _num(row, "minus_di"), reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R32", sum(checks), len(checks), reasons, failures, _num(row, "bull_pullback_failure") == 1 and _confidence_ok(row, "R32", confidence, 0.75) and not hard_block)


def detect_r33(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_min = _cal(row, "R33", "adx_min", 18)
    adx_slope_max = _cal(row, "R33", "adx_slope_max", 0)
    er_slope_max = _cal(row, "R33", "er_slope_max", 0)
    atr_min = _cal(row, "R33", "atr_percentile_min", 25)
    atr_max = _cal(row, "R33", "atr_percentile_max", 90)
    spread_max = _cal(row, "R33", "max_spread_percentile", 70)
    checks = [
        _condition("HTF bias is bearish.", row.get("htf_bias") == "bearish", reasons, failures),
        _condition("LTF bias is bearish or neutral.", row.get("ltf_bias") in {"bearish", "neutral"}, reasons, failures),
        _condition(f"ADX is at least {adx_min:g}.", _num(row, "adx") >= adx_min, reasons, failures),
        _condition(f"ADX slope is below {adx_slope_max:g}.", _num(row, "adx_slope") < adx_slope_max, reasons, failures),
        _condition(f"ER slope is below {er_slope_max:g}.", _num(row, "er_slope") < er_slope_max, reasons, failures),
        _condition("Close is above EMA20.", _num(row, "close") > _num(row, "ema20"), reasons, failures),
        _condition("-DI is above +DI.", _num(row, "minus_di") > _num(row, "plus_di"), reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R33", sum(checks), len(checks), reasons, failures, _num(row, "bear_pullback_failure") == 1 and _confidence_ok(row, "R33", confidence, 0.75) and not hard_block)


def detect_r34(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    wick_min = _cal(row, "R34", "lower_wick_min", 0.40)
    atr_min = _cal(row, "R34", "atr_percentile_min", 25)
    atr_max = _cal(row, "R34", "atr_percentile_max", 90)
    spread_max = _cal(row, "R34", "max_spread_percentile", 70)
    checks = [
        _condition("HTF bias is bullish.", row.get("htf_bias") == "bullish", reasons, failures),
        _condition("LTF bias is bullish or neutral.", row.get("ltf_bias") in {"bullish", "neutral"}, reasons, failures),
        _condition("Sweep-low flag is true.", bool(row.get("sweep_low_flag")), reasons, failures),
        _condition("Close reclaimed previous swing low.", _num(row, "close") > _num(row, "prev_swing_low"), reasons, failures),
        _condition(f"Lower wick ratio is at least {wick_min:g}.", _num(row, "lower_wick_ratio") >= wick_min, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R34", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R34", confidence, 0.75) and not hard_block)


def detect_r35(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    wick_min = _cal(row, "R35", "upper_wick_min", 0.40)
    atr_min = _cal(row, "R35", "atr_percentile_min", 25)
    atr_max = _cal(row, "R35", "atr_percentile_max", 90)
    spread_max = _cal(row, "R35", "max_spread_percentile", 70)
    checks = [
        _condition("HTF bias is bearish.", row.get("htf_bias") == "bearish", reasons, failures),
        _condition("LTF bias is bearish or neutral.", row.get("ltf_bias") in {"bearish", "neutral"}, reasons, failures),
        _condition("Sweep-high flag is true.", bool(row.get("sweep_high_flag")), reasons, failures),
        _condition("Close rejected previous swing high.", _num(row, "close") < _num(row, "prev_swing_high"), reasons, failures),
        _condition(f"Upper wick ratio is at least {wick_min:g}.", _num(row, "upper_wick_ratio") >= wick_min, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R35", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R35", confidence, 0.75) and not hard_block)


def detect_r36(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_max = _cal(row, "R36", "adx_max", 18)
    er_max = _cal(row, "R36", "er_max", 0.25)
    atr_min = _cal(row, "R36", "atr_percentile_min", 25)
    atr_max = _cal(row, "R36", "atr_percentile_max", 75)
    spread_max = _cal(row, "R36", "max_spread_percentile", 70)
    vwap_distance = _cal(row, "R36", "vwap_distance_atr_min", 1.5)
    checks = [
        _condition(f"ADX is {adx_max:g} or lower.", _num(row, "adx") <= adx_max, reasons, failures),
        _condition(f"ER is {er_max:g} or lower.", _num(row, "er") <= er_max, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("Session VWAP exists.", _has_value(row, "session_vwap"), reasons, failures),
        _condition(f"Price is at least {vwap_distance:g} ATR from VWAP.", abs(_num(row, "distance_from_vwap_atr")) >= vwap_distance, reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R36", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R36", confidence, 0.75) and not hard_block)


def detect_r37(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_min = _cal(row, "R37", "adx_min", 15)
    adx_max = _cal(row, "R37", "adx_max", 25)
    er_max = _cal(row, "R37", "er_max", 0.30)
    cross_min = _cal(row, "R37", "ema50_cross_count_min", 3)
    spread_max = _cal(row, "R37", "max_spread_percentile", 70)
    conflict = row.get("htf_bias") != row.get("ltf_bias") and row.get("htf_bias") != "neutral" and row.get("ltf_bias") != "neutral"
    checks = [
        _condition("HTF and LTF bias conflict.", conflict, reasons, failures),
        _condition(f"ADX is inside {adx_min:g}-{adx_max:g}.", adx_min <= _num(row, "adx") <= adx_max, reasons, failures),
        _condition(f"ER is {er_max:g} or lower.", _num(row, "er") <= er_max, reasons, failures),
        _condition(f"EMA50 cross count is at least {cross_min:g}.", _num(row, "ema50_cross_count") >= cross_min, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R37", sum(checks), len(checks), reasons, failures, conflict and _confidence_ok(row, "R37", confidence, 0.75) and not hard_block)


def detect_r31(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_min = _cal(row, "R31", "adx_min", 15)
    adx_max = _cal(row, "R31", "adx_max", 22)
    er_min = _cal(row, "R31", "er_min", 0.18)
    er_max = _cal(row, "R31", "er_max", 0.28)
    cross_min = _cal(row, "R31", "ema50_cross_count_min", 3)
    spread_max = _cal(row, "R31", "max_spread_percentile", 90)
    conflict = row.get("htf_bias") != row.get("ltf_bias") and row.get("htf_bias") != "neutral" and row.get("ltf_bias") != "neutral"
    checks = [
        _condition("HTF and LTF bias conflict.", conflict, reasons, failures),
        _condition(f"ADX is in uncertainty zone {adx_min:g}-{adx_max:g}.", adx_min <= _num(row, "adx") <= adx_max, reasons, failures),
        _condition(f"ER is in uncertainty zone {er_min:g}-{er_max:g}.", er_min <= _num(row, "er") <= er_max, reasons, failures),
        _condition(f"EMA50 cross count is at least {cross_min:g}.", _num(row, "ema50_cross_count") >= cross_min, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R31", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R31", confidence, 0.50) and not hard_block)


def detect_r41(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    spread_max = _cal(row, "R41", "max_spread_percentile", 70)
    atr_min = _cal(row, "R41", "atr_percentile_min", 25)
    atr_max = _cal(row, "R41", "atr_percentile_max", 90)
    asia_low_reclaim = _has_value(row, "asia_low") and _num(row, "low") < _num(row, "asia_low") and _num(row, "close") > _num(row, "asia_low")
    asia_high_reject = _has_value(row, "asia_high") and _num(row, "high") > _num(row, "asia_high") and _num(row, "close") < _num(row, "asia_high")
    checks = [
        _condition("Session is London or Overlap.", row.get("session") in {"London", "Overlap"}, reasons, failures),
        _condition("Asia high and low exist.", _has_value(row, "asia_high") and _has_value(row, "asia_low"), reasons, failures),
        _condition("Asia low reclaim or Asia high rejection is active.", asia_low_reclaim or asia_high_reject, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    result = _base_result("R41", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R41", confidence, 0.75) and not hard_block)
    result["direction"] = "long" if asia_low_reclaim else "short" if asia_high_reject else "both"
    return result


def detect_r42(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    wick_min = _cal(row, "R42", "wick_min", 0.35)
    adx_max = _cal(row, "R42", "adx_max", 25)
    er_max = _cal(row, "R42", "er_max", 0.30)
    spread_max = _cal(row, "R42", "max_spread_percentile", 70)
    upside_fakeout = _opening_range_exists(row) and _num(row, "high") > _num(row, "opening_range_high") and _num(row, "close") < _num(row, "opening_range_high") and _num(row, "upper_wick_ratio") >= wick_min
    downside_fakeout = _opening_range_exists(row) and _num(row, "low") < _num(row, "opening_range_low") and _num(row, "close") > _num(row, "opening_range_low") and _num(row, "lower_wick_ratio") >= wick_min
    checks = [
        _condition("Session is London, NewYork, or Overlap.", row.get("session") in {"London", "NewYork", "Overlap"}, reasons, failures),
        _condition("Opening range exists.", _opening_range_exists(row), reasons, failures),
        _condition("Opening range fakeout is active.", upside_fakeout or downside_fakeout, reasons, failures),
        _condition(f"ADX is {adx_max:g} or lower.", _num(row, "adx") <= adx_max, reasons, failures),
        _condition(f"ER is {er_max:g} or lower.", _num(row, "er") <= er_max, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    result = _base_result("R42", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R42", confidence, 0.75) and not hard_block)
    result["direction"] = "short" if upside_fakeout else "long" if downside_fakeout else "both"
    return result


def detect_r43(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    wick_min = _cal(row, "R43", "wick_min", 0.35)
    adx_max = _cal(row, "R43", "adx_max", 25)
    er_max = _cal(row, "R43", "er_max", 0.30)
    spread_max = _cal(row, "R43", "max_spread_percentile", 70)
    pdh_reject = _has_value(row, "prev_day_high") and _num(row, "high") >= _num(row, "prev_day_high") and _num(row, "close") < _num(row, "prev_day_high") and _num(row, "upper_wick_ratio") >= wick_min
    pdl_reclaim = _has_value(row, "prev_day_low") and _num(row, "low") <= _num(row, "prev_day_low") and _num(row, "close") > _num(row, "prev_day_low") and _num(row, "lower_wick_ratio") >= wick_min
    checks = [
        _condition("Previous-day high or low exists.", _has_value(row, "prev_day_high") or _has_value(row, "prev_day_low"), reasons, failures),
        _condition("Previous-day level rejection is active.", pdh_reject or pdl_reclaim, reasons, failures),
        _condition(f"ADX is {adx_max:g} or lower.", _num(row, "adx") <= adx_max, reasons, failures),
        _condition(f"ER is {er_max:g} or lower.", _num(row, "er") <= er_max, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    result = _base_result("R43", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R43", confidence, 0.75) and not hard_block)
    result["direction"] = "short" if pdh_reject else "long" if pdl_reclaim else "both"
    return result


def detect_r44(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_min = _cal(row, "R44", "adx_min", 25)
    er_min = _cal(row, "R44", "er_min", 0.30)
    atr_min = _cal(row, "R44", "atr_percentile_min", 50)
    atr_max = _cal(row, "R44", "atr_percentile_max", 90)
    candle_min = _cal(row, "R44", "candle_range_atr_min", 1.0)
    spread_max = _cal(row, "R44", "max_spread_percentile", 70)
    aligned = row.get("htf_bias") == row.get("ltf_bias") and row.get("htf_bias") in {"bullish", "bearish"}
    direction = "long" if row.get("htf_bias") == "bullish" else "short" if row.get("htf_bias") == "bearish" else None
    checks = [
        _condition("HTF and LTF agree directionally.", aligned, reasons, failures),
        _condition(f"ADX is at least {adx_min:g}.", _num(row, "adx") >= adx_min, reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition(f"Candle range is at least {candle_min:g} ATR.", _num(row, "candle_range_atr") >= candle_min, reasons, failures),
        _condition("EMA slope agrees with trend direction.", _ema_slope_agrees(row, direction), reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    result = _base_result("R44", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R44", confidence, 0.75) and not hard_block)
    result["direction"] = direction or "both"
    return result


def detect_r45(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    atr_min = _cal(row, "R45", "atr_percentile_min", 80)
    candle_min = _cal(row, "R45", "candle_range_atr_min", 1.6)
    distance_min = _cal(row, "R45", "distance_ema20_atr_min", 2.5)
    wick_min = _cal(row, "R45", "wick_min", 0.45)
    spread_max = _cal(row, "R45", "max_spread_percentile", 90)
    high_climax = _num(row, "distance_from_ema20_atr") >= distance_min and _num(row, "upper_wick_ratio") >= wick_min
    low_climax = _num(row, "distance_from_ema20_atr") <= -distance_min and _num(row, "lower_wick_ratio") >= wick_min
    checks = [
        _condition(f"ATR percentile is at least {atr_min:g}.", _num(row, "atr_percentile") >= atr_min, reasons, failures),
        _condition(f"Candle range is at least {candle_min:g} ATR.", _num(row, "candle_range_atr") >= candle_min, reasons, failures),
        _condition("Price is extended from EMA20 with wick rejection.", high_climax or low_climax, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    result = _base_result("R45", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R45", confidence, 0.75) and not hard_block)
    result["direction"] = "short" if high_climax else "long" if low_climax else "both"
    return result


def detect_r46(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_min = _cal(row, "R46", "adx_min", 18)
    er_min = _cal(row, "R46", "er_min", 0.25)
    vwap_min = _cal(row, "R46", "vwap_distance_min", 0.20)
    vwap_max = _cal(row, "R46", "vwap_distance_max", 1.50)
    spread_max = _cal(row, "R46", "max_spread_percentile", 70)
    aligned = row.get("htf_bias") == row.get("ltf_bias") and row.get("htf_bias") in {"bullish", "bearish"}
    accepted_long = aligned and row.get("htf_bias") == "bullish" and _num(row, "close") > _num(row, "session_vwap") and vwap_min <= _num(row, "distance_from_vwap_atr") <= vwap_max
    accepted_short = aligned and row.get("htf_bias") == "bearish" and _num(row, "close") < _num(row, "session_vwap") and -vwap_max <= _num(row, "distance_from_vwap_atr") <= -vwap_min
    checks = [
        _condition("Session VWAP exists.", _has_value(row, "session_vwap"), reasons, failures),
        _condition("Price accepted trend side of VWAP.", accepted_long or accepted_short, reasons, failures),
        _condition(f"ADX is at least {adx_min:g}.", _num(row, "adx") >= adx_min, reasons, failures),
        _condition(f"ER is at least {er_min:g}.", _num(row, "er") >= er_min, reasons, failures),
        _condition("HTF and LTF agree.", aligned, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    result = _base_result("R46", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R46", confidence, 0.75) and not hard_block)
    result["direction"] = "long" if accepted_long else "short" if accepted_short else "both"
    return result


def detect_r47(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    bb_max = _cal(row, "R47", "bb_width_percentile_max", 50)
    atr_min = _cal(row, "R47", "atr_percentile_min", 20)
    atr_max = _cal(row, "R47", "atr_percentile_max", 75)
    candle_min = _cal(row, "R47", "candle_range_atr_min", 1.0)
    spread_max = _cal(row, "R47", "max_spread_percentile", 70)
    breaks_high = _has_value(row, "close") and _has_value(row, "prev_swing_high") and _num(row, "close") > _num(row, "prev_swing_high")
    breaks_low = _has_value(row, "close") and _has_value(row, "prev_swing_low") and _num(row, "close") < _num(row, "prev_swing_low")
    checks = [
        _condition(f"BB width percentile is below {bb_max:g} or compression flag is active.", _num(row, "bb_width_percentile") <= bb_max or bool(row.get("compression_flag")), reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition(f"Candle range is at least {candle_min:g} ATR.", _num(row, "candle_range_atr") >= candle_min, reasons, failures),
        _condition("Price breaks previous swing high or low.", breaks_high or breaks_low, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    result = _base_result("R47", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R47", confidence, 0.75) and not hard_block)
    result["direction"] = "long" if breaks_high else "short" if breaks_low else "both"
    return result


def detect_r48(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    adx_max = _cal(row, "R48", "adx_max", 18)
    er_max = _cal(row, "R48", "er_max", 0.25)
    atr_min = _cal(row, "R48", "atr_percentile_min", 25)
    atr_max = _cal(row, "R48", "atr_percentile_max", 75)
    distance_min = _cal(row, "R48", "midpoint_distance_atr_min", 0.75)
    wick_min = _cal(row, "R48", "wick_min", 0.35)
    spread_max = _cal(row, "R48", "max_spread_percentile", 70)
    midpoint = _num(row, "range_midpoint")
    midpoint_distance = abs(_num(row, "close") - midpoint) / max(_num(row, "atr"), 1e-12) if _has_value(row, "range_midpoint") else 0.0
    high_reject = _num(row, "close") > midpoint and _num(row, "upper_wick_ratio") >= wick_min
    low_reclaim = _num(row, "close") < midpoint and _num(row, "lower_wick_ratio") >= wick_min
    checks = [
        _condition(f"ADX is {adx_max:g} or lower.", _num(row, "adx") <= adx_max, reasons, failures),
        _condition(f"ER is {er_max:g} or lower.", _num(row, "er") <= er_max, reasons, failures),
        _condition(f"ATR percentile is inside {atr_min:g}-{atr_max:g}.", atr_min <= _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition("Range midpoint exists.", _has_value(row, "range_midpoint"), reasons, failures),
        _condition(f"Price is at least {distance_min:g} ATR from midpoint.", midpoint_distance >= distance_min, reasons, failures),
        _condition("Wick rejection points back toward midpoint.", high_reject or low_reclaim, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    result = _base_result("R48", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R48", confidence, 0.75) and not hard_block)
    result["direction"] = "short" if high_reject else "long" if low_reclaim else "both"
    return result


def detect_r49(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    wick_min = _cal(row, "R49", "wick_min", 0.35)
    spread_max = _cal(row, "R49", "max_spread_percentile", 70)
    asia_high_fail = _has_value(row, "asia_high") and _num(row, "high") > _num(row, "asia_high") and _num(row, "close") < _num(row, "asia_high") and _num(row, "upper_wick_ratio") >= wick_min
    asia_low_fail = _has_value(row, "asia_low") and _num(row, "low") < _num(row, "asia_low") and _num(row, "close") > _num(row, "asia_low") and _num(row, "lower_wick_ratio") >= wick_min
    or_high_fail = _opening_range_exists(row) and _num(row, "high") > _num(row, "opening_range_high") and _num(row, "close") < _num(row, "opening_range_high") and _num(row, "upper_wick_ratio") >= wick_min
    or_low_fail = _opening_range_exists(row) and _num(row, "low") < _num(row, "opening_range_low") and _num(row, "close") > _num(row, "opening_range_low") and _num(row, "lower_wick_ratio") >= wick_min
    context = _num(row, "mtf_conflict_score") >= 1 or _num(row, "er") <= 0.30
    high_fail = asia_high_fail or or_high_fail
    low_fail = asia_low_fail or or_low_fail
    checks = [
        _condition("Session is London, NewYork, or Overlap.", row.get("session") in {"London", "NewYork", "Overlap"}, reasons, failures),
        _condition("Asia or opening range level exists.", _has_value(row, "asia_high") or _has_value(row, "asia_low") or _opening_range_exists(row), reasons, failures),
        _condition("Cross-session breakout failure is active.", high_fail or low_fail, reasons, failures),
        _condition("MTF conflict or low ER context is present.", context, reasons, failures),
        _condition(f"Spread percentile is below {spread_max:g}.", _num(row, "spread_percentile") < spread_max, reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    result = _base_result("R49", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R49", confidence, 0.75) and not hard_block)
    result["direction"] = "short" if high_fail else "long" if low_fail else "both"
    return result


def detect_r50(row: dict[str, Any], hard_block: bool) -> dict[str, Any]:
    reasons: list[str] = []
    failures: list[str] = []
    spread_min = _cal(row, "R50", "spread_percentile_min", 70)
    spread_max = _cal(row, "R50", "spread_percentile_max", 90)
    candle_max = _cal(row, "R50", "candle_range_atr_max", 1.0)
    atr_max = _cal(row, "R50", "atr_percentile_max", 50)
    spreadp = _num(row, "spread_percentile")
    checks = [
        _condition(f"Spread percentile is inside {spread_min:g}-{spread_max:g}.", spread_min <= spreadp < spread_max, reasons, failures),
        _condition(f"Candle range is {candle_max:g} ATR or lower, or ATR percentile is {atr_max:g} or lower.", _num(row, "candle_range_atr") <= candle_max or _num(row, "atr_percentile") <= atr_max, reasons, failures),
        _condition("Session is Asia or OffSession.", row.get("session") in {"Asia", "OffSession"}, reasons, failures),
        _condition("News flag is false.", not bool(row.get("news_flag")), reasons, failures),
        _condition("Session is not rollover.", row.get("session") != "Rollover", reasons, failures),
    ]
    confidence = sum(checks) / len(checks)
    return _base_result("R50", sum(checks), len(checks), reasons, failures, _confidence_ok(row, "R50", confidence, 0.75) and not hard_block)


def detect_regime(row: dict[str, Any]) -> dict[str, Any]:
    modifiers = detect_modifiers(row)
    hard_block = bool(modifiers["hard_block"])
    ordered = [
        detect_r40(row),
        detect_r10(row),
        detect_r30(row),
        detect_r39(row, hard_block),
        detect_r09(row, hard_block),
        detect_r23(row, hard_block),
        detect_r24(row, hard_block),
        detect_r50(row, hard_block),
        detect_r38(row, hard_block),
        detect_r07(row, hard_block),
        detect_r08(row, hard_block),
        detect_r45(row, hard_block),
        detect_r32(row, hard_block),
        detect_r33(row, hard_block),
        detect_r29(row, hard_block),
        detect_r25(row, hard_block),
        detect_r26(row, hard_block),
        detect_r27(row, hard_block),
        detect_r28(row, hard_block),
        detect_r19(row, hard_block),
        detect_r20(row, hard_block),
        detect_r21(row, hard_block),
        detect_r41(row, hard_block),
        detect_r42(row, hard_block),
        detect_r49(row, hard_block),
        detect_r06(row, hard_block),
        detect_r47(row, hard_block),
        detect_r17(row, hard_block),
        detect_r18(row, hard_block),
        detect_r15(row, hard_block),
        detect_r16(row, hard_block),
        detect_r43(row, hard_block),
        detect_r34(row, hard_block),
        detect_r35(row, hard_block),
        detect_r44(row, hard_block),
        detect_r46(row, hard_block),
        detect_r04(row, hard_block),
        detect_r05(row, hard_block),
        detect_r13(row, hard_block),
        detect_r14(row, hard_block),
        detect_r11(row, hard_block),
        detect_r12(row, hard_block),
        detect_r01(row, hard_block),
        detect_r02(row, hard_block),
        detect_r36(row, hard_block),
        detect_r48(row, hard_block),
        detect_r37(row, hard_block),
        detect_r22(row, hard_block),
        detect_r03(row, hard_block),
        detect_r31(row, hard_block),
    ]
    for candidate in ordered:
        if candidate["is_active"]:
            return candidate
    best = sorted(ordered, key=lambda item: item["confidence"], reverse=True)[0]
    best["is_active"] = False
    return best
