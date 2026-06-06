from __future__ import annotations

import math
from typing import Any

import pandas as pd

from backend.common.config_loader import load_strategies, load_thresholds
from backend.common.modifiers.modifier_engine import detect_modifiers


STRATEGIES = {item["strategy_id"]: item for item in load_strategies()}
THRESHOLDS = load_thresholds()


def _num(row: dict[str, Any] | pd.Series, key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _recent_break_above(df: pd.DataFrame, idx: int, level_col: str, lookback: int = 5) -> bool:
    start = max(0, idx - lookback)
    section = df.iloc[start:idx]
    if section.empty:
        return False
    return bool((section["close"] > section[level_col]).any())


def _recent_break_below(df: pd.DataFrame, idx: int, level_col: str, lookback: int = 5) -> bool:
    start = max(0, idx - lookback)
    section = df.iloc[start:idx]
    if section.empty:
        return False
    return bool((section["close"] < section[level_col]).any())


def _recent_break_above_level(df: pd.DataFrame, idx: int, level: float, lookback: int = 5) -> bool:
    if level <= 0:
        return False
    start = max(0, idx - lookback)
    return bool((df.iloc[start:idx]["close"] > level).any())


def _recent_break_below_level(df: pd.DataFrame, idx: int, level: float, lookback: int = 5) -> bool:
    if level <= 0:
        return False
    start = max(0, idx - lookback)
    return bool((df.iloc[start:idx]["close"] < level).any())


def _compression_box(df: pd.DataFrame, idx: int, lookback: int = 20) -> tuple[float, float, bool]:
    start = max(0, idx - lookback)
    section = df.iloc[start:idx]
    compressed = bool((section.get("compression_flag", pd.Series(dtype=float)) == 1).any()) if not section.empty else False
    if section.empty:
        return 0.0, 0.0, False
    return float(section["high"].max()), float(section["low"].min()), compressed


def _recent_high(df: pd.DataFrame, idx: int, lookback: int = 5) -> float:
    section = df.iloc[max(0, idx - lookback): idx + 1]
    return float(section["high"].max()) if not section.empty else 0.0


def _recent_low(df: pd.DataFrame, idx: int, lookback: int = 5) -> float:
    section = df.iloc[max(0, idx - lookback): idx + 1]
    return float(section["low"].min()) if not section.empty else 0.0


def _recent_flag(df: pd.DataFrame, idx: int, flag_col: str, lookback: int = 5) -> bool:
    if flag_col not in df:
        return False
    section = df.iloc[max(0, idx - lookback): idx + 1]
    return bool((pd.to_numeric(section[flag_col], errors="coerce").fillna(0) == 1).any())


def _range_high_low(df: pd.DataFrame, idx: int, lookback: int = 20) -> tuple[float, float]:
    section = df.iloc[max(0, idx - lookback):idx]
    if section.empty:
        return 0.0, 0.0
    return float(section["high"].max()), float(section["low"].min())


def _last_event_extreme(df: pd.DataFrame, idx: int, flag_col: str, extreme_col: str, lookback: int = 5) -> float:
    if flag_col not in df or extreme_col not in df:
        return 0.0
    section = df.iloc[max(0, idx - lookback): idx + 1]
    events = section[pd.to_numeric(section[flag_col], errors="coerce").fillna(0) == 1]
    if events.empty:
        return 0.0
    return float(events.iloc[-1][extreme_col])


def _usd_direction(symbol: str, usd_bias: str) -> str | None:
    symbol = symbol.upper()
    if "USD" not in symbol:
        return None
    if usd_bias == "USD_BULLISH":
        if symbol.startswith("USD"):
            return "long"
        if symbol.endswith("USD"):
            return "short"
    if usd_bias == "USD_BEARISH":
        if symbol.startswith("USD"):
            return "short"
        if symbol.endswith("USD"):
            return "long"
    return None


def _cb_direction(cb_divergence: str) -> str | None:
    if cb_divergence == "BULLISH_BASE":
        return "long"
    if cb_divergence == "BEARISH_BASE":
        return "short"
    return None


def _pullback_signal(row: pd.Series, strategy_id: str, direction: str, entry: float, atr: float, rr: float, buffer: float = 0.35) -> dict[str, Any]:
    if direction == "long":
        conditions = [_num(row, "low") <= _num(row, "ema20") + atr * buffer, _num(row, "close") > _num(row, "ema20"), _num(row, "close") > _num(row, "open")]
        if all(conditions):
            sl = min(_num(row, "low"), _num(row, "ema20")) - atr * buffer
            return _signal_payload(row, strategy_id, "long", entry, sl, entry + (entry - sl) * rr, f"{STRATEGIES[strategy_id]['strategy_name']} pullback long triggered.")
    if direction == "short":
        conditions = [_num(row, "high") >= _num(row, "ema20") - atr * buffer, _num(row, "close") < _num(row, "ema20"), _num(row, "close") < _num(row, "open")]
        if all(conditions):
            sl = max(_num(row, "high"), _num(row, "ema20")) + atr * buffer
            return _signal_payload(row, strategy_id, "short", entry, sl, entry - (sl - entry) * rr, f"{STRATEGIES[strategy_id]['strategy_name']} pullback short triggered.")
    return {"triggered": False, "reason": f"{strategy_id} pullback conditions are not met."}


def _breakout_retest_signal(df: pd.DataFrame, idx: int, row: pd.Series, strategy_id: str, direction: str, entry: float, atr: float, rr: float, level: float, buffer: float = 0.50) -> dict[str, Any]:
    if direction == "long":
        conditions = [_recent_break_above_level(df, idx, level, 5), _num(row, "low") <= level + atr * 0.25, _num(row, "close") > level]
        if all(conditions):
            sl = level - atr * buffer
            return _signal_payload(row, strategy_id, "long", entry, sl, entry + (entry - sl) * rr, f"{STRATEGIES[strategy_id]['strategy_name']} breakout retest long triggered.")
    if direction == "short":
        conditions = [_recent_break_below_level(df, idx, level, 5), _num(row, "high") >= level - atr * 0.25, _num(row, "close") < level]
        if all(conditions):
            sl = level + atr * buffer
            return _signal_payload(row, strategy_id, "short", entry, sl, entry - (sl - entry) * rr, f"{STRATEGIES[strategy_id]['strategy_name']} breakout retest short triggered.")
    return {"triggered": False, "reason": f"{strategy_id} breakout-retest conditions are not met."}


def _signal_payload(row: pd.Series, strategy_id: str, direction: str, entry: float, sl: float, tp: float, reason: str) -> dict[str, Any]:
    strategy = STRATEGIES[strategy_id]
    risk_distance = entry - sl if direction == "long" else sl - entry
    if risk_distance <= 0:
        return {"triggered": False, "reason": "Invalid risk distance; SL is not beyond entry."}
    return {
        "triggered": True,
        "strategy_id": strategy_id,
        "strategy_name": strategy["strategy_name"],
        "direction": direction,
        "entry": float(entry),
        "sl": float(sl),
        "tp": float(tp),
        "risk_distance": float(risk_distance),
        "reason": reason,
    }


def evaluate_strategy(df: pd.DataFrame, idx: int, strategy_id: str, rr: float) -> dict[str, Any]:
    row = df.iloc[idx]
    entry = _num(row, "close")
    atr = _num(row, "atr")
    if atr <= 0:
        return {"triggered": False, "reason": "ATR is missing or zero."}

    if strategy_id == "T1":
        conditions = [
            row.get("regime_id") == "R01",
            _num(row, "low") <= _num(row, "ema20") + atr * 0.35,
            _num(row, "close") > _num(row, "ema20"),
            _num(row, "close") > _num(row, "open"),
            _num(row, "distance_from_ema20_atr") < 2.5,
        ]
        if all(conditions):
            sl = min(_num(row, "low"), _num(row, "ema20")) - atr * 0.30
            return _signal_payload(row, "T1", "long", entry, sl, entry + (entry - sl) * rr, "EMA20 pullback buy triggered in R01.")
    if strategy_id == "T2":
        conditions = [
            row.get("regime_id") == "R01",
            _num(row, "low") <= _num(row, "ema50") + atr * 0.35,
            _num(row, "close") > _num(row, "ema50"),
            _num(row, "close") > _num(row, "open"),
        ]
        if all(conditions):
            sl = min(_num(row, "low"), _num(row, "ema50")) - atr * 0.35
            return _signal_payload(row, "T2", "long", entry, sl, entry + (entry - sl) * rr, "EMA50 deep pullback buy triggered in R01.")
    if strategy_id == "T3":
        level = _num(row, "prev_swing_high")
        conditions = [
            row.get("regime_id") == "R01",
            _recent_break_above(df, idx, "prev_swing_high"),
            _num(row, "low") <= level + atr * 0.25,
            _num(row, "close") > level,
            row.get("htf_bias") != "bearish",
        ]
        if all(conditions):
            sl = level - atr * 0.35
            return _signal_payload(row, "T3", "long", entry, sl, entry + (entry - sl) * rr, "Bullish break-retest triggered in R01.")

    if strategy_id == "T4":
        conditions = [
            row.get("regime_id") == "R02",
            _num(row, "high") >= _num(row, "ema20") - atr * 0.35,
            _num(row, "close") < _num(row, "ema20"),
            _num(row, "close") < _num(row, "open"),
            _num(row, "distance_from_ema20_atr") > -2.5,
        ]
        if all(conditions):
            sl = max(_num(row, "high"), _num(row, "ema20")) + atr * 0.30
            return _signal_payload(row, "T4", "short", entry, sl, entry - (sl - entry) * rr, "EMA20 pullback sell triggered in R02.")
    if strategy_id == "T5":
        conditions = [
            row.get("regime_id") == "R02",
            _num(row, "high") >= _num(row, "ema50") - atr * 0.35,
            _num(row, "close") < _num(row, "ema50"),
            _num(row, "close") < _num(row, "open"),
        ]
        if all(conditions):
            sl = max(_num(row, "high"), _num(row, "ema50")) + atr * 0.35
            return _signal_payload(row, "T5", "short", entry, sl, entry - (sl - entry) * rr, "EMA50 deep pullback sell triggered in R02.")
    if strategy_id == "T6":
        level = _num(row, "prev_swing_low")
        conditions = [
            row.get("regime_id") == "R02",
            _recent_break_below(df, idx, "prev_swing_low"),
            _num(row, "high") >= level - atr * 0.25,
            _num(row, "close") < level,
            row.get("htf_bias") != "bullish",
        ]
        if all(conditions):
            sl = level + atr * 0.35
            return _signal_payload(row, "T6", "short", entry, sl, entry - (sl - entry) * rr, "Bearish break-retest triggered in R02.")

    if strategy_id == "R1":
        level = _num(row, "prev_swing_high")
        conditions = [
            row.get("regime_id") == "R03",
            _num(row, "high") >= level - atr * 0.20,
            _num(row, "upper_wick_ratio") >= 0.35,
            _num(row, "close") < level,
            row.get("htf_bias") != "bullish",
        ]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.25
            tp = _num(row, "range_midpoint") or entry - (sl - entry) * 1.5
            return _signal_payload(row, "R1", "short", entry, sl, tp, "Range high fade short triggered in R03.")
    if strategy_id == "R2":
        level = _num(row, "prev_swing_low")
        conditions = [
            row.get("regime_id") == "R03",
            _num(row, "low") <= level + atr * 0.20,
            _num(row, "lower_wick_ratio") >= 0.35,
            _num(row, "close") > level,
            row.get("htf_bias") != "bearish",
        ]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.25
            tp = _num(row, "range_midpoint") or entry + (entry - sl) * 1.5
            return _signal_payload(row, "R2", "long", entry, sl, tp, "Range low fade long triggered in R03.")
    if strategy_id == "S1":
        conditions = [
            row.get("regime_id") == "R03",
            bool(row.get("sweep_high_flag")),
            _num(row, "close") < _num(row, "prev_swing_high"),
            _num(row, "spread_percentile") < 70,
        ]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.25
            tp = _num(row, "range_midpoint") or entry - (sl - entry) * rr
            return _signal_payload(row, "S1", "short", entry, sl, tp, "Liquidity sweep high short triggered in R03.")
    if strategy_id == "S2":
        conditions = [
            row.get("regime_id") == "R03",
            bool(row.get("sweep_low_flag")),
            _num(row, "close") > _num(row, "prev_swing_low"),
            _num(row, "spread_percentile") < 70,
        ]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.25
            tp = _num(row, "range_midpoint") or entry + (entry - sl) * rr
            return _signal_payload(row, "S2", "long", entry, sl, tp, "Liquidity sweep low long triggered in R03.")

    if strategy_id == "B1":
        level = _num(row, "prev_swing_high")
        conditions = [
            row.get("regime_id") == "R04",
            _recent_break_above(df, idx, "prev_swing_high", 5),
            _num(row, "low") <= level + atr * 0.25,
            _num(row, "close") > level,
            bool(row.get("volatility_expansion_flag")),
            _num(row, "spread_percentile") < 80,
        ]
        if all(conditions):
            sl = level - atr * 0.50
            return _signal_payload(row, "B1", "long", entry, sl, entry + (entry - sl) * rr, "True upside breakout retest buy triggered in R04.")
    if strategy_id == "B2":
        level = _num(row, "prev_day_high")
        conditions = [
            row.get("regime_id") == "R04",
            _recent_break_above_level(df, idx, level, 5),
            _num(row, "low") <= level + atr * 0.25,
            _num(row, "close") > level,
            row.get("htf_bias") == "bullish",
        ]
        if all(conditions):
            sl = level - atr * 0.50
            return _signal_payload(row, "B2", "long", entry, sl, entry + (entry - sl) * rr, "Previous day high breakout retest buy triggered in R04.")
    if strategy_id == "B3":
        conditions = [
            row.get("regime_id") == "R04",
            bool(row.get("volatility_expansion_flag")),
            _num(row, "close") > _num(row, "ema20"),
            _num(row, "low") <= _num(row, "ema20") + atr * 0.50,
            _num(row, "close") > _num(row, "open"),
        ]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.50
            return _signal_payload(row, "B3", "long", entry, sl, entry + (entry - sl) * rr, "Volatility expansion pullback buy triggered in R04.")

    if strategy_id == "B4":
        level = _num(row, "prev_swing_low")
        conditions = [
            row.get("regime_id") == "R05",
            _recent_break_below(df, idx, "prev_swing_low", 5),
            _num(row, "high") >= level - atr * 0.25,
            _num(row, "close") < level,
            bool(row.get("volatility_expansion_flag")),
            _num(row, "spread_percentile") < 80,
        ]
        if all(conditions):
            sl = level + atr * 0.50
            return _signal_payload(row, "B4", "short", entry, sl, entry - (sl - entry) * rr, "True downside breakout retest sell triggered in R05.")
    if strategy_id == "B5":
        level = _num(row, "prev_day_low")
        conditions = [
            row.get("regime_id") == "R05",
            _recent_break_below_level(df, idx, level, 5),
            _num(row, "high") >= level - atr * 0.25,
            _num(row, "close") < level,
            row.get("htf_bias") == "bearish",
        ]
        if all(conditions):
            sl = level + atr * 0.50
            return _signal_payload(row, "B5", "short", entry, sl, entry - (sl - entry) * rr, "Previous day low breakout retest sell triggered in R05.")
    if strategy_id == "B6":
        conditions = [
            row.get("regime_id") == "R05",
            bool(row.get("volatility_expansion_flag")),
            _num(row, "close") < _num(row, "ema20"),
            _num(row, "high") >= _num(row, "ema20") - atr * 0.50,
            _num(row, "close") < _num(row, "open"),
        ]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.50
            return _signal_payload(row, "B6", "short", entry, sl, entry - (sl - entry) * rr, "Volatility expansion pullback sell triggered in R05.")

    compression_high, compression_low, compression_recent = _compression_box(df, idx, 20)
    bb_rising = _num(row, "bb_width_percentile") > _num(df.iloc[idx - 1], "bb_width_percentile") if idx > 0 else False
    if strategy_id == "C1":
        conditions = [
            row.get("regime_id") == "R06",
            compression_recent,
            _num(row, "close") > compression_high + atr * 0.10,
            bb_rising,
            _num(row, "candle_range_atr") >= 1.0,
            _num(row, "spread_percentile") < 70,
        ]
        if all(conditions):
            sl = compression_high - atr * 0.40
            return _signal_payload(row, "C1", "long", entry, sl, entry + (entry - sl) * rr, "Compression upside breakout buy triggered in R06.")
    if strategy_id == "C2":
        conditions = [
            row.get("regime_id") == "R06",
            compression_recent,
            _num(row, "close") < compression_low - atr * 0.10,
            bb_rising,
            _num(row, "candle_range_atr") >= 1.0,
            _num(row, "spread_percentile") < 70,
        ]
        if all(conditions):
            sl = compression_low + atr * 0.40
            return _signal_payload(row, "C2", "short", entry, sl, entry - (sl - entry) * rr, "Compression downside breakout sell triggered in R06.")
    if strategy_id == "C3":
        recent_high = float(df.iloc[max(0, idx - 5):idx + 1]["high"].max())
        conditions = [
            row.get("regime_id") == "R06",
            _recent_break_above_level(df, idx, compression_high, 5),
            _num(row, "close") < compression_high,
            _num(row, "upper_wick_ratio") >= 0.35,
            _num(row, "spread_percentile") < 70,
        ]
        if all(conditions):
            sl = recent_high + atr * 0.25
            tp = _num(row, "range_midpoint") or entry - (sl - entry) * 1.5
            return _signal_payload(row, "C3", "short", entry, sl, tp, "Failed upside compression breakout short triggered in R06.")
    if strategy_id == "C4":
        recent_low = float(df.iloc[max(0, idx - 5):idx + 1]["low"].min())
        conditions = [
            row.get("regime_id") == "R06",
            _recent_break_below_level(df, idx, compression_low, 5),
            _num(row, "close") > compression_low,
            _num(row, "lower_wick_ratio") >= 0.35,
            _num(row, "spread_percentile") < 70,
        ]
        if all(conditions):
            sl = recent_low - atr * 0.25
            tp = _num(row, "range_midpoint") or entry + (entry - sl) * 1.5
            return _signal_payload(row, "C4", "long", entry, sl, tp, "Failed downside compression breakout long triggered in R06.")

    if strategy_id == "E1":
        conditions = [
            row.get("regime_id") == "R07",
            _num(row, "high") > _num(row, "prev_swing_high"),
            _num(row, "close") < _num(row, "prev_swing_high"),
            _num(row, "upper_wick_ratio") >= 0.45,
            _num(row, "distance_from_ema20_atr") >= 2.5,
            _num(row, "spread_percentile") < 80,
        ]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.25
            tp = _num(row, "ema20") if _num(row, "ema20") < entry else (_num(row, "range_midpoint") or entry - (sl - entry) * rr)
            return _signal_payload(row, "E1", "short", entry, sl, tp, "Exhaustion sweep high short triggered in R07.")
    if strategy_id == "E2":
        level = _num(row, "prev_swing_high")
        recent_high = float(df.iloc[max(0, idx - 3):idx + 1]["high"].max())
        conditions = [
            row.get("regime_id") == "R07",
            _recent_break_above_level(df, idx, level, 3),
            _num(row, "close") < level,
            _num(row, "close") < _num(row, "open"),
        ]
        if all(conditions):
            sl = recent_high + atr * 0.30
            return _signal_payload(row, "E2", "short", entry, sl, entry - (sl - entry) * rr, "Failed high reclaim short triggered in R07.")
    if strategy_id == "E3":
        conditions = [
            row.get("regime_id") == "R08",
            _num(row, "low") < _num(row, "prev_swing_low"),
            _num(row, "close") > _num(row, "prev_swing_low"),
            _num(row, "lower_wick_ratio") >= 0.45,
            _num(row, "distance_from_ema20_atr") <= -2.5,
            _num(row, "spread_percentile") < 80,
        ]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.25
            tp = _num(row, "ema20") if _num(row, "ema20") > entry else (_num(row, "range_midpoint") or entry + (entry - sl) * rr)
            return _signal_payload(row, "E3", "long", entry, sl, tp, "Exhaustion sweep low long triggered in R08.")
    if strategy_id == "E4":
        level = _num(row, "prev_swing_low")
        recent_low = float(df.iloc[max(0, idx - 3):idx + 1]["low"].min())
        conditions = [
            row.get("regime_id") == "R08",
            _recent_break_below_level(df, idx, level, 3),
            _num(row, "close") > level,
            _num(row, "close") > _num(row, "open"),
        ]
        if all(conditions):
            sl = recent_low - atr * 0.30
            return _signal_payload(row, "E4", "long", entry, sl, entry + (entry - sl) * rr, "Failed low reclaim long triggered in R08.")

    if strategy_id == "N1":
        return {"triggered": False, "reason": "Post-news continuation needs a real news feed/recent-news state; placeholder is reference-only for now."}
    if strategy_id == "N2":
        sweep_high = _num(row, "high") > _num(row, "prev_swing_high") and _num(row, "close") < _num(row, "prev_swing_high") and _num(row, "upper_wick_ratio") >= 0.45 and _num(row, "spread_percentile") < 80
        sweep_low = _num(row, "low") < _num(row, "prev_swing_low") and _num(row, "close") > _num(row, "prev_swing_low") and _num(row, "lower_wick_ratio") >= 0.45 and _num(row, "spread_percentile") < 80
        if row.get("regime_id") == "R09" and sweep_high:
            sl = _num(row, "high") + atr * 0.30
            tp = _num(row, "range_midpoint") or entry - (sl - entry) * rr
            return _signal_payload(row, "N2", "short", entry, sl, tp, "Post-news reversal sweep high short triggered in R09.")
        if row.get("regime_id") == "R09" and sweep_low:
            sl = _num(row, "low") - atr * 0.30
            tp = _num(row, "range_midpoint") or entry + (entry - sl) * rr
            return _signal_payload(row, "N2", "long", entry, sl, tp, "Post-news reversal sweep low long triggered in R09.")

    low_vol_rr = min(rr, 1.5)
    if strategy_id == "L1":
        conditions = [
            row.get("regime_id") == "R11",
            _num(row, "low") <= _num(row, "ema20") + atr * 0.25,
            _num(row, "close") > _num(row, "ema20"),
            _num(row, "close") > _num(row, "open"),
            _num(row, "distance_from_ema20_atr") < 2.0,
        ]
        if all(conditions):
            sl = min(_num(row, "low"), _num(row, "ema20")) - atr * 0.25
            return _signal_payload(row, "L1", "long", entry, sl, entry + (entry - sl) * low_vol_rr, "Low-vol EMA20 drift buy triggered in R11.")
    if strategy_id == "L2":
        recent_high = _recent_high(df, idx, 3)
        recent_low = _recent_low(df, idx, 10)
        conditions = [
            row.get("regime_id") == "R11",
            _num(row, "low") > _num(row, "prev_swing_low"),
            _num(row, "close") >= recent_high,
            _num(row, "close") > _num(row, "ema20"),
            _num(row, "ema_slope") > 0,
        ]
        if all(conditions):
            sl = recent_low - atr * 0.25
            return _signal_payload(row, "L2", "long", entry, sl, entry + (entry - sl) * low_vol_rr, "Low-vol higher-low buy triggered in R11.")
    if strategy_id == "L3":
        level = _num(row, "prev_swing_high")
        conditions = [
            row.get("regime_id") == "R11",
            _recent_break_above(df, idx, "prev_swing_high", 5),
            _num(row, "low") <= level + atr * 0.25,
            _num(row, "close") > level,
            _num(row, "candle_range_atr") < 1.2,
            _num(row, "spread_percentile") < 70,
        ]
        if all(conditions):
            sl = level - atr * 0.30
            return _signal_payload(row, "L3", "long", entry, sl, entry + (entry - sl) * low_vol_rr, "Low-vol break-retest buy triggered in R11.")
    if strategy_id == "L4":
        conditions = [
            row.get("regime_id") == "R12",
            _num(row, "high") >= _num(row, "ema20") - atr * 0.25,
            _num(row, "close") < _num(row, "ema20"),
            _num(row, "close") < _num(row, "open"),
            _num(row, "distance_from_ema20_atr") > -2.0,
        ]
        if all(conditions):
            sl = max(_num(row, "high"), _num(row, "ema20")) + atr * 0.25
            return _signal_payload(row, "L4", "short", entry, sl, entry - (sl - entry) * low_vol_rr, "Low-vol EMA20 drift sell triggered in R12.")
    if strategy_id == "L5":
        recent_high = _recent_high(df, idx, 10)
        recent_low = _recent_low(df, idx, 3)
        conditions = [
            row.get("regime_id") == "R12",
            _num(row, "high") < _num(row, "prev_swing_high"),
            _num(row, "close") <= recent_low,
            _num(row, "close") < _num(row, "ema20"),
            _num(row, "ema_slope") < 0,
        ]
        if all(conditions):
            sl = recent_high + atr * 0.25
            return _signal_payload(row, "L5", "short", entry, sl, entry - (sl - entry) * low_vol_rr, "Low-vol lower-high sell triggered in R12.")
    if strategy_id == "L6":
        level = _num(row, "prev_swing_low")
        conditions = [
            row.get("regime_id") == "R12",
            _recent_break_below(df, idx, "prev_swing_low", 5),
            _num(row, "high") >= level - atr * 0.25,
            _num(row, "close") < level,
            _num(row, "candle_range_atr") < 1.2,
            _num(row, "spread_percentile") < 70,
        ]
        if all(conditions):
            sl = level + atr * 0.30
            return _signal_payload(row, "L6", "short", entry, sl, entry - (sl - entry) * low_vol_rr, "Low-vol break-retest sell triggered in R12.")

    if strategy_id == "CH1":
        conditions = [row.get("regime_id") == "R13", _num(row, "channel_position") <= 0.25, _num(row, "close") > _num(row, "channel_lower"), _num(row, "close") > _num(row, "open"), _num(row, "spread_percentile") < 70]
        if all(conditions):
            sl = _num(row, "channel_lower") - atr * 0.35
            tp = _num(row, "channel_mid") if _num(row, "channel_mid") > entry else entry + (entry - sl) * rr
            return _signal_payload(row, "CH1", "long", entry, sl, tp, "Channel support buy triggered in R13; approximation uses 50-bar regression channel.")
    if strategy_id == "CH2":
        conditions = [row.get("regime_id") == "R13", _num(row, "low") <= _num(row, "ema20") + atr * 0.25, _num(row, "channel_position") <= 0.35, _num(row, "close") > _num(row, "ema20"), _num(row, "close") > _num(row, "open")]
        if all(conditions):
            sl = min(_num(row, "channel_lower"), _num(row, "ema20"), _num(row, "low")) - atr * 0.35
            tp = _num(row, "channel_upper") if _num(row, "channel_upper") > entry else entry + (entry - sl) * rr
            return _signal_payload(row, "CH2", "long", entry, sl, tp, "EMA20 and channel support confluence buy triggered in R13.")
    if strategy_id == "CH3":
        level = _num(row, "channel_upper")
        adx_rising = _num(row, "adx") > _num(df.iloc[idx - 1], "adx") if idx > 0 else False
        conditions = [row.get("regime_id") == "R13", _recent_break_above_level(df, idx, level, 5), _num(row, "low") <= level + atr * 0.25, _num(row, "close") > level, adx_rising, _num(row, "er") >= 0.25]
        if all(conditions):
            sl = level - atr * 0.40
            return _signal_payload(row, "CH3", "long", entry, sl, entry + (entry - sl) * rr, "Channel breakout retest buy triggered in R13.")
    if strategy_id == "CH4":
        conditions = [row.get("regime_id") == "R14", _num(row, "channel_position") >= 0.75, _num(row, "close") < _num(row, "channel_upper"), _num(row, "close") < _num(row, "open"), _num(row, "spread_percentile") < 70]
        if all(conditions):
            sl = _num(row, "channel_upper") + atr * 0.35
            tp = _num(row, "channel_mid") if _num(row, "channel_mid") < entry else entry - (sl - entry) * rr
            return _signal_payload(row, "CH4", "short", entry, sl, tp, "Channel resistance sell triggered in R14; approximation uses 50-bar regression channel.")
    if strategy_id == "CH5":
        conditions = [row.get("regime_id") == "R14", _num(row, "high") >= _num(row, "ema20") - atr * 0.25, _num(row, "channel_position") >= 0.65, _num(row, "close") < _num(row, "ema20"), _num(row, "close") < _num(row, "open")]
        if all(conditions):
            sl = max(_num(row, "channel_upper"), _num(row, "ema20"), _num(row, "high")) + atr * 0.35
            tp = _num(row, "channel_lower") if _num(row, "channel_lower") < entry else entry - (sl - entry) * rr
            return _signal_payload(row, "CH5", "short", entry, sl, tp, "EMA20 and channel resistance confluence sell triggered in R14.")
    if strategy_id == "CH6":
        level = _num(row, "channel_lower")
        adx_rising = _num(row, "adx") > _num(df.iloc[idx - 1], "adx") if idx > 0 else False
        conditions = [row.get("regime_id") == "R14", _recent_break_below_level(df, idx, level, 5), _num(row, "high") >= level - atr * 0.25, _num(row, "close") < level, adx_rising, _num(row, "er") >= 0.25]
        if all(conditions):
            sl = level + atr * 0.40
            return _signal_payload(row, "CH6", "short", entry, sl, entry - (sl - entry) * rr, "Channel breakdown retest sell triggered in R14.")

    if strategy_id in {"RH1", "R1"}:
        level = _num(row, "prev_swing_high")
        expected_regime = "R15" if strategy_id == "RH1" else "R03"
        conditions = [row.get("regime_id") == expected_regime, _num(row, "high") >= level - atr * 0.20, _num(row, "upper_wick_ratio") >= 0.35, _num(row, "close") < level, row.get("htf_bias") != "bullish"]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.25
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") < entry else entry - (sl - entry) * 1.5
            return _signal_payload(row, strategy_id, "short", entry, sl, tp, "Range high rejection short triggered.")
    if strategy_id == "RH2":
        conditions = [row.get("regime_id") == "R15", _num(row, "high") >= _num(row, "bb_upper"), _num(row, "close") < _num(row, "bb_upper"), _num(row, "adx") <= 18, _num(row, "upper_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.25
            tp = _num(row, "bb_basis", _num(row, "range_midpoint")) or entry - (sl - entry) * 1.5
            return _signal_payload(row, "RH2", "short", entry, sl, tp, "Upper Bollinger fade short triggered in R15.")
    if strategy_id == "RH3":
        level = _num(row, "prev_swing_high")
        conditions = [row.get("regime_id") == "R15", _recent_break_above_level(df, idx, level, 3), _num(row, "close") < level, _num(row, "upper_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _recent_high(df, idx, 3) + atr * 0.30
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") < entry else entry - (sl - entry) * 1.5
            return _signal_payload(row, "RH3", "short", entry, sl, tp, "Range high failed hold short triggered in R15.")
    if strategy_id in {"RL1", "R2"}:
        level = _num(row, "prev_swing_low")
        expected_regime = "R16" if strategy_id == "RL1" else "R03"
        conditions = [row.get("regime_id") == expected_regime, _num(row, "low") <= level + atr * 0.20, _num(row, "lower_wick_ratio") >= 0.35, _num(row, "close") > level, row.get("htf_bias") != "bearish"]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.25
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") > entry else entry + (entry - sl) * 1.5
            return _signal_payload(row, strategy_id, "long", entry, sl, tp, "Range low rejection long triggered.")
    if strategy_id == "RL2":
        conditions = [row.get("regime_id") == "R16", _num(row, "low") <= _num(row, "bb_lower"), _num(row, "close") > _num(row, "bb_lower"), _num(row, "adx") <= 18, _num(row, "lower_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.25
            tp = _num(row, "bb_basis", _num(row, "range_midpoint")) or entry + (entry - sl) * 1.5
            return _signal_payload(row, "RL2", "long", entry, sl, tp, "Lower Bollinger fade long triggered in R16.")
    if strategy_id == "RL3":
        level = _num(row, "prev_swing_low")
        conditions = [row.get("regime_id") == "R16", _recent_break_below_level(df, idx, level, 3), _num(row, "close") > level, _num(row, "lower_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _recent_low(df, idx, 3) - atr * 0.30
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") > entry else entry + (entry - sl) * 1.5
            return _signal_payload(row, "RL3", "long", entry, sl, tp, "Range low failed hold long triggered in R16.")

    if strategy_id == "FB1":
        conditions = [row.get("regime_id") == "R17", bool(row.get("false_upside_breakout")), _num(row, "upper_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _recent_high(df, idx, 3) + atr * 0.30
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") < entry else entry - (sl - entry) * rr
            return _signal_payload(row, "FB1", "short", entry, sl, tp, "Failed upside breakout short triggered in R17.")
    if strategy_id == "FB2":
        level = _num(row, "prev_swing_high")
        conditions = [row.get("regime_id") == "R17", _recent_break_above_level(df, idx, level, 3), _num(row, "high") >= level - atr * 0.10, _num(row, "close") < level]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.30
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") < entry else entry - (sl - entry) * rr
            return _signal_payload(row, "FB2", "short", entry, sl, tp, "Breakout trap retest short triggered in R17.")
    if strategy_id == "FB3":
        conditions = [row.get("regime_id") == "R17", _num(row, "close") < _recent_low(df, idx, 3), _num(row, "close") < _num(row, "open"), (_num(row, "er") <= 0.30 or _num(row, "adx") <= 25)]
        if all(conditions):
            sl = _recent_high(df, idx, 5) + atr * 0.30
            return _signal_payload(row, "FB3", "short", entry, sl, entry - (sl - entry) * rr, "Failed high continuation short triggered in R17.")
    if strategy_id == "FB4":
        conditions = [row.get("regime_id") == "R18", bool(row.get("false_downside_breakout")), _num(row, "lower_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _recent_low(df, idx, 3) - atr * 0.30
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") > entry else entry + (entry - sl) * rr
            return _signal_payload(row, "FB4", "long", entry, sl, tp, "Failed downside breakout long triggered in R18.")
    if strategy_id == "FB5":
        level = _num(row, "prev_swing_low")
        conditions = [row.get("regime_id") == "R18", _recent_break_below_level(df, idx, level, 3), _num(row, "low") <= level + atr * 0.10, _num(row, "close") > level]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.30
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") > entry else entry + (entry - sl) * rr
            return _signal_payload(row, "FB5", "long", entry, sl, tp, "Breakdown trap retest long triggered in R18.")
    if strategy_id == "FB6":
        conditions = [row.get("regime_id") == "R18", _num(row, "close") > _recent_high(df, idx, 3), _num(row, "close") > _num(row, "open"), (_num(row, "er") <= 0.30 or _num(row, "adx") <= 25)]
        if all(conditions):
            sl = _recent_low(df, idx, 5) - atr * 0.30
            return _signal_payload(row, "FB6", "long", entry, sl, entry + (entry - sl) * rr, "Failed low continuation long triggered in R18.")

    opening_high = _num(row, "opening_range_high")
    opening_low = _num(row, "opening_range_low")
    opening_mid = _num(row, "opening_range_mid")
    if strategy_id in {"LO1", "NY1"}:
        expected_regime = "R19" if strategy_id == "LO1" else "R20"
        conditions = [row.get("regime_id") == expected_regime, _num(row, "close") > opening_high + atr * 0.10, _num(row, "candle_range_atr") >= 1.0, _num(row, "spread_percentile") < 70]
        if all(conditions):
            sl = opening_high - atr * 0.50
            return _signal_payload(row, strategy_id, "long", entry, sl, entry + (entry - sl) * rr, "Opening range breakout buy triggered.")
    if strategy_id in {"LO2", "NY2"}:
        expected_regime = "R19" if strategy_id == "LO2" else "R20"
        conditions = [row.get("regime_id") == expected_regime, _num(row, "close") < opening_low - atr * 0.10, _num(row, "candle_range_atr") >= 1.0, _num(row, "spread_percentile") < 70]
        if all(conditions):
            sl = opening_low + atr * 0.50
            return _signal_payload(row, strategy_id, "short", entry, sl, entry - (sl - entry) * rr, "Opening range breakdown sell triggered.")
    if strategy_id in {"LO3", "NY3"}:
        expected_regime = "R19" if strategy_id == "LO3" else "R20"
        level = max(opening_high, _num(row, "prev_swing_high"))
        conditions = [row.get("regime_id") == expected_regime, _num(row, "high") > level, _num(row, "close") < level, _num(row, "upper_wick_ratio") >= 0.40]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.25
            tp = opening_mid if opening_mid < entry else entry - (sl - entry) * rr
            return _signal_payload(row, strategy_id, "short", entry, sl, tp, "Opening session sweep high short triggered.")
    if strategy_id in {"LO4", "NY4"}:
        expected_regime = "R19" if strategy_id == "LO4" else "R20"
        level = min(opening_low if opening_low else _num(row, "prev_swing_low"), _num(row, "prev_swing_low"))
        conditions = [row.get("regime_id") == expected_regime, _num(row, "low") < level, _num(row, "close") > level, _num(row, "lower_wick_ratio") >= 0.40]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.25
            tp = opening_mid if opening_mid > entry else entry + (entry - sl) * rr
            return _signal_payload(row, strategy_id, "long", entry, sl, tp, "Opening session sweep low long triggered.")
    if strategy_id in {"LO5", "NY5"}:
        expected_regime = "R19" if strategy_id == "LO5" else "R20"
        long_ok = row.get("regime_id") == expected_regime and _recent_break_above_level(df, idx, opening_high, 5) and _num(row, "low") <= opening_high + atr * 0.25 and _num(row, "close") > opening_high and row.get("htf_bias") == row.get("ltf_bias") == "bullish"
        short_ok = row.get("regime_id") == expected_regime and _recent_break_below_level(df, idx, opening_low, 5) and _num(row, "high") >= opening_low - atr * 0.25 and _num(row, "close") < opening_low and row.get("htf_bias") == row.get("ltf_bias") == "bearish"
        if long_ok:
            sl = opening_high - atr * 0.40
            return _signal_payload(row, strategy_id, "long", entry, sl, entry + (entry - sl) * rr, "Opening range breakout retest continuation buy triggered.")
        if short_ok:
            sl = opening_low + atr * 0.40
            return _signal_payload(row, strategy_id, "short", entry, sl, entry - (sl - entry) * rr, "Opening range breakout retest continuation sell triggered.")

    if strategy_id == "OV1" and row.get("regime_id") == "R21":
        direction = "long" if row.get("htf_bias") == "bullish" else "short" if row.get("htf_bias") == "bearish" else None
        if direction:
            return _pullback_signal(row, "OV1", direction, entry, atr, rr, 0.35)
    if strategy_id == "OV2" and row.get("regime_id") == "R21":
        if row.get("htf_bias") == row.get("ltf_bias") == "bullish":
            return _breakout_retest_signal(df, idx, row, "OV2", "long", entry, atr, rr, _num(row, "prev_swing_high"), 0.50)
        if row.get("htf_bias") == row.get("ltf_bias") == "bearish":
            return _breakout_retest_signal(df, idx, row, "OV2", "short", entry, atr, rr, _num(row, "prev_swing_low"), 0.50)
    if strategy_id == "OV3" and row.get("regime_id") == "R21":
        if row.get("htf_bias") == row.get("ltf_bias") == "bullish":
            return _breakout_retest_signal(df, idx, row, "OV3", "long", entry, atr, rr, _num(row, "prev_day_high"), 0.50)
        if row.get("htf_bias") == row.get("ltf_bias") == "bearish":
            return _breakout_retest_signal(df, idx, row, "OV3", "short", entry, atr, rr, _num(row, "prev_day_low"), 0.50)
    if strategy_id == "OV4" and row.get("regime_id") == "R21":
        if row.get("htf_bias") == row.get("ltf_bias") == "bullish" and bool(row.get("sweep_low_flag")) and _num(row, "close") > _num(row, "prev_swing_low"):
            sl = _num(row, "low") - atr * 0.25
            return _signal_payload(row, "OV4", "long", entry, sl, entry + (entry - sl) * rr, "Overlap sweep-low reclaim continuation triggered.")
        if row.get("htf_bias") == row.get("ltf_bias") == "bearish" and bool(row.get("sweep_high_flag")) and _num(row, "close") < _num(row, "prev_swing_high"):
            sl = _num(row, "high") + atr * 0.25
            return _signal_payload(row, "OV4", "short", entry, sl, entry - (sl - entry) * rr, "Overlap sweep-high rejection continuation triggered.")

    if strategy_id == "AR1":
        conditions = [row.get("regime_id") == "R22", _num(row, "high") >= _num(row, "prev_swing_high") - atr * 0.20, _num(row, "upper_wick_ratio") >= 0.35, _num(row, "close") < _num(row, "prev_swing_high")]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.25
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") < entry else entry - (sl - entry) * 1.5
            return _signal_payload(row, "AR1", "short", entry, sl, tp, "Asia range high fade triggered in R22.")
    if strategy_id == "AR2":
        conditions = [row.get("regime_id") == "R22", _num(row, "low") <= _num(row, "prev_swing_low") + atr * 0.20, _num(row, "lower_wick_ratio") >= 0.35, _num(row, "close") > _num(row, "prev_swing_low")]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.25
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") > entry else entry + (entry - sl) * 1.5
            return _signal_payload(row, "AR2", "long", entry, sl, tp, "Asia range low fade triggered in R22.")
    if strategy_id == "AR3":
        if row.get("regime_id") == "R22" and row.get("session") == "Asia" and bool(row.get("sweep_high_flag")):
            sl = _num(row, "high") + atr * 0.25
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") < entry else entry - (sl - entry) * 1.5
            return _signal_payload(row, "AR3", "short", entry, sl, tp, "Asia sweep high short triggered in R22.")
    if strategy_id == "AR4":
        if row.get("regime_id") == "R22" and row.get("session") == "Asia" and bool(row.get("sweep_low_flag")):
            sl = _num(row, "low") - atr * 0.25
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") > entry else entry + (entry - sl) * 1.5
            return _signal_payload(row, "AR4", "long", entry, sl, tp, "Asia sweep low long triggered in R22.")
    if strategy_id == "AR5":
        return {"triggered": False, "reason": f"Asia watchlist only. Asia high={_num(row, 'asia_high')}, low={_num(row, 'asia_low')}, midpoint={_num(row, 'asia_midpoint')}."}

    if strategy_id == "NC1" and row.get("regime_id") == "R23":
        if _num(row, "high") >= _num(row, "prev_swing_high") - atr * 0.20 and _num(row, "upper_wick_ratio") >= 0.55 and _num(row, "close") < _num(row, "prev_swing_high"):
            sl = _num(row, "high") + atr * 0.25
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") < entry else entry - (sl - entry) * 1.5
            return _signal_payload(row, "NC1", "short", entry, sl, tp, "Research-only noisy chop extreme high fade triggered.")
        if _num(row, "low") <= _num(row, "prev_swing_low") + atr * 0.20 and _num(row, "lower_wick_ratio") >= 0.55 and _num(row, "close") > _num(row, "prev_swing_low"):
            sl = _num(row, "low") - atr * 0.25
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") > entry else entry + (entry - sl) * 1.5
            return _signal_payload(row, "NC1", "long", entry, sl, tp, "Research-only noisy chop extreme low fade triggered.")
    if strategy_id == "DL1":
        return {"triggered": False, "reason": "Dead market expansion watch only; no executable trade in Tab 1 MVP."}

    if strategy_id in {"USD1", "USD4"} and row.get("regime_id") in {"R25", "R26"}:
        expected_bias = "USD_BULLISH" if strategy_id == "USD1" else "USD_BEARISH"
        direction = _usd_direction(str(row.get("symbol", "")), expected_bias)
        if row.get("usd_bias") == expected_bias and direction:
            return _pullback_signal(row, strategy_id, direction, entry, atr, rr, 0.35)
    if strategy_id in {"USD2", "USD5"} and row.get("regime_id") in {"R25", "R26"}:
        expected_bias = "USD_BULLISH" if strategy_id == "USD2" else "USD_BEARISH"
        direction = _usd_direction(str(row.get("symbol", "")), expected_bias)
        if row.get("usd_bias") == expected_bias and direction == "long":
            return _breakout_retest_signal(df, idx, row, strategy_id, "long", entry, atr, rr, _num(row, "prev_swing_high"), 0.50)
        if row.get("usd_bias") == expected_bias and direction == "short":
            return _breakout_retest_signal(df, idx, row, strategy_id, "short", entry, atr, rr, _num(row, "prev_swing_low"), 0.50)
    if strategy_id in {"USD3", "USD6", "RO3"}:
        return {"triggered": False, "reason": f"{strategy_id} needs cross-pair basket confirmation; reference-only until basket data is added."}

    if strategy_id == "RO1" and row.get("regime_id") == "R27" and row.get("risk_sentiment") == "RISK_ON":
        return _pullback_signal(row, "RO1", "long", entry, atr, rr, 0.35)
    if strategy_id == "RO2" and row.get("regime_id") == "R27" and row.get("risk_sentiment") == "RISK_ON":
        return _breakout_retest_signal(df, idx, row, "RO2", "long", entry, atr, rr, _num(row, "prev_swing_high"), 0.50)
    if strategy_id == "RF1" and row.get("regime_id") == "R28" and row.get("risk_sentiment") == "RISK_OFF":
        return _pullback_signal(row, "RF1", "short", entry, atr, rr, 0.40)
    if strategy_id == "RF2" and row.get("regime_id") == "R28" and row.get("risk_sentiment") == "RISK_OFF":
        return _breakout_retest_signal(df, idx, row, "RF2", "short", entry, atr, rr, _num(row, "prev_swing_low"), 0.50)
    if strategy_id == "RF3" and row.get("regime_id") == "R28" and row.get("risk_sentiment") == "RISK_OFF":
        direction = "short" if row.get("htf_bias") == row.get("ltf_bias") == "bearish" else "long" if row.get("htf_bias") == row.get("ltf_bias") == "bullish" else None
        if direction:
            return _pullback_signal(row, "RF3", direction, entry, atr, rr, 0.40)

    if strategy_id == "CB1" and row.get("regime_id") == "R29":
        direction = _cb_direction(str(row.get("cb_divergence", "NEUTRAL")))
        if direction:
            return _pullback_signal(row, "CB1", direction, entry, atr, rr, 0.40)
    if strategy_id == "CB2" and row.get("regime_id") == "R29":
        direction = _cb_direction(str(row.get("cb_divergence", "NEUTRAL")))
        if direction == "long":
            return _breakout_retest_signal(df, idx, row, "CB2", "long", entry, atr, rr, _num(row, "prev_swing_high"), 0.50)
        if direction == "short":
            return _breakout_retest_signal(df, idx, row, "CB2", "short", entry, atr, rr, _num(row, "prev_swing_low"), 0.50)
    if strategy_id == "CB3":
        return {"triggered": False, "reason": "CB3 requires event repricing/news state; reference-only until event feed is added."}
    if strategy_id == "MF1":
        return {"triggered": False, "reason": "Fixing flow watchlist only; no executable trade in Tab 1 MVP."}
    if strategy_id == "MF2":
        return {"triggered": False, "reason": "Post-fixing normalization test is disabled by default until allow_post_fixing_test is added."}

    if strategy_id == "TR1":
        box_high, box_low = _range_high_low(df, idx, 20)
        if row.get("regime_id") == "R31" and 25 <= _num(row, "atr_percentile") <= 75 and _num(row, "spread_percentile") < 70:
            if box_high > 0 and _num(row, "close") > box_high:
                sl = box_high - atr * 0.50
                return _signal_payload(row, "TR1", "long", entry, sl, entry + (entry - sl) * 1.5, "Small transition probe breakout long triggered in R31.")
            if box_low > 0 and _num(row, "close") < box_low:
                sl = box_low + atr * 0.50
                return _signal_payload(row, "TR1", "short", entry, sl, entry - (sl - entry) * 1.5, "Small transition probe breakdown short triggered in R31.")
    if strategy_id == "TR2":
        return {"triggered": False, "reason": "Transition regime watchlist only; wait for R01/R02/R04/R05/R13/R14 confirmation."}

    if strategy_id == "TW1":
        pullback_low = _recent_low(df, idx, 5)
        conditions = [row.get("regime_id") == "R32", _num(row, "close") > _num(row, "ema20"), _num(row, "close") > _num(row, "open"), _num(row, "er_slope") >= -0.01, _num(row, "spread_percentile") < 70]
        if all(conditions):
            sl = pullback_low - atr * 0.35
            return _signal_payload(row, "TW1", "long", entry, sl, entry + (entry - sl) * min(rr, 2.0), "Bull trend weakening recovery buy triggered in R32.")
    if strategy_id == "TW2":
        recent_low = _recent_low(df, idx, 5)
        recent_high = _recent_high(df, idx, 5)
        conditions = [row.get("regime_id") == "R32", _num(row, "close") < recent_low, _num(row, "upper_wick_ratio") >= 0.35, _num(row, "adx_slope") < 0, _num(row, "er_slope") < 0]
        if all(conditions):
            sl = recent_high + atr * 0.35
            tp = _num(row, "ema50") if _num(row, "ema50") < entry else entry - (sl - entry) * 1.5
            return _signal_payload(row, "TW2", "short", entry, sl, tp, "Bull pullback failure short triggered in R32.")
    if strategy_id == "TW3":
        pullback_high = _recent_high(df, idx, 5)
        conditions = [row.get("regime_id") == "R33", _num(row, "close") < _num(row, "ema20"), _num(row, "close") < _num(row, "open"), _num(row, "er_slope") >= -0.01, _num(row, "spread_percentile") < 70]
        if all(conditions):
            sl = pullback_high + atr * 0.35
            return _signal_payload(row, "TW3", "short", entry, sl, entry - (sl - entry) * min(rr, 2.0), "Bear trend weakening recovery sell triggered in R33.")
    if strategy_id == "TW4":
        recent_low = _recent_low(df, idx, 5)
        recent_high = _recent_high(df, idx, 5)
        conditions = [row.get("regime_id") == "R33", _num(row, "close") > recent_high, _num(row, "lower_wick_ratio") >= 0.35, _num(row, "adx_slope") < 0, _num(row, "er_slope") < 0]
        if all(conditions):
            sl = recent_low - atr * 0.35
            tp = _num(row, "ema50") if _num(row, "ema50") > entry else entry + (entry - sl) * 1.5
            return _signal_payload(row, "TW4", "long", entry, sl, tp, "Bear pullback failure long triggered in R33.")

    if strategy_id == "LS1":
        conditions = [row.get("regime_id") == "R34", bool(row.get("sweep_low_flag")), _num(row, "close") > _num(row, "prev_swing_low"), _num(row, "close") > _num(row, "open")]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.30
            return _signal_payload(row, "LS1", "long", entry, sl, entry + (entry - sl) * 2.0, "Bullish sweep reclaim buy triggered in R34.")
    if strategy_id == "LS2":
        sweep_low = _last_event_extreme(df, idx, "sweep_low_flag", "low", 5) or _recent_low(df, idx, 5)
        conditions = [row.get("regime_id") == "R34", _recent_flag(df, idx, "sweep_low_flag", 5), _num(row, "close") > _num(row, "ema20"), row.get("htf_bias") == "bullish"]
        if all(conditions):
            sl = sweep_low - atr * 0.30
            return _signal_payload(row, "LS2", "long", entry, sl, entry + (entry - sl) * 2.0, "Sweep-low plus EMA20 continuation buy triggered in R34.")
    if strategy_id == "LS3":
        recent_high = _recent_high(df, idx - 1, 3) if idx > 0 else 0.0
        recent_low = _recent_low(df, idx, 5)
        conditions = [row.get("regime_id") == "R34", _recent_flag(df, idx, "sweep_low_flag", 5), _num(row, "close") > recent_high, _num(row, "er") >= 0.25]
        if all(conditions):
            sl = recent_low - atr * 0.35
            return _signal_payload(row, "LS3", "long", entry, sl, entry + (entry - sl) * 2.0, "Sweep-low breakout follow-through buy triggered in R34.")
    if strategy_id == "LS4":
        conditions = [row.get("regime_id") == "R35", bool(row.get("sweep_high_flag")), _num(row, "close") < _num(row, "prev_swing_high"), _num(row, "close") < _num(row, "open")]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.30
            return _signal_payload(row, "LS4", "short", entry, sl, entry - (sl - entry) * 2.0, "Bearish sweep reclaim sell triggered in R35.")
    if strategy_id == "LS5":
        sweep_high = _last_event_extreme(df, idx, "sweep_high_flag", "high", 5) or _recent_high(df, idx, 5)
        conditions = [row.get("regime_id") == "R35", _recent_flag(df, idx, "sweep_high_flag", 5), _num(row, "close") < _num(row, "ema20"), row.get("htf_bias") == "bearish"]
        if all(conditions):
            sl = sweep_high + atr * 0.30
            return _signal_payload(row, "LS5", "short", entry, sl, entry - (sl - entry) * 2.0, "Sweep-high plus EMA20 continuation sell triggered in R35.")
    if strategy_id == "LS6":
        recent_low = _recent_low(df, idx - 1, 3) if idx > 0 else 0.0
        recent_high = _recent_high(df, idx, 5)
        conditions = [row.get("regime_id") == "R35", _recent_flag(df, idx, "sweep_high_flag", 5), _num(row, "close") < recent_low, _num(row, "er") >= 0.25]
        if all(conditions):
            sl = recent_high + atr * 0.35
            return _signal_payload(row, "LS6", "short", entry, sl, entry - (sl - entry) * 2.0, "Sweep-high breakdown follow-through sell triggered in R35.")

    if strategy_id == "VW1":
        conditions = [row.get("regime_id") == "R36", _num(row, "distance_from_vwap_atr") >= 1.5, _num(row, "upper_wick_ratio") >= 0.35, _num(row, "close") < _num(row, "open")]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.40
            tp = _num(row, "session_vwap") if _num(row, "session_vwap") < entry else entry - (sl - entry) * 1.5
            return _signal_payload(row, "VW1", "short", entry, sl, tp, "VWAP high mean-reversion short triggered in R36.")
    if strategy_id == "VW2":
        conditions = [row.get("regime_id") == "R36", _num(row, "distance_from_vwap_atr") <= -1.5, _num(row, "lower_wick_ratio") >= 0.35, _num(row, "close") > _num(row, "open")]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.40
            tp = _num(row, "session_vwap") if _num(row, "session_vwap") > entry else entry + (entry - sl) * 1.5
            return _signal_payload(row, "VW2", "long", entry, sl, tp, "VWAP low mean-reversion long triggered in R36.")
    if strategy_id == "VW3" and idx > 0 and row.get("regime_id") == "R36":
        prev = df.iloc[idx - 1]
        failed_high = _num(prev, "distance_from_vwap_atr") >= 1.5 and _num(row, "close") < _num(prev, "high") and _num(row, "close") < _num(row, "open")
        failed_low = _num(prev, "distance_from_vwap_atr") <= -1.5 and _num(row, "close") > _num(prev, "low") and _num(row, "close") > _num(row, "open")
        if failed_high:
            sl = max(_num(row, "high"), _num(prev, "high")) + atr * 0.35
            tp = _num(row, "session_vwap") if _num(row, "session_vwap") < entry else entry - (sl - entry) * 1.5
            return _signal_payload(row, "VW3", "short", entry, sl, tp, "VWAP failed high extension short triggered in R36.")
        if failed_low:
            sl = min(_num(row, "low"), _num(prev, "low")) - atr * 0.35
            tp = _num(row, "session_vwap") if _num(row, "session_vwap") > entry else entry + (entry - sl) * 1.5
            return _signal_payload(row, "VW3", "long", entry, sl, tp, "VWAP failed low extension long triggered in R36.")

    if strategy_id == "MT1" and row.get("regime_id") == "R37":
        if row.get("htf_bias") == "bullish" and bool(row.get("sweep_low_flag")) and _num(row, "close") > _num(row, "prev_swing_low"):
            sl = _num(row, "low") - atr * 0.30
            return _signal_payload(row, "MT1", "long", entry, sl, entry + (entry - sl) * min(rr, 2.0), "HTF bullish conflict trap long triggered in R37.")
        if row.get("htf_bias") == "bearish" and bool(row.get("sweep_high_flag")) and _num(row, "close") < _num(row, "prev_swing_high"):
            sl = _num(row, "high") + atr * 0.30
            return _signal_payload(row, "MT1", "short", entry, sl, entry - (sl - entry) * min(rr, 2.0), "HTF bearish conflict trap short triggered in R37.")
    if strategy_id == "MT2" and row.get("regime_id") == "R37":
        if bool(row.get("false_upside_breakout")) and _num(row, "upper_wick_ratio") >= 0.35:
            sl = _recent_high(df, idx, 3) + atr * 0.30
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") < entry else entry - (sl - entry) * 1.5
            return _signal_payload(row, "MT2", "short", entry, sl, tp, "LTF failed upside breakout fade triggered in R37.")
        if bool(row.get("false_downside_breakout")) and _num(row, "lower_wick_ratio") >= 0.35:
            sl = _recent_low(df, idx, 3) - atr * 0.30
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") > entry else entry + (entry - sl) * 1.5
            return _signal_payload(row, "MT2", "long", entry, sl, tp, "LTF failed downside breakout fade triggered in R37.")

    if strategy_id == "PS1":
        stress_high, stress_low = _range_high_low(df, idx, 10)
        if row.get("regime_id") == "R38" and _num(row, "spread_stress_bars_ago", 0) >= 3 and _num(row, "spread_percentile") < 70:
            if _recent_break_above_level(df, idx, stress_high, 5) and _num(row, "low") <= stress_high + atr * 0.25 and _num(row, "close") > stress_high:
                sl = stress_high - atr * 0.50
                return _signal_payload(row, "PS1", "long", entry, sl, entry + (entry - sl) * 2.0, "Post-stress breakout retest long triggered in R38.")
            if _recent_break_below_level(df, idx, stress_low, 5) and _num(row, "high") >= stress_low - atr * 0.25 and _num(row, "close") < stress_low:
                sl = stress_low + atr * 0.50
                return _signal_payload(row, "PS1", "short", entry, sl, entry - (sl - entry) * 2.0, "Post-stress breakdown retest short triggered in R38.")
    if strategy_id == "PS2":
        stress_high, stress_low = _range_high_low(df, idx, 10)
        if row.get("regime_id") == "R38" and _num(row, "upper_wick_ratio") >= 0.40 and _num(row, "close") < stress_high:
            sl = _num(row, "high") + atr * 0.35
            tp = _num(row, "session_vwap") if _num(row, "session_vwap") < entry else (_num(row, "range_midpoint") or entry - (sl - entry) * 1.5)
            return _signal_payload(row, "PS2", "short", entry, sl, tp, "Post-stress mean-reversion short triggered in R38.")
        if row.get("regime_id") == "R38" and _num(row, "lower_wick_ratio") >= 0.40 and _num(row, "close") > stress_low:
            sl = _num(row, "low") - atr * 0.35
            tp = _num(row, "session_vwap") if _num(row, "session_vwap") > entry else (_num(row, "range_midpoint") or entry + (entry - sl) * 1.5)
            return _signal_payload(row, "PS2", "long", entry, sl, tp, "Post-stress mean-reversion long triggered in R38.")

    if strategy_id == "G1" and row.get("regime_id") == "R39" and _num(row, "gap_bars_ago", 0) >= 3 and _num(row, "spread_percentile") < 70:
        previous_close = _num(row, "previous_close")
        gap_up = _num(row, "open") > previous_close
        gap_down = _num(row, "open") < previous_close
        if gap_up and _num(row, "close") < _num(row, "open") and _num(row, "upper_wick_ratio") >= 0.35:
            sl = _recent_high(df, idx, 5) + atr * 0.50
            tp = max(previous_close, entry - abs(_num(row, "open") - previous_close) * 0.50)
            return _signal_payload(row, "G1", "short", entry, sl, tp, "Gap fill short test triggered in R39.")
        if gap_down and _num(row, "close") > _num(row, "open") and _num(row, "lower_wick_ratio") >= 0.35:
            sl = _recent_low(df, idx, 5) - atr * 0.50
            tp = min(previous_close, entry + abs(_num(row, "open") - previous_close) * 0.50)
            return _signal_payload(row, "G1", "long", entry, sl, tp, "Gap fill long test triggered in R39.")
    if strategy_id == "G2" and row.get("regime_id") == "R39" and _num(row, "gap_bars_ago", 0) >= 3 and row.get("htf_bias") == row.get("ltf_bias"):
        previous_close = _num(row, "previous_close")
        if _num(row, "open") > previous_close and row.get("htf_bias") == "bullish":
            return _breakout_retest_signal(df, idx, row, "G2", "long", entry, atr, 2.0, _num(row, "open"), 0.50)
        if _num(row, "open") < previous_close and row.get("htf_bias") == "bearish":
            return _breakout_retest_signal(df, idx, row, "G2", "short", entry, atr, 2.0, _num(row, "open"), 0.50)

    if strategy_id == "AS1":
        level = _num(row, "asia_low")
        conditions = [row.get("regime_id") == "R41", _num(row, "low") < level, _num(row, "close") > level, _num(row, "lower_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.30
            return _signal_payload(row, "AS1", "long", entry, sl, entry + (entry - sl) * 2.0, "Asia low sweep reclaim buy triggered in R41.")
    if strategy_id == "AS2":
        level = _num(row, "asia_high")
        conditions = [row.get("regime_id") == "R41", _num(row, "high") > level, _num(row, "close") < level, _num(row, "upper_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.30
            return _signal_payload(row, "AS2", "short", entry, sl, entry - (sl - entry) * 2.0, "Asia high sweep rejection sell triggered in R41.")
    if strategy_id == "AS3" and row.get("regime_id") == "R41":
        if row.get("htf_bias") == "bullish" and _num(row, "close") > _num(row, "asia_high") and _num(row, "low") <= _num(row, "asia_high") + atr * 0.25:
            sl = _num(row, "asia_high") - atr * 0.40
            return _signal_payload(row, "AS3", "long", entry, sl, entry + (entry - sl) * 2.0, "Asia range continuation retest buy triggered in R41.")
        if row.get("htf_bias") == "bearish" and _num(row, "close") < _num(row, "asia_low") and _num(row, "high") >= _num(row, "asia_low") - atr * 0.25:
            sl = _num(row, "asia_low") + atr * 0.40
            return _signal_payload(row, "AS3", "short", entry, sl, entry - (sl - entry) * 2.0, "Asia range continuation retest sell triggered in R41.")

    if strategy_id == "OF1":
        level = _num(row, "opening_range_high")
        conditions = [row.get("regime_id") == "R42", _num(row, "high") > level, _num(row, "close") < level, _num(row, "upper_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.30
            tp = _num(row, "opening_range_mid") if _num(row, "opening_range_mid") < entry else entry - (sl - entry) * 1.5
            return _signal_payload(row, "OF1", "short", entry, sl, tp, "Opening range upside fakeout short triggered in R42.")
    if strategy_id == "OF2":
        level = _num(row, "opening_range_low")
        conditions = [row.get("regime_id") == "R42", _num(row, "low") < level, _num(row, "close") > level, _num(row, "lower_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.30
            tp = _num(row, "opening_range_mid") if _num(row, "opening_range_mid") > entry else entry + (entry - sl) * 1.5
            return _signal_payload(row, "OF2", "long", entry, sl, tp, "Opening range downside fakeout long triggered in R42.")

    if strategy_id == "PD1":
        level = _num(row, "prev_day_high")
        conditions = [row.get("regime_id") == "R43", _num(row, "high") >= level, _num(row, "close") < level, _num(row, "upper_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.30
            tp = _num(row, "range_midpoint") if 0 < _num(row, "range_midpoint") < entry else entry - (sl - entry) * 1.5
            return _signal_payload(row, "PD1", "short", entry, sl, tp, "Previous-day high rejection short triggered in R43.")
    if strategy_id == "PD2":
        level = _num(row, "prev_day_low")
        conditions = [row.get("regime_id") == "R43", _num(row, "low") <= level, _num(row, "close") > level, _num(row, "lower_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.30
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") > entry else entry + (entry - sl) * 1.5
            return _signal_payload(row, "PD2", "long", entry, sl, tp, "Previous-day low rejection long triggered in R43.")

    if strategy_id == "TD1" and row.get("regime_id") == "R44":
        if row.get("htf_bias") == "bullish":
            return _pullback_signal(row, "TD1", "long", entry, atr, 2.0, 0.35)
        if row.get("htf_bias") == "bearish":
            return _pullback_signal(row, "TD1", "short", entry, atr, 2.0, 0.35)
    if strategy_id == "TD2" and row.get("regime_id") == "R44":
        if row.get("htf_bias") == "bullish":
            return _breakout_retest_signal(df, idx, row, "TD2", "long", entry, atr, 2.0, _num(row, "prev_swing_high"), 0.50)
        if row.get("htf_bias") == "bearish":
            return _breakout_retest_signal(df, idx, row, "TD2", "short", entry, atr, 2.0, _num(row, "prev_swing_low"), 0.50)
    if strategy_id == "TD3" and row.get("regime_id") == "R44":
        if row.get("htf_bias") == "bullish" and _num(row, "low") <= _num(row, "session_vwap") + atr * 0.25 and _num(row, "close") > _num(row, "session_vwap"):
            sl = _num(row, "session_vwap") - atr * 0.45
            return _signal_payload(row, "TD3", "long", entry, sl, entry + (entry - sl) * 2.0, "Trend-day VWAP hold continuation buy triggered in R44.")
        if row.get("htf_bias") == "bearish" and _num(row, "high") >= _num(row, "session_vwap") - atr * 0.25 and _num(row, "close") < _num(row, "session_vwap"):
            sl = _num(row, "session_vwap") + atr * 0.45
            return _signal_payload(row, "TD3", "short", entry, sl, entry - (sl - entry) * 2.0, "Trend-day VWAP hold continuation sell triggered in R44.")

    if strategy_id == "CX1":
        conditions = [row.get("regime_id") == "R45", _num(row, "distance_from_ema20_atr") >= 2.5, _num(row, "upper_wick_ratio") >= 0.45, _num(row, "close") < _num(row, "open")]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.35
            tp = _num(row, "ema20") if _num(row, "ema20") < entry else entry - (sl - entry) * 1.5
            return _signal_payload(row, "CX1", "short", entry, sl, tp, "Climax high exhaustion short triggered in R45.")
    if strategy_id == "CX2":
        conditions = [row.get("regime_id") == "R45", _num(row, "distance_from_ema20_atr") <= -2.5, _num(row, "lower_wick_ratio") >= 0.45, _num(row, "close") > _num(row, "open")]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.35
            tp = _num(row, "ema20") if _num(row, "ema20") > entry else entry + (entry - sl) * 1.5
            return _signal_payload(row, "CX2", "long", entry, sl, tp, "Climax low exhaustion long triggered in R45.")

    if strategy_id == "VT1":
        conditions = [row.get("regime_id") == "R46", row.get("htf_bias") == "bullish", _num(row, "close") > _num(row, "session_vwap"), _num(row, "low") <= _num(row, "session_vwap") + atr * 0.35, _num(row, "close") > _num(row, "open")]
        if all(conditions):
            sl = _num(row, "session_vwap") - atr * 0.40
            return _signal_payload(row, "VT1", "long", entry, sl, entry + (entry - sl) * 2.0, "VWAP trend acceptance pullback buy triggered in R46.")
    if strategy_id == "VT2":
        conditions = [row.get("regime_id") == "R46", row.get("htf_bias") == "bearish", _num(row, "close") < _num(row, "session_vwap"), _num(row, "high") >= _num(row, "session_vwap") - atr * 0.35, _num(row, "close") < _num(row, "open")]
        if all(conditions):
            sl = _num(row, "session_vwap") + atr * 0.40
            return _signal_payload(row, "VT2", "short", entry, sl, entry - (sl - entry) * 2.0, "VWAP trend acceptance pullback sell triggered in R46.")

    if strategy_id == "SQ1":
        conditions = [row.get("regime_id") == "R47", _num(row, "close") > _num(row, "prev_swing_high"), _num(row, "candle_range_atr") >= 1.0, _num(row, "spread_percentile") < 70]
        if all(conditions):
            sl = _num(row, "prev_swing_high") - atr * 0.45
            return _signal_payload(row, "SQ1", "long", entry, sl, entry + (entry - sl) * 2.0, "Squeeze expansion breakout buy triggered in R47.")
    if strategy_id == "SQ2":
        conditions = [row.get("regime_id") == "R47", _num(row, "close") < _num(row, "prev_swing_low"), _num(row, "candle_range_atr") >= 1.0, _num(row, "spread_percentile") < 70]
        if all(conditions):
            sl = _num(row, "prev_swing_low") + atr * 0.45
            return _signal_payload(row, "SQ2", "short", entry, sl, entry - (sl - entry) * 2.0, "Squeeze expansion breakdown sell triggered in R47.")

    if strategy_id == "MM1":
        midpoint = _num(row, "range_midpoint")
        conditions = [row.get("regime_id") == "R48", _num(row, "close") > midpoint, _num(row, "upper_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.25
            tp = midpoint if midpoint < entry else entry - (sl - entry) * 1.5
            return _signal_payload(row, "MM1", "short", entry, sl, tp, "Range high midpoint-magnet short triggered in R48.")
    if strategy_id == "MM2":
        midpoint = _num(row, "range_midpoint")
        conditions = [row.get("regime_id") == "R48", _num(row, "close") < midpoint, _num(row, "lower_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.25
            tp = midpoint if midpoint > entry else entry + (entry - sl) * 1.5
            return _signal_payload(row, "MM2", "long", entry, sl, tp, "Range low midpoint-magnet long triggered in R48.")

    if strategy_id == "XS1":
        high_level = max(_num(row, "asia_high"), _num(row, "opening_range_high"))
        conditions = [row.get("regime_id") == "R49", high_level > 0, _num(row, "high") > high_level, _num(row, "close") < high_level, _num(row, "upper_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _num(row, "high") + atr * 0.30
            tp = _num(row, "range_midpoint") if 0 < _num(row, "range_midpoint") < entry else entry - (sl - entry) * 1.5
            return _signal_payload(row, "XS1", "short", entry, sl, tp, "Cross-session high breakout failure short triggered in R49.")
    if strategy_id == "XS2":
        low_candidates = [value for value in [_num(row, "asia_low"), _num(row, "opening_range_low")] if value > 0]
        low_level = min(low_candidates) if low_candidates else 0.0
        conditions = [row.get("regime_id") == "R49", low_level > 0, _num(row, "low") < low_level, _num(row, "close") > low_level, _num(row, "lower_wick_ratio") >= 0.35]
        if all(conditions):
            sl = _num(row, "low") - atr * 0.30
            tp = _num(row, "range_midpoint") if _num(row, "range_midpoint") > entry else entry + (entry - sl) * 1.5
            return _signal_payload(row, "XS2", "long", entry, sl, tp, "Cross-session low breakout failure long triggered in R49.")

    if strategy_id == "EC1" and row.get("regime_id") == "R50" and row.get("htf_bias") == row.get("ltf_bias") and row.get("htf_bias") in {"bullish", "bearish"}:
        if row.get("htf_bias") == "bullish" and _num(row, "close") > _num(row, "ema20"):
            sl = min(_num(row, "low"), _num(row, "ema20")) - atr * 0.70
            return _signal_payload(row, "EC1", "long", entry, sl, entry + (entry - sl) * rr, "Cost-adjusted wide-stop long research test triggered in R50.")
        if row.get("htf_bias") == "bearish" and _num(row, "close") < _num(row, "ema20"):
            sl = max(_num(row, "high"), _num(row, "ema20")) + atr * 0.70
            return _signal_payload(row, "EC1", "short", entry, sl, entry - (sl - entry) * rr, "Cost-adjusted wide-stop short research test triggered in R50.")

    if strategy_id == "DQ1":
        return {"triggered": False, "reason": f"Manual review only. {row.get('data_quality_reasons') or 'Data-quality regime blocks executable strategies.'}"}

    if strategy_id in {"D0", "D1"}:
        return {"triggered": False, "reason": f"{strategy_id} is a defensive research decision, not an executable trade signal."}

    return {"triggered": False, "reason": f"{strategy_id} entry conditions are not met."}


def calculate_alpha(row: dict[str, Any] | pd.Series, strategy_result: dict[str, Any], modifiers: dict[str, Any]) -> dict[str, Any]:
    direction = strategy_result.get("direction")
    components = {
        "direction": 0,
        "structure": 0,
        "volatility": 0,
        "liquidity": 0,
        "session": 0,
        "sentiment": 0,
        "penalties": 0,
    }

    htf = row.get("htf_bias")
    ltf = row.get("ltf_bias")
    if direction == "long":
        if htf == "bullish" and ltf == "bullish":
            components["direction"] += 2
        if _num(row, "plus_di") > _num(row, "minus_di"):
            components["direction"] += 1
        if _num(row, "ema_slope") > 0:
            components["direction"] += 1
    if direction == "short":
        if htf == "bearish" and ltf == "bearish":
            components["direction"] += 2
        if _num(row, "minus_di") > _num(row, "plus_di"):
            components["direction"] += 1
        if _num(row, "ema_slope") < 0:
            components["direction"] += 1

    if strategy_result.get("triggered"):
        components["structure"] += 2
    if strategy_result.get("strategy_id") in {
        "T1", "T2", "T4", "T5", "R1", "R2", "B1", "B2", "B3", "B4", "B5", "B6",
        "C1", "C2", "C3", "C4", "E1", "E2", "E3", "E4", "N2",
        "L1", "L2", "L3", "L4", "L5", "L6",
        "CH1", "CH2", "CH3", "CH4", "CH5", "CH6",
        "RH1", "RH2", "RH3", "RL1", "RL2", "RL3",
        "FB1", "FB2", "FB3", "FB4", "FB5", "FB6",
        "LO1", "LO2", "LO3", "LO4", "LO5", "NY1", "NY2", "NY3", "NY4", "NY5",
        "OV1", "OV2", "OV3", "OV4", "AR1", "AR2", "AR3", "AR4", "NC1",
        "USD1", "USD2", "USD4", "USD5", "RO1", "RO2", "RF1", "RF2", "RF3", "CB1", "CB2",
        "TR1", "TW1", "TW2", "TW3", "TW4", "LS1", "LS2", "LS3", "LS4", "LS5", "LS6",
        "VW1", "VW2", "VW3", "MT1", "MT2", "PS1", "PS2", "G1", "G2",
        "AS1", "AS2", "AS3", "OF1", "OF2", "PD1", "PD2", "TD1", "TD2", "TD3",
        "CX1", "CX2", "VT1", "VT2", "SQ1", "SQ2", "MM1", "MM2", "XS1", "XS2", "EC1",
    }:
        components["structure"] += 1
    if (direction == "long" and _num(row, "close") > _num(row, "open")) or (direction == "short" and _num(row, "close") < _num(row, "open")):
        components["structure"] += 1

    atrp = _num(row, "atr_percentile")
    if 25 <= atrp <= 80:
        components["volatility"] += 1
    if row.get("volatility_expansion_flag") and strategy_result.get("strategy_id") in {"T3", "T6", "B1", "B2", "B3", "B4", "B5", "B6", "C1", "C2", "LO1", "LO2", "LO5", "NY1", "NY2", "NY5", "OV2", "OV3", "OV4", "RO2", "RF2", "CB2", "TR1", "LS3", "LS6", "PS1", "G2", "AS3", "TD2", "SQ1", "SQ2"}:
        components["volatility"] += 1
    if atrp >= 90:
        components["volatility"] -= 2

    spreadp = _num(row, "spread_percentile")
    if spreadp < 70:
        components["liquidity"] += 1
    if spreadp >= 90:
        components["liquidity"] -= 3
    if row.get("session") == "Rollover":
        components["liquidity"] -= 3

    session = row.get("session")
    if session == "London":
        components["session"] += 1
    if session == "NewYork":
        components["session"] += 1
    if session == "Overlap":
        components["session"] += 2
    if session == "Asia" and strategy_result.get("strategy_id") in {"R1", "R2", "RH1", "RL1", "RH2", "RL2", "AR1", "AR2", "AR3", "AR4", "MM1", "MM2"}:
        components["session"] += 1
    if session == "Rollover":
        components["session"] -= 2

    sentiment = row.get("sentiment", "NEUTRAL")
    if (direction == "long" and sentiment == "BULLISH") or (direction == "short" and sentiment == "BEARISH"):
        components["sentiment"] += 1
    if (direction == "long" and sentiment == "BEARISH") or (direction == "short" and sentiment == "BULLISH"):
        components["sentiment"] -= 1

    if 70 <= spreadp < 90:
        components["penalties"] -= 1
    if spreadp >= 90:
        components["penalties"] -= 3
    if htf != ltf and htf != "neutral" and ltf != "neutral":
        components["penalties"] -= 2
    if abs(_num(row, "distance_from_ema20_atr")) >= 2.5:
        components["penalties"] -= 2
    if direction == "long" and _num(row, "upper_wick_ratio") >= 0.45:
        components["penalties"] -= 1
    if direction == "short" and _num(row, "lower_wick_ratio") >= 0.45:
        components["penalties"] -= 1
    if modifiers["hard_block"]:
        components["penalties"] -= 5

    score = sum(components.values())
    allowed = score >= THRESHOLDS["alpha"]["minimum"] and not modifiers["hard_block"] and strategy_result.get("triggered", False)
    return {
        "alpha_score": float(score),
        "components": components,
        "decision": "ALLOW" if allowed else "BLOCK",
        "reason": "Trend/range structure and execution context are valid." if allowed else "Alpha score is too low or a hard block is active.",
    }


def allowed_strategies_for_regime(regime_result: dict[str, Any]) -> list[str]:
    if not regime_result.get("is_active"):
        return []
    return list(regime_result.get("allowed_strategies", []))
