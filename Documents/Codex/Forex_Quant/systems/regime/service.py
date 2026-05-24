from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from core.config_manager import ConfigManager
from core.models.regime import RegimeFeatureSet, RegimeReason, RegimeResult
from core.time_utils import classify_session, to_utc


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


def _ols_slope_per_bar(closes: list[float]) -> float:
    """Least-squares slope of close vs bar index (price units per bar)."""
    n = len(closes)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(closes) / n
    num = sum((i - x_mean) * (closes[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den else 0.0


def _slope_score(closes: list[float], period: int, atr: float) -> float:
    """Blueprint-style trend tilt: slope_N / ATR over the last `period` closes (or fewer if short history)."""
    if len(closes) < 2:
        return 0.0
    window = closes[-period:] if len(closes) >= period else closes
    raw = _ols_slope_per_bar(window)
    return raw / max(atr, 1e-10)


def _kaufman_er(closes: list[float], period: int) -> float:
    """
    Kaufman Efficiency Ratio: |net displacement| / sum(|step changes|) over the last `period` bars.
    Source: Kaufman (1995). Same receptive field as the prior efficiency_ratio helper.
    """
    if len(closes) <= period:
        return 0.0
    net = abs(closes[-1] - closes[-period - 1])
    path = sum(abs(closes[index] - closes[index - 1]) for index in range(len(closes) - period, len(closes)))
    return net / path if path else 0.0


def _ema(values: list[float], period: int) -> float:
    """
    SMA-seeded EMA. Seeds from mean of first period bars, NOT values[0].
    Starting from values[0] distorts first 50-100 bars on short history.
    """
    if not values:
        return 0.0
    if len(values) < period:
        return sum(values) / len(values)
    seed = sum(values[:period]) / period
    multiplier = 2.0 / (period + 1)
    ema = seed
    for value in values[period:]:
        ema = (value - ema) * multiplier + ema
    return ema


def _wilder_adx(rows: list[dict[str, Any]], period: int = 14) -> float:
    """
    Wilder-smoothed ADX on the bar series (last value). Replaces the prior single-smoothed DX blend.
    Source: Wilder (1978).
    """
    if len(rows) < period * 2 + 1:
        return 0.0
    highs = [float(r["high"]) for r in rows]
    lows = [float(r["low"]) for r in rows]
    closes = [float(r["close"]) for r in rows]

    trs: list[float] = [highs[0] - lows[0]]
    for i in range(1, len(rows)):
        hl = highs[i] - lows[i]
        hpc = abs(highs[i] - closes[i - 1])
        lpc = abs(lows[i] - closes[i - 1])
        trs.append(max(hl, hpc, lpc))

    plus_dms: list[float] = [0.0]
    minus_dms: list[float] = [0.0]
    for i in range(1, len(rows)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dms.append(up if up > down and up > 0 else 0.0)
        minus_dms.append(down if down > up and down > 0 else 0.0)

    alpha = 1.0 / period

    def wilder(values: list[float]) -> list[float]:
        out = [values[0]]
        for v in values[1:]:
            out.append(out[-1] * (1 - alpha) + v * alpha)
        return out

    atr_s = wilder(trs)
    plus_s = wilder(plus_dms)
    minus_s = wilder(minus_dms)

    plus_di = [100.0 * p / max(a, 1e-10) for p, a in zip(plus_s, atr_s)]
    minus_di = [100.0 * m / max(a, 1e-10) for m, a in zip(minus_s, atr_s)]

    dx_series: list[float] = []
    for p, m in zip(plus_di, minus_di):
        den = p + m
        dx_series.append(100.0 * abs(p - m) / den if den > 0 else 0.0)

    adx_series = wilder(dx_series)
    return adx_series[-1]


def _jump_z(rows: list[dict[str, Any]], period: int = 30) -> float:
    """
    Jump detector for FX using log returns.
    FX mean return ≈ 0. Real jump: |return| > 3×sigma AND sigma > hist_sigma × 1.5
    """
    if len(rows) < period + 1:
        return 0.0
    log_returns: list[float] = []
    for i in range(1, len(rows)):
        c0 = float(rows[i - 1]["close"])
        c1 = float(rows[i]["close"])
        if c0 > 0:
            log_returns.append(math.log(c1 / c0))
    if len(log_returns) < period:
        return 0.0
    recent = log_returns[-period:]
    last = recent[-1]
    m = sum(recent) / len(recent)
    var = sum((r - m) ** 2 for r in recent) / len(recent)
    sigma = var**0.5
    if sigma <= 0:
        return 0.0
    full_m = sum(log_returns) / len(log_returns)
    full_var = sum((r - full_m) ** 2 for r in log_returns) / len(log_returns)
    hist_sigma = full_var**0.5
    z = abs(last) / sigma
    sigma_ratio = sigma / max(hist_sigma, 1e-10)
    return z if (z > 3.0 and sigma_ratio > 1.5) else 0.0


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


def _pip_size(price: float) -> float:
    return 0.01 if abs(price) >= 10 else 0.0001


def _volume_ratio(rows: list[dict[str, Any]], lookback: int = 20) -> float:
    volumes = [float(row.get("tick_volume", 0) or 0) for row in rows]
    if len(volumes) < 2:
        return 1.0
    history = volumes[-lookback - 1:-1] or volumes[:-1]
    baseline = _average(history) or 1.0
    return volumes[-1] / baseline


def _round_number_context(price: float) -> dict[str, Any]:
    pip = _pip_size(price)
    step = pip * 50.0
    nearest = round(price / step) * step if step else price
    distance_pips = abs(price - nearest) / pip if pip else 0.0
    decimals = 3 if pip >= 0.01 else 5
    return {
        "nearest_round_number": round(nearest, decimals),
        "round_number_distance_pips": round(distance_pips, 2),
        "near_round_number": distance_pips <= 5.0,
    }


def _equal_level_context(rows: list[dict[str, Any]], lookback: int, pip: float) -> dict[str, Any]:
    if len(rows) <= lookback + 1:
        return {"equal_high_cluster": False, "equal_low_cluster": False, "prior_cluster_high": None, "prior_cluster_low": None}
    prior = rows[-lookback - 1:-1]
    tolerance = max(pip * 3.0, 1e-12)
    prior_high = max(float(row["high"]) for row in prior)
    prior_low = min(float(row["low"]) for row in prior)
    high_touches = sum(1 for row in prior if abs(float(row["high"]) - prior_high) <= tolerance)
    low_touches = sum(1 for row in prior if abs(float(row["low"]) - prior_low) <= tolerance)
    decimals = 3 if pip >= 0.01 else 5
    return {
        "equal_high_cluster": high_touches >= 2,
        "equal_low_cluster": low_touches >= 2,
        "prior_cluster_high": round(prior_high, decimals),
        "prior_cluster_low": round(prior_low, decimals),
        "equal_high_touches": high_touches,
        "equal_low_touches": low_touches,
    }


def _asian_range_context(rows: list[dict[str, Any]], sessions_config: dict[str, Any], pip: float) -> dict[str, Any]:
    if len(rows) < 3:
        return {"asian_range_high": None, "asian_range_low": None, "asian_high_swept": False, "asian_low_swept": False}
    current_time = to_utc(rows[-1]["time"])
    current = rows[-1]
    asia_rows: list[dict[str, Any]] = []
    for row in reversed(rows[:-1]):
        row_time = to_utc(row["time"])
        if (current_time - row_time).total_seconds() > 36 * 3600:
            break
        if classify_session(row["time"], sessions_config).get("session") == "Asia":
            asia_rows.append(row)
    if not asia_rows:
        return {"asian_range_high": None, "asian_range_low": None, "asian_high_swept": False, "asian_low_swept": False}
    high = max(float(row["high"]) for row in asia_rows)
    low = min(float(row["low"]) for row in asia_rows)
    tolerance = max(pip * 1.0, 1e-12)
    decimals = 3 if pip >= 0.01 else 5
    return {
        "asian_range_high": round(high, decimals),
        "asian_range_low": round(low, decimals),
        "asian_high_swept": float(current["high"]) > high + tolerance and float(current["close"]) < high,
        "asian_low_swept": float(current["low"]) < low - tolerance and float(current["close"]) > low,
    }


def _microstructure_context(
    *,
    rows: list[dict[str, Any]],
    sessions_config: dict[str, Any],
    swing_lookback: int,
    close: float,
    spread_percentile: float,
    sweep_high: bool,
    sweep_low: bool,
    upper_wick_ratio: float,
    lower_wick_ratio: float,
) -> dict[str, Any]:
    pip = _pip_size(close)
    volume_ratio = _volume_ratio(rows, lookback=20)
    round_ctx = _round_number_context(close)
    equal_ctx = _equal_level_context(rows, swing_lookback, pip)
    asia_ctx = _asian_range_context(rows, sessions_config, pip)
    stop_zones: list[str] = []
    if round_ctx["near_round_number"]:
        stop_zones.append("round_number")
    if equal_ctx["equal_high_cluster"]:
        stop_zones.append("equal_highs")
    if equal_ctx["equal_low_cluster"]:
        stop_zones.append("equal_lows")
    if asia_ctx["asian_high_swept"]:
        stop_zones.append("asian_high_sweep")
    if asia_ctx["asian_low_swept"]:
        stop_zones.append("asian_low_sweep")

    trap_score = 0
    trap_score += 30 if sweep_high or sweep_low or asia_ctx["asian_high_swept"] or asia_ctx["asian_low_swept"] else 0
    trap_score += 20 if volume_ratio >= 1.5 else 0
    trap_score += 15 if round_ctx["near_round_number"] else 0
    trap_score += 15 if equal_ctx["equal_high_cluster"] or equal_ctx["equal_low_cluster"] else 0
    trap_score += 10 if max(upper_wick_ratio, lower_wick_ratio) >= 0.55 else 0
    trap_score += 10 if spread_percentile >= 80 else 0
    if sweep_high or asia_ctx["asian_high_swept"]:
        sweep_direction = "high_sweep_reversal_short_watch"
    elif sweep_low or asia_ctx["asian_low_swept"]:
        sweep_direction = "low_sweep_reversal_long_watch"
    else:
        sweep_direction = "none"

    return {
        **round_ctx,
        **equal_ctx,
        **asia_ctx,
        "pip_size": pip,
        "tick_volume": float(rows[-1].get("tick_volume", 0) or 0),
        "tick_volume_ratio": round(volume_ratio, 3),
        "volume_spike": volume_ratio >= 1.5,
        "retail_stop_zones": stop_zones,
        "institutional_trap_score": min(100, trap_score),
        "liquidity_sweep_direction": sweep_direction,
        "news_proxy": {
            "status": "proxy_only_no_calendar",
            "jump_z": None,
            "spread_percentile": round(spread_percentile, 2),
            "tick_volume_ratio": round(volume_ratio, 3),
        },
        "sentiment_status": "unavailable_without_feed",
    }


def calculate_feature_snapshot(rows: list[dict[str, Any]], context: dict[str, Any] | None = None) -> RegimeFeatureSet:
    regimes_config, local_config, sessions_config = _cfg()
    thresholds = regimes_config.get("thresholds", {})
    lookbacks = local_config.get("feature_lookbacks", {})
    atr_period = int(lookbacks.get("atr_period", thresholds.get("atr_period", 14)))
    trend_period = int(
        lookbacks.get(
            "efficiency_ratio_period",
            thresholds.get(
                "efficiency_ratio_period",
                lookbacks.get("trend_efficiency_period", thresholds.get("trend_efficiency_period", 30)),
            ),
        )
    )
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
    jump_z = _jump_z(rows, trend_period)
    microstructure = _microstructure_context(
        rows=rows,
        sessions_config=sessions_config,
        swing_lookback=swing_lookback,
        close=close,
        spread_percentile=spread_percentile,
        sweep_high=sweep_high,
        sweep_low=sweep_low,
        upper_wick_ratio=upper_wick_ratio,
        lower_wick_ratio=lower_wick_ratio,
    )
    microstructure["news_proxy"]["jump_z"] = round(jump_z, 3)

    return RegimeFeatureSet(
        atr=atr,
        atr_percent=atr_percent,
        volatility_percentile=volatility_percentile,
        efficiency_ratio=_kaufman_er(closes, trend_period),
        adx=_wilder_adx(rows, atr_period),
        slope_score=_slope_score(closes, trend_period, atr),
        spread_percentile=spread_percentile,
        jump_z=jump_z,
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
            "kill_zone_active": bool(session.get("kill_zone_active", False)),
            "ema_50": _ema(closes[-50:], 50),
            "close": close,
            **microstructure,
        },
    )


def _compute_confidence(features: RegimeFeatureSet, base_regime: str, modifier: str) -> float:
    """
    Confidence score 0.10 – 0.95. Higher = more signals agree.
    Uses RegimeFeatureSet field names (volatility_percentile, spread_percentile, etc.).
    """
    kz = bool(features.extra.get("kill_zone_active", False))

    score = 0.0
    weights = 0.0

    if base_regime in ("Q1", "Q2"):
        if features.adx > 30:
            score += 0.25
        elif features.adx > 25:
            score += 0.18
        elif features.adx > 22:
            score += 0.10
        weights += 0.25

    if base_regime in ("Q1", "Q2") and features.efficiency_ratio > 0.50:
        score += 0.20
    elif base_regime == "Q3" and features.efficiency_ratio < 0.20:
        score += 0.20
    weights += 0.20

    if modifier == "M04" and kz:
        score += 0.15
    weights += 0.15

    if modifier == "M09" and (features.sweep_high or features.sweep_low):
        score += 0.15
    weights += 0.15

    vpt = features.volatility_percentile
    if base_regime in ("Q1", "Q3") and vpt < 50:
        score += 0.10
    elif base_regime == "Q2" and vpt > 70:
        score += 0.10
    weights += 0.10

    if features.spread_percentile < 50:
        score += 0.10
    weights += 0.10

    if modifier == "M02" and features.compression_percentile <= 20:
        score += 0.05
    weights += 0.05

    raw = score / max(weights, 1e-10)
    return max(0.10, min(0.95, raw))


def _choose_base(features: RegimeFeatureSet, thresholds: dict[str, Any], reasons: list[RegimeReason]) -> str:
    er_min = float(thresholds.get("efficiency_ratio_min", thresholds.get("trend_efficiency_min", 0.35)))
    er_max = float(thresholds.get("efficiency_ratio_range_max", thresholds.get("trend_efficiency_range_max", 0.25)))
    if features.data_quality_bad:
        reasons.append(RegimeReason("data_quality_bad", "Data quality is marked bad; trading is blocked.", "critical"))
        return "Q4"
    if features.spread_percentile >= float(thresholds.get("spread_critical_percentile", 95)):
        reasons.append(RegimeReason("spread_critical", f"Spread percentile {features.spread_percentile:.1f} >= {float(thresholds.get('spread_critical_percentile', 95)):.1f}.", "critical"))
        return "Q4"
    if features.jump_z > float(thresholds.get("jump_shock_z", 3.0)):
        reasons.append(RegimeReason("jump_shock", f"Jump z-score {features.jump_z:.2f} > {float(thresholds.get('jump_shock_z', 3.0)):.2f}.", "critical"))
        return "Q4"

    extreme_vol = features.volatility_percentile >= float(thresholds.get("extreme_vol_percentile", 90)) or features.atr_percent >= float(
        thresholds.get("extreme_vol_atr_percent", 0.004)
    )
    high_vol = features.volatility_percentile > float(thresholds.get("high_vol_percentile", 70)) or features.atr_percent >= float(
        thresholds.get("high_vol_atr_percent", 0.0015)
    )
    trend = features.efficiency_ratio >= er_min and features.adx >= float(thresholds.get("adx_trend_min", 22))
    range_bound = features.efficiency_ratio <= er_max and features.adx <= float(thresholds.get("adx_range_max", 18))

    if trend and (high_vol or extreme_vol):
        reasons.append(
            RegimeReason(
                "trend_high_vol",
                f"Trend (ER={features.efficiency_ratio:.2f} ADX={features.adx:.1f}) + elevated vol ({features.volatility_percentile:.0f}th pct / ATR%). Q2.",
            )
        )
        return "Q2"
    if trend:
        reasons.append(RegimeReason("trend_low_vol", "Trend confirmed, normal vol. Q1."))
        return "Q1"
    if range_bound and not high_vol:
        reasons.append(
            RegimeReason(
                "range_low_vol",
                f"Range (ER={features.efficiency_ratio:.2f} ADX={features.adx:.1f}). Q3.",
            )
        )
        return "Q3"
    if extreme_vol:
        reasons.append(
            RegimeReason(
                "extreme_vol_no_trend",
                f"Extreme vol no trend ({features.volatility_percentile:.0f}th pct). Q4.",
                "warning",
            )
        )
        return "Q4"
    reasons.append(
        RegimeReason(
            "transition",
            f"Mixed signals. ER={features.efficiency_ratio:.2f} ADX={features.adx:.1f}. Q4.",
            "warning",
        )
    )
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

    confidence = round(_compute_confidence(features, base, modifier), 4)

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


def regime_to_dict(result: RegimeResult) -> dict[str, Any]:
    return asdict(result)


def get_current_regime(symbol: str = "EURUSD", timeframe: str = "M15") -> RegimeResult:
    """Latest regime classification from cleaned bars (no extra MT5 fetch)."""
    from systems.data.service import load_cleaned_rows

    sym, tf = symbol.upper(), timeframe.upper()
    rows = load_cleaned_rows(sym, tf)
    return detect_regime_for_rows(rows, symbol=sym, timeframe=tf)


def _row_time(row: dict[str, Any]) -> Any:
    return to_utc(row["time"])


def _is_killzone(row: dict[str, Any], sessions_config: dict[str, Any]) -> bool:
    return bool(classify_session(row["time"], sessions_config).get("kill_zone_active"))


def _window_label(start: Any, end: Any | None = None) -> str:
    start_text = to_utc(start).isoformat()
    if end is None:
        return start_text
    return f"{start_text} -> {to_utc(end).isoformat()}"


def _timeframe_minutes(timeframe: str) -> int:
    key = str(timeframe).upper()
    if key.startswith("M"):
        return max(1, int(key[1:] or 1))
    if key.startswith("H"):
        return max(1, int(key[1:] or 1) * 60)
    if key.startswith("D"):
        return max(1, int(key[1:] or 1) * 1440)
    return 15


def _regime_library(regimes_config: dict[str, Any]) -> list[str]:
    return [
        f"{base}_{modifier}"
        for base in regimes_config.get("base_regimes", {})
        for modifier in regimes_config.get("modifiers", {})
    ]


def _build_segments(timeline: list[dict[str, Any]], bar_minutes: int) -> list[dict[str, Any]]:
    if not timeline:
        return []
    segments: list[dict[str, Any]] = []
    start = timeline[0]
    end = timeline[0]
    bars = 1
    for entry in timeline[1:]:
        if entry["regime_id"] == end["regime_id"]:
            end = entry
            bars += 1
            continue
        segments.append(
            {
                "regime_id": end["regime_id"],
                "start": start["time"],
                "end": end["time"],
                "bars": bars,
                "duration_minutes": round(float(max(1, bars) * bar_minutes), 2),
            }
        )
        start = entry
        end = entry
        bars = 1
    segments.append(
        {
            "regime_id": end["regime_id"],
            "start": start["time"],
            "end": end["time"],
            "bars": bars,
            "duration_minutes": round(float(max(1, bars) * bar_minutes), 2),
        }
    )
    return segments


def _status_for_regime(regime_id: str, current_id: str | None, previous_id: str | None, observed: bool) -> str:
    if regime_id == current_id:
        return "current"
    if regime_id == previous_id:
        return "previous"
    if observed:
        return "observed"
    return "not_observed"


def _build_regime_scan_table(
    *,
    regimes_config: dict[str, Any],
    timeline: list[dict[str, Any]],
    regime_counts: Counter[str],
    transitions: list[dict[str, Any]],
    current_id: str | None,
    previous_id: str | None,
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    total_bars = len(timeline)
    latest_by_regime: dict[str, dict[str, Any]] = {}
    confidence_by_regime: dict[str, list[float]] = {}
    first_seen: dict[str, str] = {}
    tradable_counts: Counter[str] = Counter()
    no_trade_counts: Counter[str] = Counter()
    killzone_counts: Counter[str] = Counter()
    spread_stress_counts: Counter[str] = Counter()
    sweep_counts: Counter[str] = Counter()
    trap_counts: Counter[str] = Counter()
    volume_spike_counts: Counter[str] = Counter()
    round_number_counts: Counter[str] = Counter()
    transition_counts: Counter[str] = Counter()
    durations_by_regime: dict[str, list[float]] = {}

    for entry in timeline:
        regime_id = entry["regime_id"]
        latest_by_regime[regime_id] = entry
        first_seen.setdefault(regime_id, entry["time"])
        confidence_by_regime.setdefault(regime_id, []).append(float(entry.get("confidence") or 0.0))
        if entry.get("tradable"):
            tradable_counts[regime_id] += 1
        else:
            no_trade_counts[regime_id] += 1
        if entry.get("killzone"):
            killzone_counts[regime_id] += 1
        features = entry.get("features") or {}
        if float(features.get("spread_percentile") or 0.0) >= 90.0:
            spread_stress_counts[regime_id] += 1
        if features.get("sweep_high") or features.get("sweep_low"):
            sweep_counts[regime_id] += 1
        extra = features.get("extra") or {}
        if float(extra.get("institutional_trap_score") or 0.0) >= 60.0:
            trap_counts[regime_id] += 1
        if extra.get("volume_spike"):
            volume_spike_counts[regime_id] += 1
        if extra.get("near_round_number"):
            round_number_counts[regime_id] += 1

    for transition in transitions:
        transition_counts[str(transition.get("from"))] += 1
        transition_counts[str(transition.get("to"))] += 1

    for segment in segments:
        durations_by_regime.setdefault(segment["regime_id"], []).append(float(segment["duration_minutes"]))

    rows: list[dict[str, Any]] = []
    for regime_id in _regime_library(regimes_config):
        base, _, modifier = regime_id.partition("_")
        observed = regime_counts.get(regime_id, 0) > 0
        durations = durations_by_regime.get(regime_id, [])
        confidences = confidence_by_regime.get(regime_id, [])
        latest = latest_by_regime.get(regime_id)
        rows.append(
            {
                "regime_id": regime_id,
                "quadrant": base,
                "modifier": modifier,
                "observed": observed,
                "bars_count": int(regime_counts.get(regime_id, 0)),
                "pct_of_period": round(100.0 * regime_counts.get(regime_id, 0) / total_bars, 3) if total_bars else 0.0,
                "first_seen": first_seen.get(regime_id),
                "last_seen": latest.get("time") if latest else None,
                "avg_duration_minutes": round(mean(durations), 2) if durations else 0.0,
                "median_duration_minutes": round(median(durations), 2) if durations else 0.0,
                "last_duration_minutes": round(durations[-1], 2) if durations else 0.0,
                "transition_count": int(transition_counts.get(regime_id, 0)),
                "tradable_count": int(tradable_counts.get(regime_id, 0)),
                "no_trade_count": int(no_trade_counts.get(regime_id, 0)),
                "killzone_count": int(killzone_counts.get(regime_id, 0)),
                "spread_stress_count": int(spread_stress_counts.get(regime_id, 0)),
                "sweep_count": int(sweep_counts.get(regime_id, 0)),
                "institutional_trap_count": int(trap_counts.get(regime_id, 0)),
                "volume_spike_count": int(volume_spike_counts.get(regime_id, 0)),
                "round_number_count": int(round_number_counts.get(regime_id, 0)),
                "confidence_avg": round(mean(confidences), 4) if confidences else 0.0,
                "confidence_latest_if_current": round(float(latest.get("confidence") or 0.0), 4) if regime_id == current_id and latest else None,
                "status": _status_for_regime(regime_id, current_id, previous_id, observed),
            }
        )
    return rows


def _build_change_stats(
    *,
    segments: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
    current_duration_minutes: float,
    bars_analyzed: int,
    bar_minutes: int,
) -> dict[str, Any]:
    durations = [float(segment["duration_minutes"]) for segment in segments]
    previous_durations = durations[:-1] if len(durations) > 1 else durations
    period_minutes = max(float(bars_analyzed * bar_minutes), 1.0)
    period_days = max(period_minutes / 1440.0, 1.0 / 1440.0)
    typical = median(previous_durations) if previous_durations else current_duration_minutes
    if typical <= 0:
        age_state = "unknown"
    elif current_duration_minutes < typical * 0.5:
        age_state = "young"
    elif current_duration_minutes > typical * 1.5:
        age_state = "extended"
    else:
        age_state = "normal"
    return {
        "total_transitions": len(transitions),
        "changes_per_day": round(len(transitions) / period_days, 3),
        "avg_minutes_between_changes": round(mean(previous_durations), 2) if previous_durations else 0.0,
        "median_minutes_between_changes": round(median(previous_durations), 2) if previous_durations else 0.0,
        "fastest_change_minutes": round(min(previous_durations), 2) if previous_durations else 0.0,
        "slowest_change_minutes": round(max(previous_durations), 2) if previous_durations else 0.0,
        "current_regime_age_minutes": round(current_duration_minutes, 2),
        "current_regime_age_vs_typical": age_state,
        "by_timeframe_explanation": f"Duration uses contiguous regime segments on {bar_minutes}-minute bars.",
    }


def analyze_regime_window(
    rows: list[dict[str, Any]],
    symbol: str = "UNKNOWN",
    timeframe: str = "UNKNOWN",
    killzone_enabled: bool = True,
    include_spread_filter: bool = True,
    include_sweep_detection: bool = True,
    include_alpha_features: bool = True,
) -> dict[str, Any]:
    regimes_config, _, sessions_config = _cfg()
    ordered = sorted(rows, key=lambda row: row["time"])
    warnings: list[str] = []
    bar_minutes = _timeframe_minutes(timeframe)
    if len(ordered) < 30:
        warnings.append("Data is thin; regime confidence is limited.")
    if not ordered:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "current_regime": None,
            "previous_regime": None,
            "active_since": None,
            "bars_analyzed": 0,
            "bars_by_regime": {},
            "bars_by_quadrant": {},
            "bars_by_modifier": {},
            "regime_timeline": [],
            "regime_transition_table": [],
            "killzone_summary": {"enabled": killzone_enabled, "killzone_bars": 0, "non_killzone_bars": 0, "by_regime": {}},
            "spread_summary": {"stress_bars": 0, "max_spread_percentile": 0.0, "windows": []},
            "sweep_summary": {"events": 0, "windows": []},
            "institutional_summary": {
                "trap_events": 0,
                "volume_spike_events": 0,
                "round_number_events": 0,
                "retail_stop_zones": {},
                "high_trap_windows": [],
                "news_proxy_events": 0,
                "sentiment_status": "unavailable_without_feed",
            },
            "alpha_feature_summary": {"compression_events": 0, "trend_exhaustion_events": 0, "notes": []},
            "no_trade_periods": [],
            "observed_regimes": [],
            "regime_scan_table": _build_regime_scan_table(
                regimes_config=regimes_config,
                timeline=[],
                regime_counts=Counter(),
                transitions=[],
                current_id=None,
                previous_id=None,
                segments=[],
            ),
            "change_stats": _build_change_stats(
                segments=[],
                transitions=[],
                current_duration_minutes=0.0,
                bars_analyzed=0,
                bar_minutes=bar_minutes,
            ),
            "latest_observation_by_regime": {},
            "warnings": warnings or ["No bars available for regime analysis."],
        }

    timeline: list[dict[str, Any]] = []
    regime_counts: Counter[str] = Counter()
    quadrant_counts: Counter[str] = Counter()
    modifier_counts: Counter[str] = Counter()
    killzone_counts: Counter[str] = Counter()
    non_killzone_counts: Counter[str] = Counter()
    transitions: list[dict[str, Any]] = []
    spread_windows: list[dict[str, Any]] = []
    sweep_windows: list[dict[str, Any]] = []
    high_trap_windows: list[dict[str, Any]] = []
    no_trade_periods: list[dict[str, Any]] = []
    retail_stop_zone_counts: Counter[str] = Counter()
    compression_events = 0
    trend_exhaustion_events = 0
    trap_events = 0
    volume_spike_events = 0
    round_number_events = 0
    news_proxy_events = 0
    previous_entry: dict[str, Any] | None = None
    max_spread_percentile = 0.0

    for index in range(len(ordered)):
        window = ordered[max(0, index - 320) : index + 1]
        result = detect_regime_for_rows(window, symbol=symbol, timeframe=timeframe)
        result_dict = regime_to_dict(result)
        row = ordered[index]
        session = classify_session(row["time"], sessions_config)
        killzone = _is_killzone(row, sessions_config)
        entry = {
            "time": _row_time(row).isoformat(),
            "regime_id": result.regime_id,
            "base_regime": result.base_regime,
            "modifier": result.modifier,
            "confidence": result.confidence,
            "tradable": result.tradable,
            "risk_posture": result.risk_posture,
            "session": session.get("session"),
            "killzone": killzone,
            "spread": float(row.get("spread", 0) or 0),
            "close": float(row.get("close", 0) or 0),
            "features": result_dict.get("features", {}),
            "microstructure": (result_dict.get("features", {}).get("extra", {}) if result_dict.get("features") else {}),
            "reasons": result_dict.get("reasons", []),
        }
        timeline.append(entry)
        regime_counts[result.regime_id] += 1
        quadrant_counts[result.base_regime] += 1
        modifier_counts[result.modifier] += 1
        if killzone:
            killzone_counts[result.regime_id] += 1
        else:
            non_killzone_counts[result.regime_id] += 1
        features = result.features
        max_spread_percentile = max(max_spread_percentile, float(features.spread_percentile))
        if include_spread_filter and features.spread_percentile >= 90:
            spread_windows.append({"time": entry["time"], "regime_id": result.regime_id, "spread_percentile": round(features.spread_percentile, 2)})
        if include_sweep_detection and (features.sweep_high or features.sweep_low):
            sweep_windows.append({"time": entry["time"], "regime_id": result.regime_id, "sweep_high": features.sweep_high, "sweep_low": features.sweep_low})
        extra = features.extra or {}
        trap_score = float(extra.get("institutional_trap_score") or 0.0)
        if trap_score >= 60.0:
            trap_events += 1
            high_trap_windows.append(
                {
                    "time": entry["time"],
                    "regime_id": result.regime_id,
                    "trap_score": round(trap_score, 2),
                    "retail_stop_zones": extra.get("retail_stop_zones", []),
                    "sweep_direction": extra.get("liquidity_sweep_direction"),
                }
            )
        if extra.get("volume_spike"):
            volume_spike_events += 1
        if extra.get("near_round_number"):
            round_number_events += 1
        for zone in extra.get("retail_stop_zones", []):
            retail_stop_zone_counts[str(zone)] += 1
        news_proxy = extra.get("news_proxy") or {}
        if float(news_proxy.get("jump_z") or 0.0) >= 2.0 or float(news_proxy.get("spread_percentile") or 0.0) >= 90.0 or float(news_proxy.get("tick_volume_ratio") or 0.0) >= 2.0:
            news_proxy_events += 1
        if include_alpha_features and features.compression_percentile <= 25:
            compression_events += 1
        if include_alpha_features and result.modifier == "M11":
            trend_exhaustion_events += 1
        if not result.tradable:
            no_trade_periods.append({"time": entry["time"], "regime_id": result.regime_id, "reason": result.risk_posture})
        if previous_entry and previous_entry["regime_id"] != entry["regime_id"]:
            transitions.append(
                {
                    "from": previous_entry["regime_id"],
                    "to": entry["regime_id"],
                    "time": entry["time"],
                    "from_time": previous_entry["time"],
                    "to_time": entry["time"],
                }
            )
        previous_entry = entry

    current = timeline[-1]
    previous_regime = next((entry for entry in reversed(timeline[:-1]) if entry["regime_id"] != current["regime_id"]), None)
    active_since = current["time"]
    for entry in reversed(timeline):
        if entry["regime_id"] != current["regime_id"]:
            break
        active_since = entry["time"]
    segments = _build_segments(timeline, bar_minutes)
    current_duration_minutes = float(segments[-1]["duration_minutes"]) if segments else 0.0
    current["active_duration_minutes"] = round(current_duration_minutes, 2)
    current["latest_bar_time"] = current["time"]
    latest_by_regime: dict[str, dict[str, Any]] = {}
    for entry in timeline:
        latest_by_regime[entry["regime_id"]] = entry
    scan_table = _build_regime_scan_table(
        regimes_config=regimes_config,
        timeline=timeline,
        regime_counts=regime_counts,
        transitions=transitions,
        current_id=current["regime_id"],
        previous_id=previous_regime["regime_id"] if previous_regime else None,
        segments=segments,
    )
    change_stats = _build_change_stats(
        segments=segments,
        transitions=transitions,
        current_duration_minutes=current_duration_minutes,
        bars_analyzed=len(timeline),
        bar_minutes=bar_minutes,
    )

    observed_regimes = sorted(regime_counts)
    if not observed_regimes:
        warnings.append("No regime observed in selected period.")

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "current_regime": current,
        "previous_regime": previous_regime,
        "active_since": active_since,
        "active_duration_minutes": round(current_duration_minutes, 2),
        "bars_analyzed": len(timeline),
        "bars_by_regime": dict(regime_counts),
        "bars_by_quadrant": dict(quadrant_counts),
        "bars_by_modifier": dict(modifier_counts),
        "regime_timeline": timeline[-160:],
        "regime_transition_table": transitions,
        "regime_segments": segments[-120:],
        "regime_scan_table": scan_table,
        "change_stats": change_stats,
        "latest_observation_by_regime": latest_by_regime,
        "killzone_summary": {
            "enabled": killzone_enabled,
            "killzone_bars": sum(killzone_counts.values()),
            "non_killzone_bars": sum(non_killzone_counts.values()),
            "by_regime": dict(killzone_counts if killzone_enabled else non_killzone_counts),
        },
        "spread_summary": {"stress_bars": len(spread_windows), "max_spread_percentile": round(max_spread_percentile, 2), "windows": spread_windows[-25:]},
        "sweep_summary": {"events": len(sweep_windows), "windows": sweep_windows[-25:]},
        "institutional_summary": {
            "trap_events": trap_events,
            "volume_spike_events": volume_spike_events,
            "round_number_events": round_number_events,
            "retail_stop_zones": dict(retail_stop_zone_counts),
            "high_trap_windows": high_trap_windows[-25:],
            "news_proxy_events": news_proxy_events,
            "sentiment_status": "unavailable_without_feed",
        },
        "alpha_feature_summary": {
            "compression_events": compression_events,
            "trend_exhaustion_events": trend_exhaustion_events,
            "notes": ["trend alpha", "range alpha", "breakout alpha", "sweep alpha"] if include_alpha_features else [],
        },
        "no_trade_periods": no_trade_periods[-40:],
        "observed_regimes": observed_regimes,
        "warnings": warnings,
    }
