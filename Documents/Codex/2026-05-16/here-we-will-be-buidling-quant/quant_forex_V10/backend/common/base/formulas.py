from __future__ import annotations

import math

import numpy as np


def break_even_win_rate_no_cost(rr: float) -> float:
    return 1 / (1 + rr)


def break_even_win_rate_with_cost(avg_win_r: float, avg_loss_r: float) -> float:
    loss = abs(avg_loss_r)
    if avg_win_r <= 0 or loss <= 0:
        return 0.0
    return loss / (avg_win_r + loss)


def expectancy_r(win_rate: float, avg_win_r: float, loss_rate: float, avg_loss_r: float, avg_cost_r: float) -> float:
    return (win_rate * avg_win_r) - (loss_rate * abs(avg_loss_r)) - avg_cost_r


def profit_factor(gross_profit: float, gross_loss: float) -> float:
    loss = abs(gross_loss)
    if loss == 0:
        return 999.0 if gross_profit > 0 else 0.0
    return gross_profit / loss


def losing_streak_probability(loss_rate: float, streak: int) -> float:
    return loss_rate**streak


def linear_regression_slope(values: list[float] | np.ndarray) -> float:
    cleaned = np.asarray(values, dtype=float)
    cleaned = cleaned[~np.isnan(cleaned)]
    if len(cleaned) < 2:
        return math.nan
    x = np.arange(len(cleaned), dtype=float)
    return float(np.polyfit(x, cleaned, 1)[0])


def channel_position(close: float, channel_lower: float, channel_upper: float) -> float:
    width = channel_upper - channel_lower
    if width == 0:
        return math.nan
    return (close - channel_lower) / width


def near_range_high(high: float, previous_swing_high: float, atr: float, tolerance_atr: float = 0.20) -> bool:
    return high >= previous_swing_high - atr * tolerance_atr


def near_range_low(low: float, previous_swing_low: float, atr: float, tolerance_atr: float = 0.20) -> bool:
    return low <= previous_swing_low + atr * tolerance_atr


def false_upside_breakout(previous_close: float, previous_swing_high: float, close: float, upper_wick_ratio: float) -> bool:
    return previous_close > previous_swing_high and close < previous_swing_high and upper_wick_ratio >= 0.35


def false_downside_breakout(previous_close: float, previous_swing_low: float, close: float, lower_wick_ratio: float) -> bool:
    return previous_close < previous_swing_low and close > previous_swing_low and lower_wick_ratio >= 0.35


def count_crosses(values: list[float] | np.ndarray, reference: list[float] | np.ndarray) -> int:
    lhs = np.asarray(values, dtype=float)
    rhs = np.asarray(reference, dtype=float)
    if len(lhs) != len(rhs) or len(lhs) < 2:
        return 0
    signs = np.sign(lhs - rhs)
    return int(np.nansum(np.abs(np.diff(signs)) > 0))


def chop_score(adx: float, er: float, atr_percentile: float, ema50_cross_count: float, candle_range_atr: float) -> int:
    return int(adx <= 18) + int(er <= 0.20) + int(atr_percentile >= 75) + int(ema50_cross_count >= 4) + int(candle_range_atr >= 1.2)


def dead_market_score(atr_percentile: float, bb_width_percentile: float, adx: float, candle_range_atr: float) -> int:
    return int(atr_percentile < 15) + int(bb_width_percentile < 15) + int(adx < 15) + int(candle_range_atr < 0.70)


def is_month_end(day_of_month: int, start_day: int = 25) -> bool:
    return day_of_month >= start_day


def is_fixing_window(hour: int, minute: int) -> bool:
    minutes = hour * 60 + minute
    return 15 * 60 <= minutes <= 16 * 60 + 15


def adx_slope(adx: float, adx_5_bars_ago: float) -> float:
    return adx - adx_5_bars_ago


def er_slope(er: float, er_5_bars_ago: float) -> float:
    return er - er_5_bars_ago


def ema_slope_change(ema_slope: float, ema_slope_5_bars_ago: float) -> float:
    return ema_slope - ema_slope_5_bars_ago


def trend_weakening(adx_slope: float, er_slope: float) -> bool:
    return adx_slope < 0 and er_slope < 0


def pullback_failure_bullish(htf_bias: str, close: float, open_price: float, ema20: float, plus_di: float, minus_di: float, er_slope: float) -> bool:
    return htf_bias == "bullish" and close < ema20 and close < open_price and plus_di > minus_di and er_slope < 0


def pullback_failure_bearish(htf_bias: str, close: float, open_price: float, ema20: float, plus_di: float, minus_di: float, er_slope: float) -> bool:
    return htf_bias == "bearish" and close > ema20 and close > open_price and minus_di > plus_di and er_slope < 0


def mtf_conflict_score(htf_bias: str, ltf_bias: str, adx: float, er: float, ema50_cross_count: float) -> int:
    return int(htf_bias != ltf_bias) + int(adx < 18) + int(er < 0.25) + int(ema50_cross_count >= 3)


def session_vwap(cumulative_typical_price_volume: float, cumulative_volume: float) -> float:
    if cumulative_volume == 0:
        return math.nan
    return cumulative_typical_price_volume / cumulative_volume


def distance_from_vwap_atr(close: float, session_vwap: float, atr: float) -> float:
    if atr == 0:
        return math.nan
    return (close - session_vwap) / atr


def vwap_extreme_high(distance_from_vwap_atr: float, threshold_atr: float = 1.5) -> bool:
    return distance_from_vwap_atr >= threshold_atr


def vwap_extreme_low(distance_from_vwap_atr: float, threshold_atr: float = 1.5) -> bool:
    return distance_from_vwap_atr <= -threshold_atr


def post_stress_normalization(spread_was_stressed: bool, spread_percentile: float, candle_range_atr: float) -> bool:
    return spread_was_stressed and spread_percentile < 70 and candle_range_atr < 2.0


def gap_size(open_price: float, previous_close: float) -> float:
    return abs(open_price - previous_close)


def gap_atr(open_price: float, previous_close: float, atr: float) -> float:
    if atr == 0:
        return math.nan
    return abs(open_price - previous_close) / atr


def gap_fill_percent(open_price: float, close: float, previous_close: float) -> float:
    gap = abs(open_price - previous_close)
    if gap == 0:
        return 0.0
    return abs(close - open_price) / gap


def missing_ohlc(open_price: float | None, high: float | None, low: float | None, close: float | None) -> bool:
    return any(value is None for value in [open_price, high, low, close])


def invalid_ohlc(open_price: float, high: float, low: float, close: float) -> bool:
    return high < low or close > high or close < low or open_price > high or open_price < low


def zero_range(high: float, low: float) -> bool:
    return high == low
