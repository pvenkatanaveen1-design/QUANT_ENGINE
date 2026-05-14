from __future__ import annotations

import math
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from core.config_manager import ConfigManager
from core.models.regime import RegimeFeatureSet, RegimeReason, RegimeResult
from core.time_utils import classify_session


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _cfg() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manager = ConfigManager(PROJECT_ROOT)
    return (
        manager.load_yaml("config/regimes.yaml"),
        manager.load_yaml("systems/regime/config.yaml"),
        manager.load_yaml("config/sessions.yaml"),
    )


def _values(rows: list[dict[str, Any]], column: str) -> list[float]:
    return [float(row[column]) for row in rows]


def _true_ranges(rows: list[dict[str, Any]]) -> list[float]:
    ranges: list[float] = []
    for index, row in enumerate(rows):
        high = float(row["high"])
        low = float(row["low"])
        if index == 0:
            ranges.append(high - low)
            continue
        prev_close = float(rows[index - 1]["close"])
        ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return ranges


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile_rank(values: list[float], current: float) -> float:
    if not values:
        return 0.0
    if max(values) == min(values):
        return 50.0
    below_or_equal = sum(1 for value in values if value <= current)
    return 100.0 * below_or_equal / len(values)


def _trend_efficiency(closes: list[float], period: int) -> float:
    if len(closes) <= period:
        return 0.0
    net = abs(closes[-1] - closes[-period - 1])
    path = sum(abs(closes[index] - closes[index - 1]) for index in range(len(closes) - period, len(closes)))
    return net / path if path else 0.0


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    multiplier = 2 / (period + 1)
    ema = values[0]
    for value in values[1:]:
        ema = (value - ema) * multiplier + ema
    return ema


def _simplified_adx(rows: list[dict[str, Any]], period: int = 14) -> float:
    if len(rows) <= period + 1:
        return 0.0
    trs = _true_ranges(rows)
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for index in range(1, len(rows)):
        up_move = float(rows[index]["high"]) - float(rows[index - 1]["high"])
        down_move = float(rows[index - 1]["low"]) - float(rows[index]["low"])
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
    tr_period = sum(trs[-period:]) or 1e-12
    plus_di = 100.0 * sum(plus_dm[-period:]) / tr_period
    minus_di = 100.0 * sum(minus_dm[-period:]) / tr_period
    denominator = plus_di + minus_di
    return 100.0 * abs(plus_di - minus_di) / denominator if denominator else 0.0


def _jump_z(closes: list[float], lookback: int = 30) -> float:
    if len(closes) <= lookback + 1:
        return 0.0
    returns = [math.log(closes[index] / closes[index - 1]) for index in range(1, len(closes)) if closes[index - 1] > 0]
    recent = returns[-lookback:]
    sigma = pstdev(recent) if len(recent) > 1 else 0.0
    baseline = abs(mean(recent)) * 0.75 if recent else 0.0
    denominator = max(sigma, baseline, 1e-8)
    return abs(returns[-1]) / denominator if denominator else 0.0


def _compression_percentile(rows: list[dict[str, Any]], lookback: int) -> float:
    if len(rows) < lookback:
        return 100.0
    ranges = [float(row["high"]) - float(row["low"]) for row in rows]
    current = _average(ranges[-min(10, len(ranges)):])
    history = []
    for index in range(lookback, len(ranges) + 1):
        history.append(_average(ranges[index - lookback:index]))
    return _percentile_rank(history, current)


def _candle_ratios(row: dict[str, Any]) -> tuple[float, float, float]:
    high = float(row["high"])
    low = float(row["low"])
    open_ = float(row["open"])
    close = float(row["close"])
    candle_range = max(high - low, 1e-12)
    body = abs(close - open_)
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    return body / candle_range, upper_wick / candle_range, lower_wick / candle_range


def _sweep_flags(rows: list[dict[str, Any]], lookback: int, spread_percentile: float) -> tuple[bool, bool]:
    if len(rows) <= lookback + 1:
        return False, False
    current = rows[-1]
    prior = rows[-lookback - 1:-1]
    prior_high = max(float(row["high"]) for row in prior)
    prior_low = min(float(row["low"]) for row in prior)
    body_ratio, upper_wick_ratio, lower_wick_ratio = _candle_ratios(current)
    sweep_high = float(current["high"]) > prior_high and float(current["close"]) < prior_high and upper_wick_ratio > 0.45 and spread_percentile < 80
    sweep_low = float(current["low"]) < prior_low and float(current["close"]) > prior_low and lower_wick_ratio > 0.45 and spread_percentile < 80
    return sweep_high, sweep_low


def calculate_feature_snapshot(rows: list[dict[str, Any]], context: dict[str, Any] | None = None) -> RegimeFeatureSet:
    regimes_config, local_config, sessions_config = _cfg()
    thresholds = regimes_config.get("thresholds", {})
    lookbacks = local_config.get("feature_lookbacks", {})
    atr_period = int(lookbacks.get("atr_period", thresholds.get("atr_period", 14)))
    trend_period = int(lookbacks.get("trend_efficiency_period", thresholds.get("trend_efficiency_period", 30)))
    vol_lookback = int(lookbacks.get("volatility_percentile_lookback", thresholds.get("volatility_percentile_lookback", 252)))
    swing_lookback = int(lookbacks.get("swing_lookback", 20))

    if not rows:
        return RegimeFeatureSet(data_quality_bad=True, extra={"error": "no rows"})

    rows = sorted(rows, key=lambda row: row["time"])
    closes = _values(rows, "close")
    trs = _true_ranges(rows)
    atr = _average(trs[-atr_period:])
    close = closes[-1]
    atr_percent = atr / close if close else 0.0

    atr_percents: list[float] = []
    for index in range(atr_period, len(rows) + 1):
        window_atr = _average(trs[index - atr_period:index])
        window_close = float(rows[index - 1]["close"])
        atr_percents.append(window_atr / window_close if window_close else 0.0)
    vol_history = atr_percents[-vol_lookback:] or atr_percents
    volatility_percentile = _percentile_rank(vol_history, atr_percent)

    spreads = _values(rows, "spread")
    spread_percentile = _percentile_rank(spreads[-vol_lookback:], spreads[-1])
    body_ratio, upper_wick_ratio, lower_wick_ratio = _candle_ratios(rows[-1])
    sweep_high, sweep_low = _sweep_flags(rows, swing_lookback, spread_percentile)
    session = classify_session(rows[-1]["time"], sessions_config)

    slope = (closes[-1] - closes[-min(trend_period + 1, len(closes))]) / max(1, min(trend_period, len(closes) - 1))
    slope_score = slope / atr if atr else 0.0

    return RegimeFeatureSet(
        atr=atr,
        atr_percent=atr_percent,
        volatility_percentile=volatility_percentile,
        trend_efficiency=_trend_efficiency(closes, trend_period),
        adx=_simplified_adx(rows, atr_period),
        slope_score=slope_score,
        spread_percentile=spread_percentile,
        jump_z=_jump_z(closes, trend_period),
        compression_percentile=_compression_percentile(rows, trend_period),
        body_ratio=body_ratio,
        upper_wick_ratio=upper_wick_ratio,
        lower_wick_ratio=lower_wick_ratio,
        session_label=str(session.get("session") or "Unclassified"),
        sweep_high=sweep_high,
        sweep_low=sweep_low,
        data_quality_bad=bool(context and context.get("data_quality_bad")),
        extra={
            "session_modifier": session.get("modifier") or "M01",
            "ema_50": _ema(closes[-50:], 50),
            "close": close,
        },
    )


def _choose_base(features: RegimeFeatureSet, thresholds: dict[str, Any], reasons: list[RegimeReason]) -> str:
    if features.data_quality_bad:
        reasons.append(RegimeReason("data_quality_bad", "Data quality is marked bad; trading is blocked.", "critical"))
        return "Q4"
    if features.spread_percentile >= float(thresholds.get("spread_critical_percentile", 95)):
        reasons.append(RegimeReason("spread_critical", f"Spread percentile {features.spread_percentile:.1f} >= {float(thresholds.get('spread_critical_percentile', 95)):.1f}.", "critical"))
        return "Q4"
    if features.jump_z > float(thresholds.get("jump_shock_z", 3.0)):
        reasons.append(RegimeReason("jump_shock", f"Jump z-score {features.jump_z:.2f} > {float(thresholds.get('jump_shock_z', 3.0)):.2f}.", "critical"))
        return "Q4"
    extreme_vol = features.volatility_percentile >= float(thresholds.get("extreme_vol_percentile", 90)) or features.atr_percent >= float(thresholds.get("extreme_vol_atr_percent", 0.004))
    if extreme_vol:
        reasons.append(RegimeReason("volatility_extreme", f"Volatility percentile {features.volatility_percentile:.1f} or ATR percent {features.atr_percent:.4f} is extreme.", "warning"))
        return "Q4"

    trend = features.trend_efficiency >= float(thresholds.get("trend_efficiency_min", 0.35)) and features.adx >= float(thresholds.get("adx_trend_min", 22))
    range_bound = features.trend_efficiency <= float(thresholds.get("trend_efficiency_range_max", 0.25)) and features.adx <= float(thresholds.get("adx_range_max", 18))
    high_vol = features.volatility_percentile > float(thresholds.get("high_vol_percentile", 70)) or features.atr_percent >= float(thresholds.get("high_vol_atr_percent", 0.0015))

    if trend and high_vol:
        reasons.append(RegimeReason("trend_high_vol", f"Trend efficiency {features.trend_efficiency:.2f} >= {float(thresholds.get('trend_efficiency_min', 0.35)):.2f}, ADX {features.adx:.1f} >= {float(thresholds.get('adx_trend_min', 22)):.1f}, volatility percentile {features.volatility_percentile:.1f} or ATR percent {features.atr_percent:.4f} is high."))
        return "Q2"
    if trend:
        reasons.append(RegimeReason("trend_low_normal_vol", f"Trend efficiency {features.trend_efficiency:.2f} >= {float(thresholds.get('trend_efficiency_min', 0.35)):.2f}, ADX {features.adx:.1f} >= {float(thresholds.get('adx_trend_min', 22)):.1f}, volatility percentile {features.volatility_percentile:.1f} <= {float(thresholds.get('high_vol_percentile', 70)):.1f}."))
        return "Q1"
    if range_bound:
        reasons.append(RegimeReason("range_low_normal_vol", f"Trend efficiency {features.trend_efficiency:.2f} <= {float(thresholds.get('trend_efficiency_range_max', 0.25)):.2f} and ADX {features.adx:.1f} <= {float(thresholds.get('adx_range_max', 18)):.1f}."))
        return "Q3"

    reasons.append(RegimeReason("transition", f"Trend/range evidence is mixed: trend efficiency {features.trend_efficiency:.2f}, ADX {features.adx:.1f}, volatility percentile {features.volatility_percentile:.1f}.", "warning"))
    return "Q4"


def _choose_modifier(features: RegimeFeatureSet, thresholds: dict[str, Any], context: dict[str, Any] | None, reasons: list[RegimeReason]) -> str:
    context = context or {}
    if features.spread_percentile >= float(thresholds.get("spread_stress_percentile", 90)):
        reasons.append(RegimeReason("spread_stress", f"Spread percentile {features.spread_percentile:.1f} >= {float(thresholds.get('spread_stress_percentile', 90)):.1f}; M10 overrides normal modifiers.", "warning"))
        return "M10"
    if context.get("pre_news_lock") or context.get("news_lock_active"):
        reasons.append(RegimeReason("pre_news_lock", "News lock is active.", "warning"))
        return "M07"
    if context.get("post_news_active"):
        reasons.append(RegimeReason("post_news", "Post-news mode is active."))
        return "M08"
    if context.get("correlation_shock"):
        reasons.append(RegimeReason("correlation_shock", "Correlation/USD shock input is active.", "warning"))
        return "M13"
    if context.get("multi_timeframe_agreement"):
        reasons.append(RegimeReason("multi_timeframe_agreement", "Higher and current timeframe agree."))
        return "M12"
    if features.sweep_high or features.sweep_low:
        side = "high" if features.sweep_high else "low"
        reasons.append(RegimeReason("liquidity_sweep", f"Latest candle swept prior swing {side} and closed back inside."))
        return "M09"

    close = float(features.extra.get("close") or 0.0)
    ema_50 = float(features.extra.get("ema_50") or close)
    distance_from_mean = abs(close - ema_50) / features.atr if features.atr else 0.0
    rejection_present = max(features.upper_wick_ratio, features.lower_wick_ratio) > 0.55 and features.body_ratio < 0.45
    if distance_from_mean >= float(thresholds.get("exhaustion_atr_distance", 2.5)) and features.adx >= float(thresholds.get("adx_trend_min", 22)) and rejection_present:
        reasons.append(RegimeReason("trend_exhaustion", f"Price is {distance_from_mean:.2f} ATR from EMA50; threshold is {float(thresholds.get('exhaustion_atr_distance', 2.5)):.2f}."))
        return "M11"
    if features.compression_percentile <= float(thresholds.get("compression_percentile", 25)):
        reasons.append(RegimeReason("compression", f"Compression percentile {features.compression_percentile:.1f} <= {float(thresholds.get('compression_percentile', 25)):.1f}."))
        return "M02"

    session_modifier = str(features.extra.get("session_modifier") or "M01")
    if session_modifier in {"M03", "M04", "M05", "M06"}:
        reasons.append(RegimeReason("session_modifier", f"{features.session_label} session detected; maps to {session_modifier}."))
        return session_modifier

    reasons.append(RegimeReason("clean_liquid_market", "No stronger modifier applied; using clean market modifier."))
    return "M01"


def detect_regime_for_rows(rows: list[dict[str, Any]], symbol: str = "UNKNOWN", timeframe: str = "UNKNOWN", context: dict[str, Any] | None = None) -> RegimeResult:
    regimes_config, _, _ = _cfg()
    thresholds = regimes_config.get("thresholds", {})
    reasons: list[RegimeReason] = []
    features = calculate_feature_snapshot(rows, context=context)
    base = _choose_base(features, thresholds, reasons)
    modifier = _choose_modifier(features, thresholds, context, reasons)
    regime_id = f"{base}_{modifier}"

    base_meta = regimes_config.get("base_regimes", {}).get(base, {})
    modifier_meta = regimes_config.get("modifiers", {}).get(modifier, {})
    tradable = bool(base_meta.get("tradable", False)) and bool(modifier_meta.get("tradable", True))
    risk_posture = str(modifier_meta.get("risk_posture") or base_meta.get("risk_posture") or "unknown")

    confidence = 0.55
    confidence += min(features.trend_efficiency, 0.5) * 0.35
    confidence += min(features.adx / 100.0, 0.4) * 0.25
    confidence -= 0.2 if base == "Q4" else 0.0
    confidence -= 0.15 if modifier in {"M10", "M07", "M13"} else 0.0
    confidence = max(0.1, min(0.95, confidence))

    return RegimeResult(
        base_regime=base,
        modifier=modifier,
        regime_id=regime_id,
        confidence=round(confidence, 4),
        tradable=tradable,
        risk_posture=risk_posture,
        reasons=reasons,
        features=features,
    )


def dataframe_to_rows(dataframe: Any) -> list[dict[str, Any]]:
    if hasattr(dataframe, "to_dict"):
        return list(dataframe.to_dict(orient="records"))
    return list(dataframe)
