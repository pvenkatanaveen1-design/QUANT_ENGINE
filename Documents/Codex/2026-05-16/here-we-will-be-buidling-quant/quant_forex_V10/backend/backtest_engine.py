from __future__ import annotations

import math
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from backend.common.engines.explanation_engine import explain_backtest_summary
from backend.common.engines.pattern_engine import detect_patterns
from backend.common.engines.regime_engine import detect_regime
from backend.common.engines.strategy_engine import (
    STRATEGIES,
    calculate_alpha,
    evaluate_strategy,
)
from backend.common.config_loader import load_market_defaults
from backend.common.modifiers.modifier_engine import detect_modifiers
from backend.calibration_engine import (
    apply_calibration_to_request,
    calibration_summary,
    inject_calibration_columns,
    resolve_calibration,
)
from backend.cost_model_engine import DEFAULT_FIXED_COST_R, POINT_SIZE_BY_SYMBOL, calculate_trade_cost, resolve_cost_model
from backend.database import save_backtest_result
from backend.feature_cache_engine import load_or_calculate_features
from backend.institutional_data_engine import evaluate_institutional_data_quality


COST_R = DEFAULT_FIXED_COST_R
STRICT_BLOCK_MODIFIERS = {"M00", "M07", "M08", "M10", "M11", "M13"}
TREND_KILLZONES = {"London", "NewYork", "Overlap"}
VALID_SESSIONS = {"Asia", "London", "NewYork", "Overlap"}
STAT_TREND_REGIMES = {"R01", "R02", "R04", "R05", "R11", "R12", "R13", "R14", "R19", "R20", "R21", "R25", "R26", "R27", "R28", "R29", "R32", "R33", "R34", "R35", "R41", "R44", "R46", "R47"}
STAT_RANGE_REGIMES = {"R03", "R15", "R16", "R22", "R36", "R37", "R42", "R45", "R48"}
STAT_STRESS_REGIMES = {"R09", "R10", "R23", "R30", "R38", "R39", "R40", "R50"}


def research_mode_presets() -> dict[str, Any]:
    market = load_market_defaults()
    presets = market.get("research_mode_presets") if isinstance(market.get("research_mode_presets"), dict) else {}
    return {
        "mode_presets": market.get("mode_presets") or list(presets),
        "default_mode_preset": market.get("default_mode_preset"),
        "research_mode_presets": presets,
    }


def resolve_research_mode_preset(name: str | None = None) -> dict[str, Any]:
    presets_payload = research_mode_presets()
    presets = presets_payload["research_mode_presets"]
    selected = name or presets_payload.get("default_mode_preset")
    preset = presets.get(selected)
    if not isinstance(preset, dict):
        selected = presets_payload.get("default_mode_preset")
        preset = presets.get(selected, {}) if selected else {}
    return {
        "selected": selected,
        "default": presets_payload.get("default_mode_preset"),
        "available": presets_payload.get("mode_presets") or list(presets),
        "preset": dict(preset or {}),
    }


def _apply_research_mode_preset(request: dict[str, Any]) -> dict[str, Any]:
    resolved = resolve_research_mode_preset(request.get("research_mode_preset"))
    preset_name = resolved.get("selected")
    preset = resolved.get("preset")
    if not isinstance(preset, dict):
        return request

    merged = dict(request)
    merged["research_mode_preset"] = preset_name
    merged["_resolved_mode_preset"] = resolved
    filters = dict(merged.get("filters") or {})
    pattern_engine = dict(merged.get("pattern_engine") or {})
    regime_controls = dict(merged.get("regime_controls") or {})
    mt5_backtest = dict(merged.get("mt5_backtest") or {})
    calibration = dict(merged.get("calibration") or {})

    for key in [
        "killzone_mode",
        "spread_filter_mode",
        "alpha_mode",
        "min_alpha_score",
        "max_spread_percentile",
        "strict_regime_validation",
        "reject_trend_weakening",
        "reject_low_er_clean_trend",
        "reject_adx_outside_clean_trend",
        "reject_mtf_conflict_score",
        "strict_regime_max_failed_conditions",
        "strict_regime_min_confidence",
        "min_clean_trend_er",
        "clean_trend_adx_min",
        "clean_trend_adx_max",
    ]:
        if key in preset:
            filters.setdefault(key, preset[key])
    for key in ["strict_clean_trend"]:
        if key in preset:
            merged.setdefault(key, preset[key])
    for key in ["pattern_score_mode", "min_pattern_score"]:
        if key in preset:
            pattern_engine.setdefault(key, preset[key])
    if "calibration_profile" in preset:
        calibration.setdefault("profile", preset["calibration_profile"])
    for source, target in [("use_regime_hysteresis", "use_regime_hysteresis"), ("hysteresis_confirm_bars", "hysteresis_confirm_bars"), ("hysteresis_confidence_margin", "hysteresis_confidence_margin")]:
        if source in preset:
            regime_controls.setdefault(target, preset[source])
    if "mt5_tester_model" in preset:
        mt5_backtest.setdefault("test_model", preset["mt5_tester_model"])
    if "execution_quality" in preset:
        mt5_backtest.setdefault("execution_quality", preset["execution_quality"])
    if "use_python_signals" in preset:
        mt5_backtest.setdefault("use_python_signals", preset["use_python_signals"])

    merged["filters"] = filters
    merged["pattern_engine"] = pattern_engine
    merged["regime_controls"] = regime_controls
    merged["mt5_backtest"] = mt5_backtest
    merged["calibration"] = calibration
    return merged
TIMEFRAME_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
MT5_MODEL_ROWS = [
    ("one_min_ohlc", "1-Min OHLC"),
    ("every_tick", "Every Tick"),
    ("every_tick_real_ticks", "Real Ticks"),
]
DANGER_REGIME_IDS = {"R40", "R10", "R30", "R39", "R09", "R23", "R24", "R38", "R50"}


def _switch_count(values: pd.Series | list[Any]) -> int:
    series = pd.Series(values).astype(str)
    if series.empty:
        return 0
    return int((series != series.shift(1)).fillna(False).sum())


def _apply_regime_hysteresis(
    raw_regimes: list[dict[str, Any]],
    regime_controls: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Stabilize regime labels while allowing safety regimes to override immediately."""
    controls = regime_controls or {}
    enabled = bool(controls.get("use_regime_hysteresis", True))
    confirm_bars = max(1, int(controls.get("hysteresis_confirm_bars", 3)))
    confidence_margin = float(controls.get("hysteresis_confidence_margin", 0.15))
    danger_ids = set(controls.get("danger_regime_ids") or DANGER_REGIME_IDS)
    if not enabled:
        return [
            {
                **regime,
                "stable_regime_id": regime["regime_id"],
                "stable_regime_name": regime["regime_name"],
                "stable_regime_confidence": regime["confidence"],
                "stable_regime_failed_conditions": regime.get("conditions_failed", []),
                "regime_hysteresis_applied": 0,
                "regime_hysteresis_reason": "Hysteresis disabled; raw regime used.",
                "regime_hysteresis_pending": "",
            }
            for regime in raw_regimes
        ]

    stabilized: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    pending_id: str | None = None
    pending_count = 0

    for regime in raw_regimes:
        raw_id = regime["regime_id"]
        raw_conf = float(regime.get("confidence") or 0)
        if current is None:
            current = regime
            pending_id = None
            pending_count = 0
            reason = "Initial regime accepted."
            applied = 0
        elif raw_id == current["regime_id"]:
            current = regime
            pending_id = None
            pending_count = 0
            reason = "Raw regime matches stable regime."
            applied = 0
        elif raw_id in danger_ids:
            current = regime
            pending_id = None
            pending_count = 0
            reason = f"Danger/safety regime {raw_id} overrode hysteresis immediately."
            applied = 0
        else:
            if raw_id == pending_id:
                pending_count += 1
            else:
                pending_id = raw_id
                pending_count = 1
            current_conf = float(current.get("confidence") or 0)
            confidence_override = raw_conf >= current_conf + confidence_margin
            persistence_override = pending_count >= confirm_bars
            if confidence_override or persistence_override:
                current = regime
                reason = (
                    f"Accepted {raw_id}: "
                    + (
                        f"confidence exceeded previous stable regime by {confidence_margin:.2f}."
                        if confidence_override
                        else f"raw regime persisted for {pending_count} bars."
                    )
                )
                pending_id = None
                pending_count = 0
                applied = 0
            else:
                reason = (
                    f"Held {current['regime_id']} while candidate {raw_id} has "
                    f"{pending_count}/{confirm_bars} confirming bars and confidence margin "
                    f"{raw_conf - current_conf:.2f}/{confidence_margin:.2f}."
                )
                applied = 1

        stable = {
            **regime,
            "stable_regime_id": current["regime_id"],
            "stable_regime_name": current["regime_name"],
            "stable_regime_confidence": current.get("confidence", 0),
            "stable_regime_failed_conditions": current.get("conditions_failed", []),
            "regime_hysteresis_applied": applied,
            "regime_hysteresis_reason": reason,
            "regime_hysteresis_pending": pending_id or "",
        }
        stabilized.append(stable)
    return stabilized


def _status(trade_count: int, expectancy_r: float, profit_factor: float) -> str:
    if trade_count >= 100 and expectancy_r > 0 and profit_factor >= 1.2:
        return "APPROVED"
    if 50 <= trade_count <= 99 and expectancy_r > 0:
        return "WATCHLIST"
    if 20 <= trade_count <= 49:
        return "INSUFFICIENT DATA"
    if trade_count < 20:
        return "NOT ENOUGH DATA"
    if expectancy_r <= 0:
        return "REJECTED"
    return "WATCHLIST"


def _profit_factor(results: list[float]) -> float:
    gross_profit = sum(x for x in results if x > 0)
    gross_loss = abs(sum(x for x in results if x < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def _max_drawdown(values: list[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    cumulative = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    return max_dd


def _max_losing_streak(results: list[float]) -> int:
    current = 0
    max_streak = 0
    for value in results:
        if value < 0:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak


def _break_even_win_rate(avg_win: float, avg_loss: float, fallback_rr: float = 2.0) -> float:
    loss = abs(avg_loss)
    if avg_win > 0 and loss > 0:
        return loss / (avg_win + loss)
    return 1 / (1 + fallback_rr)


def _performance_from_trades(key: dict[str, Any], trades: list[dict[str, Any]], rr: float = 2.0) -> dict[str, Any]:
    results = [float(t["result_R"]) for t in trades]
    profits = [float(t["profit"]) for t in trades]
    costs = [float(t.get("total_cost_R") or t.get("cost_R") or 0) for t in trades]
    wins = [r for r in results if r > 0]
    losses = [r for r in results if r < 0]
    trade_count = len(results)
    win_rate = len(wins) / trade_count if trade_count else 0.0
    loss_rate = len(losses) / trade_count if trade_count else 0.0
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    average_r = float(np.mean(results)) if results else 0.0
    expectancy = average_r
    pf = _profit_factor(results)
    be = _break_even_win_rate(avg_win, avg_loss, rr)
    payoff = avg_win / abs(avg_loss) if avg_win > 0 and avg_loss < 0 else 0.0
    std_r = float(np.std(results, ddof=1)) if len(results) > 1 else 0.0
    max_dd = _max_drawdown(results)
    recovery = sum(results) / abs(max_dd) if max_dd < 0 else (sum(results) if sum(results) > 0 else 0.0)
    return {
        **key,
        "trade_count": trade_count,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 4),
        "loss_rate": round(loss_rate, 4),
        "avg_win_R": round(avg_win, 4),
        "avg_loss_R": round(avg_loss, 4),
        "expectancy_R": round(expectancy, 4),
        "average_R": round(average_r, 4),
        "profit_factor": round(pf, 4) if math.isfinite(pf) else 999.0,
        "max_drawdown_R": round(max_dd, 4),
        "max_losing_streak": _max_losing_streak(results),
        "net_profit": round(sum(profits), 2),
        "gross_profit": round(sum(p for p in profits if p > 0), 2),
        "gross_loss": round(sum(p for p in profits if p < 0), 2),
        "probability_of_3_losses": round(loss_rate**3, 4),
        "probability_of_5_losses": round(loss_rate**5, 4),
        "break_even_win_rate": round(be, 4),
        "actual_vs_break_even": round(win_rate - be, 4),
        "payoff_ratio": round(payoff, 4),
        "recovery_factor": round(recovery, 4),
        "sharpe_like_R": round(average_r / std_r, 4) if std_r else 0.0,
        "average_cost_R": round(float(np.mean(costs)), 4) if costs else 0.0,
        "total_cost_R": round(sum(costs), 4),
        "status": _status(trade_count, expectancy, pf if math.isfinite(pf) else 999.0),
    }


def _simulate_exit(df: pd.DataFrame, entry_idx: int, signal: dict[str, Any]) -> tuple[int, float, str]:
    direction = signal["direction"]
    sl = signal["sl"]
    tp = signal["tp"]
    for j in range(entry_idx + 1, len(df)):
        bar = df.iloc[j]
        if direction == "long":
            sl_hit = bar["low"] <= sl
            tp_hit = bar["high"] >= tp
        else:
            sl_hit = bar["high"] >= sl
            tp_hit = bar["low"] <= tp
        if sl_hit and tp_hit:
            return j, sl, "SL and TP touched in same candle; conservative mode assumed SL first."
        if sl_hit:
            return j, sl, "Stop loss hit."
        if tp_hit:
            return j, tp, "Take profit hit."
    last = df.iloc[-1]
    return len(df) - 1, float(last["close"]), "Closed at final available candle."


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def _point_size(symbol: str, controls: dict[str, Any] | None = None) -> float:
    overrides = (controls or {}).get("symbol_point_size")
    symbol_u = str(symbol or "").upper()
    if isinstance(overrides, dict) and symbol_u in overrides:
        return max(_float(overrides[symbol_u], POINT_SIZE_BY_SYMBOL.get(symbol_u, 0.00001)), 0.00000001)
    for key, point in POINT_SIZE_BY_SYMBOL.items():
        if symbol_u.startswith(key):
            return point
    if "JPY" in symbol_u:
        return 0.001
    if "XAU" in symbol_u or "GOLD" in symbol_u:
        return 0.01
    return 0.00001


def _profile_stop_atr(symbol: str, row: pd.Series, strategy_id: str) -> tuple[float, str]:
    symbol_u = str(symbol or "").upper()
    session = str(row.get("session") or "OffSession")
    regime_id = str(row.get("regime_id") or "")
    atr_percentile = _float(row.get("atr_percentile"))
    spread_percentile = _float(row.get("spread_percentile"))
    base = 0.50
    reason = "Default institutional M15 profile."

    if "XAU" in symbol_u or "GOLD" in symbol_u:
        base = 1.00
        reason = "XAU/GOLD profile uses wider stops for larger intrabar noise."
        if session in {"NewYork", "Overlap"} or atr_percentile >= 75 or spread_percentile >= 70:
            base = 1.25
            reason = "XAU/GOLD NY/high-vol/spread profile uses the widest stop bucket."
    elif "JPY" in symbol_u:
        base = 0.75 if atr_percentile >= 75 else 0.50
        reason = "JPY profile allows wider stops when volatility is elevated."
    elif symbol_u.startswith(("GBP", "EURGBP")) or symbol_u in {"GBPUSD", "GBPJPY"}:
        base = 0.75 if session in {"NewYork", "Overlap"} or atr_percentile >= 75 else 0.50
        reason = "GBP profile uses moderate/wide stops for session whipsaw risk."
    elif symbol_u in {"EURUSD", "USDCHF"}:
        base = 0.35 if session in {"London", "Overlap"} and atr_percentile < 75 else 0.50
        reason = "EURUSD/USDCHF liquid-session profile permits tighter stops only outside stress."

    if regime_id in {"R04", "R05", "R19", "R20", "R21", "R46", "R47"}:
        base = max(base, 0.75)
        reason += " Breakout/session impulse regime widened to reduce path-noise stop-outs."
    if regime_id in {"R09", "R10", "R23", "R30", "R38", "R39", "R40", "R50"}:
        base = max(base, 1.00)
        reason += " Stress/defensive regime requires wider validation stop if traded."
    if strategy_id in {"S1", "S2", "E1", "E3", "LS1", "LS4", "AR3", "AR4"}:
        base = max(base, 0.50)
        reason += " Sweep strategy uses wick-plus-buffer protection."
    return round(base, 4), reason


def _retarget_signal_stop(signal: dict[str, Any], sl: float, rr: float) -> dict[str, Any]:
    updated = dict(signal)
    entry = _float(updated.get("entry"))
    direction = str(updated.get("direction"))
    risk_distance = entry - sl if direction == "long" else sl - entry
    if risk_distance <= 0:
        updated["triggered"] = False
        updated["reason"] = "Invalid stop override; SL is not beyond entry."
        return updated
    updated["sl"] = float(sl)
    updated["risk_distance"] = float(risk_distance)
    updated["tp"] = float(entry + risk_distance * rr if direction == "long" else entry - risk_distance * rr)
    return updated


def _apply_stop_realism_controls(
    symbol: str,
    row: pd.Series,
    signal: dict[str, Any],
    rr: float,
    strategy_controls: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Optionally apply ATR stop grids and spread-multiple safety without changing default backtests."""
    controls = dict(strategy_controls or {})
    updated = dict(signal)
    atr = _float(row.get("atr"))
    entry = _float(updated.get("entry"))
    original_sl = _float(updated.get("sl"))
    direction = str(updated.get("direction") or "")
    strategy_id = str(updated.get("strategy_id") or "")
    diagnostics: dict[str, Any] = {
        "enabled": bool(controls),
        "stop_adjusted": False,
        "stop_blocked": False,
        "reasons": [],
        "original_sl": round(original_sl, 8),
        "original_risk_distance": round(_float(updated.get("risk_distance")), 8),
    }
    if atr <= 0 or entry <= 0 or direction not in {"long", "short"}:
        diagnostics["reasons"].append("Stop realism skipped because ATR/entry/direction is unavailable.")
        return updated, diagnostics

    override_mode = str(controls.get("stop_override_mode") or "off").lower()
    stop_atr = controls.get("stop_atr_override", controls.get("stop_atr"))
    if controls.get("use_symbol_session_stop_profile") and stop_atr in {None, "", 0, 0.0}:
        stop_atr, profile_reason = _profile_stop_atr(symbol, row, strategy_id)
        override_mode = str(controls.get("stop_profile_override_mode") or "widen_only").lower()
        diagnostics["profile_reason"] = profile_reason

    stop_atr_float = _float(stop_atr, 0.0)
    if stop_atr_float > 0 and override_mode != "off":
        target_sl = entry - atr * stop_atr_float if direction == "long" else entry + atr * stop_atr_float
        if override_mode == "replace":
            new_sl = target_sl
        elif override_mode == "tighten_only":
            new_sl = max(original_sl, target_sl) if direction == "long" else min(original_sl, target_sl)
        else:
            new_sl = min(original_sl, target_sl) if direction == "long" else max(original_sl, target_sl)
        retargeted = _retarget_signal_stop(updated, new_sl, rr)
        if not retargeted.get("triggered", True):
            diagnostics["stop_blocked"] = True
            diagnostics["reasons"].append(retargeted.get("reason", "Invalid stop override."))
            return retargeted, diagnostics
        if abs(_float(retargeted.get("sl")) - original_sl) > 1e-12:
            diagnostics["stop_adjusted"] = True
            diagnostics["reasons"].append(f"Stop {override_mode} applied at {stop_atr_float:.2f} ATR.")
        updated = retargeted
        diagnostics["stop_atr"] = stop_atr_float
        diagnostics["stop_override_mode"] = override_mode

    spread_points = _float(row.get("spread"))
    point_size = _point_size(symbol, controls)
    spread_price = spread_points * point_size
    risk_distance = _float(updated.get("risk_distance"))
    effective_multiple = risk_distance / spread_price if spread_price > 0 else None
    min_mult = _float(controls.get("min_effective_stop_spread_mult"), 0.0)
    min_mode = str(controls.get("min_effective_stop_mode") or "widen").lower()
    diagnostics.update(
        {
            "spread_points": round(spread_points, 4),
            "point_size": point_size,
            "spread_price": round(spread_price, 8),
            "effective_stop_spread_mult": round(effective_multiple, 4) if effective_multiple is not None else None,
            "min_effective_stop_spread_mult": min_mult,
            "min_effective_stop_mode": min_mode,
        }
    )
    if min_mult > 0:
        if spread_price <= 0:
            diagnostics["reasons"].append("Minimum effective stop check could not use spread because spread is missing or zero.")
        elif risk_distance < spread_price * min_mult:
            if min_mode == "block":
                diagnostics["stop_blocked"] = True
                diagnostics["reasons"].append(f"Stop distance is below {min_mult:.1f}x spread; blocked to avoid bid/ask candle noise.")
                return {**updated, "triggered": False, "reason": diagnostics["reasons"][-1]}, diagnostics
            new_distance = spread_price * min_mult
            new_sl = entry - new_distance if direction == "long" else entry + new_distance
            updated = _retarget_signal_stop(updated, new_sl, rr)
            diagnostics["stop_adjusted"] = True
            diagnostics["reasons"].append(f"Stop widened to minimum {min_mult:.1f}x spread.")
            risk_distance = _float(updated.get("risk_distance"))
            diagnostics["effective_stop_spread_mult"] = round(risk_distance / spread_price, 4) if spread_price > 0 else None

    diagnostics["final_sl"] = round(_float(updated.get("sl")), 8)
    diagnostics["final_risk_distance"] = round(_float(updated.get("risk_distance")), 8)
    updated["stop_realism"] = diagnostics
    return updated, diagnostics


def _execution_failure_checks(
    row: pd.Series,
    signal: dict[str, Any],
    cost_breakdown: dict[str, Any],
    position_size: float,
    equity: float,
    strategy_controls: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    controls = dict(strategy_controls or {})
    checks: list[dict[str, Any]] = []
    stop = signal.get("stop_realism") if isinstance(signal.get("stop_realism"), dict) else {}
    spread_pct = _float(row.get("spread_percentile"))
    total_cost_r = _float(cost_breakdown.get("total_cost_R"))
    slippage_r = _float(cost_breakdown.get("slippage_R"))
    effective_mult = stop.get("effective_stop_spread_mult")
    min_mult = _float(stop.get("min_effective_stop_spread_mult"), _float(controls.get("min_effective_stop_spread_mult"), 0.0))

    def add(name: str, status: str, reason: str) -> None:
        checks.append({"check": name, "status": status, "reason": reason})

    add("spread_failure", "WARN" if spread_pct >= 70 else "PASS", f"Spread percentile is {spread_pct:.1f}.")
    add("slippage_failure", "WARN" if slippage_r >= 0.10 or total_cost_r >= 0.25 else "PASS", f"Estimated cost is {total_cost_r:.3f}R and slippage is {slippage_r:.3f}R.")
    if effective_mult is None:
        add("bid_ask_candle_problem", "WARN", "Spread multiple is unavailable; bid/ask path cannot be validated from candles.")
    else:
        add(
            "bid_ask_candle_problem",
            "WARN" if min_mult > 0 and float(effective_mult) < min_mult else "PASS",
            f"Stop is {float(effective_mult):.1f}x spread; minimum configured is {min_mult:.1f}x.",
        )
    session = str(row.get("session") or "OffSession")
    tick_volume = _float(row.get("tick_volume"))
    add("liquidity_failure", "WARN" if session in {"Rollover", "OffSession"} or tick_volume <= 0 else "PASS", f"Session {session}, tick volume {tick_volume:.0f}.")
    add("margin_leverage_failure", "WARN" if position_size <= 0 or equity <= 0 else "PASS", f"Backtest position size {position_size:.2f}; equity {equity:.2f}.")
    mtf_score = _float(row.get("mtf_conflict_score"))
    htf_unavailable = int(row.get("htf_unavailable") or 0)
    add("multi_timeframe_sync_failure", "WARN" if htf_unavailable or mtf_score > 0 else "PASS", f"HTF unavailable={htf_unavailable}, MTF conflict score={mtf_score:.1f}.")
    data_bad = int(row.get("data_quality_bad_data_flag") or 0)
    add("data_quality_failure", "WARN" if data_bad else "PASS", str(row.get("data_quality_reasons") or "Data quality flags are clear."))
    return checks


def _mae_mfe_for_trade(df: pd.DataFrame, entry_idx: int, exit_idx: int, signal: dict[str, Any]) -> dict[str, Any]:
    """Measure adverse/favorable excursion after entry without changing trade outcome."""
    entry = float(signal["entry"])
    sl = float(signal["sl"])
    risk_distance = float(signal.get("risk_distance") or 0)
    direction = str(signal.get("direction") or "")
    if risk_distance <= 0:
        return {
            "mae_price": 0.0,
            "mfe_price": 0.0,
            "mae_R": 0.0,
            "mfe_R": 0.0,
            "mae_percent_of_stop": 0.0,
            "mfe_to_mae_ratio": 0.0,
            "max_adverse_price": entry,
            "max_favorable_price": entry,
            "bars_held": 0,
            "stop_distance": abs(entry - sl),
        }

    path = df.iloc[min(entry_idx + 1, len(df)): min(exit_idx + 1, len(df))]
    if path.empty:
        high = low = entry
    else:
        high = float(pd.to_numeric(path["high"], errors="coerce").max())
        low = float(pd.to_numeric(path["low"], errors="coerce").min())

    if direction == "long":
        adverse_price = low
        favorable_price = high
        mae_price = max(0.0, entry - adverse_price)
        mfe_price = max(0.0, favorable_price - entry)
    else:
        adverse_price = high
        favorable_price = low
        mae_price = max(0.0, adverse_price - entry)
        mfe_price = max(0.0, entry - favorable_price)

    mae_r = mae_price / risk_distance
    mfe_r = mfe_price / risk_distance
    return {
        "mae_price": round(mae_price, 6),
        "mfe_price": round(mfe_price, 6),
        "mae_R": round(mae_r, 4),
        "mfe_R": round(mfe_r, 4),
        "mae_percent_of_stop": round(mae_r * 100, 2),
        "mfe_to_mae_ratio": round(mfe_r / mae_r, 4) if mae_r > 0 else (round(mfe_r, 4) if mfe_r > 0 else 0.0),
        "max_adverse_price": round(adverse_price, 6),
        "max_favorable_price": round(favorable_price, 6),
        "bars_held": max(0, exit_idx - entry_idx),
        "stop_distance": round(risk_distance, 6),
        "entry_to_sl_R": 1.0,
    }


def _percentile(values: list[float], percentile: float) -> float:
    clean = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isnan(number):
            clean.append(number)
    if not clean:
        return 0.0
    return float(np.percentile(clean, percentile))


def _mae_mfe_row(key: dict[str, Any], trades: list[dict[str, Any]]) -> dict[str, Any]:
    mae = [float(t.get("mae_R") or 0) for t in trades]
    mfe = [float(t.get("mfe_R") or 0) for t in trades]
    winners = [t for t in trades if float(t.get("result_R") or 0) > 0]
    losers = [t for t in trades if float(t.get("result_R") or 0) < 0]
    winner_mae = [float(t.get("mae_R") or 0) for t in winners]
    loser_mfe = [float(t.get("mfe_R") or 0) for t in losers]
    stop_outs = [t for t in trades if "stop" in str(t.get("exit_reason") or "").lower()]
    near_stop_winners = [t for t in winners if float(t.get("mae_R") or 0) >= 0.75]
    inefficient_losses = [t for t in losers if float(t.get("mfe_R") or 0) >= 1.0]
    winner_capture = [
        min(2.0, max(0.0, float(t.get("gross_result_R") or t.get("result_R") or 0)) / float(t.get("mfe_R") or 0))
        for t in winners
        if float(t.get("mfe_R") or 0) > 0
    ]
    trade_count = len(trades)
    p75_winner_mae = _percentile(winner_mae, 75)
    p75_loser_mfe = _percentile(loser_mfe, 75)
    stop_out_rate = len(stop_outs) / trade_count if trade_count else 0.0
    near_stop_rate = len(near_stop_winners) / len(winners) if winners else 0.0
    inefficient_loss_rate = len(inefficient_losses) / len(losers) if losers else 0.0

    decision = "INSUFFICIENT SAMPLE"
    recommendation = "Collect at least 20 trades before changing stop placement."
    if trade_count >= 20:
        decision = "STOP OK"
        recommendation = "Current stop placement is acceptable for research; confirm with real ticks."
        if p75_winner_mae >= 0.85 or near_stop_rate >= 0.35:
            decision = "STOP TOO TIGHT REVIEW"
            recommendation = "Winning trades often use most of the stop before working; test wider stop buffers or cleaner entry confirmation."
        elif stop_out_rate >= 0.55 and p75_loser_mfe >= 0.75:
            decision = "EXIT/TRAILING REVIEW"
            recommendation = "Many stopped trades first moved favorably; test breakeven, partials, or faster invalidation logic."
        elif _percentile(mae, 75) <= 0.35 and _percentile(mfe, 50) < 1.0:
            decision = "ENTRY QUALITY REVIEW"
            recommendation = "Stops are not being stressed, but favorable excursion is weak; the entry may be late or target path poor."

    return {
        **key,
        "trade_count": trade_count,
        "avg_mae_R": round(float(np.mean(mae)) if mae else 0.0, 4),
        "median_mae_R": round(_percentile(mae, 50), 4),
        "p75_mae_R": round(_percentile(mae, 75), 4),
        "p90_mae_R": round(_percentile(mae, 90), 4),
        "avg_mfe_R": round(float(np.mean(mfe)) if mfe else 0.0, 4),
        "median_mfe_R": round(_percentile(mfe, 50), 4),
        "p75_mfe_R": round(_percentile(mfe, 75), 4),
        "p90_mfe_R": round(_percentile(mfe, 90), 4),
        "winner_p75_mae_R": round(p75_winner_mae, 4),
        "loser_p75_mfe_R": round(p75_loser_mfe, 4),
        "stop_out_rate": round(stop_out_rate, 4),
        "near_stop_winner_rate": round(near_stop_rate, 4),
        "inefficient_loss_rate": round(inefficient_loss_rate, 4),
        "avg_winner_capture_ratio": round(float(np.mean(winner_capture)) if winner_capture else 0.0, 4),
        "decision": decision,
        "recommendation": recommendation,
    }


def _mae_mfe_analysis(trades: list[dict[str, Any]]) -> dict[str, Any]:
    by_regime: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_strategy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_regime_strategy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        by_regime[str(trade.get("regime_id") or "Unknown")].append(trade)
        by_strategy[str(trade.get("strategy_id") or "Unknown")].append(trade)
        by_regime_strategy[f"{trade.get('regime_id')}_{trade.get('strategy_id')}"].append(trade)

    regime_rows = [
        _mae_mfe_row({"regime_id": key, "regime_name": group[0].get("regime_name")}, group)
        for key, group in by_regime.items()
    ]
    strategy_rows = [
        _mae_mfe_row({"strategy_id": key, "strategy_name": group[0].get("strategy_name")}, group)
        for key, group in by_strategy.items()
    ]
    combo_rows = [
        _mae_mfe_row(
            {
                "regime_strategy": key,
                "regime_id": group[0].get("regime_id"),
                "strategy_id": group[0].get("strategy_id"),
                "strategy_name": group[0].get("strategy_name"),
            },
            group,
        )
        for key, group in by_regime_strategy.items()
    ]
    all_row = _mae_mfe_row({"scope": "ALL"}, trades) if trades else {"scope": "ALL", "trade_count": 0, "decision": "NO TRADES", "recommendation": "Run a backtest with trades to calculate MAE/MFE."}
    review_rows = [row for row in combo_rows if row.get("decision") in {"STOP TOO TIGHT REVIEW", "EXIT/TRAILING REVIEW", "ENTRY QUALITY REVIEW"}]
    priority = {
        "STOP TOO TIGHT REVIEW": 4,
        "EXIT/TRAILING REVIEW": 3,
        "ENTRY QUALITY REVIEW": 2,
        "STOP OK": 1,
        "INSUFFICIENT SAMPLE": 0,
    }
    sort_key = lambda row: (priority.get(str(row.get("decision")), 0), int(row.get("trade_count") or 0))
    return {
        "summary": all_row,
        "by_regime": sorted(regime_rows, key=sort_key, reverse=True),
        "by_strategy": sorted(strategy_rows, key=sort_key, reverse=True),
        "by_regime_strategy": sorted(combo_rows, key=sort_key, reverse=True),
        "review_flags": review_rows[:20],
        "notes": [
            "MAE is maximum adverse excursion after signal-close entry, measured in initial-risk R.",
            "MFE is maximum favorable excursion before exit, measured in initial-risk R.",
            "Candle MAE/MFE uses bar high/low path and should be confirmed with MT5 real ticks for tight stops.",
        ],
    }


def _prepare_features(
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    sentiment: str,
    usd_bias: str,
    risk_sentiment: str,
    cb_divergence: str,
    macro_evidence: dict[str, Any] | None,
    use_killzone: bool,
    use_spread_filter: bool,
    use_sweeps: bool,
    regime_controls: dict[str, Any] | None = None,
    calibration: dict[str, Any] | None = None,
    data_source_controls: dict[str, Any] | None = None,
    use_feature_cache: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    macro_payload = dict(macro_evidence or {})
    macro_payload.setdefault("symbol", symbol)
    macro_payload.setdefault("start_date", start_date)
    macro_payload.setdefault("end_date", end_date)
    macro_payload.setdefault("as_of", end_date)
    candles, features, cache_meta = load_or_calculate_features(
        symbol=symbol,
        timeframe=timeframe,
        start_date=start_date,
        end_date=end_date,
        sentiment=sentiment,
        usd_bias=usd_bias,
        risk_sentiment=risk_sentiment,
        cb_divergence=cb_divergence,
        macro_evidence=macro_payload,
        data_source_controls=data_source_controls,
        use_cache=use_feature_cache,
        persist_cache=True,
    )
    if calibration:
        features = inject_calibration_columns(features, calibration)
    if not use_killzone:
        features["session"] = "Research"
    if not use_spread_filter:
        features["spread_percentile"] = 0.0
        features["spread"] = 0.0
    if not use_sweeps:
        features["sweep_high_flag"] = 0
        features["sweep_low_flag"] = 0
    raw_regimes = []
    modifier_lists = []
    hard_blocks = []
    for _, row in features.iterrows():
        row_dict = row.to_dict()
        modifiers = detect_modifiers(row_dict)
        regime = detect_regime(row_dict)
        raw_regimes.append(regime)
        modifier_lists.append(modifiers["modifiers"])
        hard_blocks.append(modifiers["hard_block"])
    stable_regimes = _apply_regime_hysteresis(raw_regimes, regime_controls)
    features = pd.concat(
        [
            features,
            pd.DataFrame(
                {
                    "raw_regime_id": [r["regime_id"] for r in stable_regimes],
                    "raw_regime_name": [r["regime_name"] for r in stable_regimes],
                    "raw_regime_confidence": [r["confidence"] for r in stable_regimes],
                    "raw_regime_failed_conditions": [r.get("conditions_failed", []) for r in stable_regimes],
                    "regime_id": [r["stable_regime_id"] for r in stable_regimes],
                    "regime_name": [r["stable_regime_name"] for r in stable_regimes],
                    "regime_confidence": [r["stable_regime_confidence"] for r in stable_regimes],
                    "regime_failed_conditions": [r.get("stable_regime_failed_conditions", []) for r in stable_regimes],
                    "regime_hysteresis_applied": [r["regime_hysteresis_applied"] for r in stable_regimes],
                    "regime_hysteresis_reason": [r["regime_hysteresis_reason"] for r in stable_regimes],
                    "regime_hysteresis_pending": [r["regime_hysteresis_pending"] for r in stable_regimes],
                    "modifiers": modifier_lists,
                    "hard_block": hard_blocks,
                },
                index=features.index,
            ),
        ],
        axis=1,
    )
    features.attrs["feature_cache"] = cache_meta
    return candles, features


def _expected_bars(timeframe: str, start_date: str, end_date: str) -> int | None:
    try:
        start = pd.Timestamp(start_date, tz="UTC")
        end = pd.Timestamp(end_date, tz="UTC")
        minutes = TIMEFRAME_MINUTES.get(timeframe.upper())
        if not minutes:
            return None
        return max(0, int((end - start).total_seconds() // 60 // minutes) + 1)
    except Exception:
        return None


def _bucket_counts(series: pd.Series, buckets: list[tuple[str, float, float]]) -> dict[str, int]:
    cleaned = pd.to_numeric(series, errors="coerce")
    return {label: int(((cleaned >= low) & (cleaned < high)).sum()) for label, low, high in buckets}


def _data_health(candles: pd.DataFrame, features: pd.DataFrame, request: dict[str, Any], tradable_rows: int) -> dict[str, Any]:
    timestamps = pd.to_datetime(candles["timestamp"], utc=True) if "timestamp" in candles else pd.Series(dtype="datetime64[ns, UTC]")
    expected = _expected_bars(request["timeframe"], request["start_date"], request["end_date"])
    required = ["adx", "er", "atr_percentile", "bb_width_percentile", "prev_swing_high", "prev_swing_low"]
    nan_rows = int(features[required].isna().any(axis=1).sum()) if all(col in features for col in required) else 0
    spread_available = bool("spread" in candles and pd.to_numeric(candles["spread"], errors="coerce").fillna(0).abs().sum() > 0)
    warmup_rows = int(pd.to_numeric(features.get("data_quality_warmup_flag"), errors="coerce").fillna(0).sum())
    bad_data_rows = int(pd.to_numeric(features.get("data_quality_bad_data_flag"), errors="coerce").fillna(0).sum())
    htf_unavailable_rows = int(pd.to_numeric(features.get("htf_unavailable"), errors="coerce").fillna(0).sum())
    hysteresis_rows = int(pd.to_numeric(features.get("regime_hysteresis_applied"), errors="coerce").fillna(0).sum())
    feature_cache = dict(features.attrs.get("feature_cache") or {})
    return {
        "source": "MT5 / SQLite candles",
        "symbol": request["symbol"],
        "timeframe": request["timeframe"],
        "start_date": request["start_date"],
        "end_date": request["end_date"],
        "bars_expected_calendar": expected,
        "bars_loaded": int(len(candles)),
        "candles_missing_estimate": max(0, expected - len(candles)) if expected is not None else None,
        "duplicate_candles": int(candles.duplicated(subset=["timestamp"]).sum()) if "timestamp" in candles else 0,
        "first_candle_time": timestamps.min().isoformat() if len(timestamps) else None,
        "last_candle_time": timestamps.max().isoformat() if len(timestamps) else None,
        "spread_available": spread_available,
        "htf_data_available": htf_unavailable_rows == 0,
        "htf_derived_by_resampling": True,
        "feature_rows_with_nan": nan_rows,
        "warmup_rows": warmup_rows,
        "bad_data_rows": bad_data_rows,
        "htf_unavailable_rows": htf_unavailable_rows,
        "raw_regime_switches": _switch_count(features.get("raw_regime_id", [])),
        "stable_regime_switches": _switch_count(features.get("regime_id", [])),
        "hysteresis_suppressed_flips": hysteresis_rows,
        "regime_hysteresis_enabled": bool((features.get("regime_hysteresis_reason", pd.Series(dtype=str)).astype(str).str.contains("Hysteresis disabled", regex=False).sum() == 0) if len(features) else False),
        "warmup_label": "R40-WARMUP",
        "bad_data_label": "R40-BAD-DATA",
        "tradable_rows_after_filters": int(tradable_rows),
        "feature_cache": feature_cache,
        "feature_cache_status": feature_cache.get("status", "UNKNOWN"),
        "feature_cache_hit": bool(feature_cache.get("cache_hit")),
    }


def _feature_summary(features: pd.DataFrame) -> dict[str, Any]:
    def stats(col: str) -> dict[str, float | None]:
        s = pd.to_numeric(features.get(col), errors="coerce")
        return {
            "avg": round(float(s.mean()), 4) if s.notna().any() else None,
            "min": round(float(s.min()), 4) if s.notna().any() else None,
            "max": round(float(s.max()), 4) if s.notna().any() else None,
        }

    spread_by_session = []
    if "session" in features and "spread" in features:
        for session, group in features.groupby("session", dropna=False):
            spreads = pd.to_numeric(group.get("spread"), errors="coerce").dropna()
            spread_pct = pd.to_numeric(group.get("spread_percentile"), errors="coerce").dropna()
            spread_by_session.append({
                "session": str(session or "UNKNOWN"),
                "rows": int(len(group)),
                "avg_spread": round(float(spreads.mean()), 4) if len(spreads) else 0.0,
                "spread_p90": round(float(spreads.quantile(0.90)), 4) if len(spreads) else 0.0,
                "avg_spread_percentile": round(float(spread_pct.mean()), 2) if len(spread_pct) else 0.0,
                "spread_stress_count": int((spread_pct >= 90).sum()) if len(spread_pct) else 0,
            })

    htf = features.get("htf_bias", pd.Series(dtype=str))
    ltf = features.get("ltf_bias", pd.Series(dtype=str))
    modifiers = [m for mods in features.get("modifiers", []) for m in (mods or [])]
    stat_vote = features.get("stat_regime_vote", pd.Series(dtype=str)).astype(str) if "stat_regime_vote" in features else pd.Series(dtype=str)
    hmm_state = features.get("hmm_state", pd.Series(dtype=str)).astype(str) if "hmm_state" in features else pd.Series(dtype=str)
    return {
        "rows": int(len(features)),
        "adx": stats("adx"),
        "er": stats("er"),
        "ema_slope": stats("ema_slope"),
        "hurst_exponent": stats("hurst_exponent"),
        "fractal_dimension": stats("fractal_dimension"),
        "kalman_slope": stats("kalman_slope"),
        "garch_vol_forecast": stats("garch_vol_forecast"),
        "garch_vol_percentile": stats("garch_vol_percentile"),
        "structural_break_score": stats("structural_break_score"),
        "structural_break_count": int(pd.to_numeric(features.get("structural_break_flag"), errors="coerce").fillna(0).sum()),
        "hmm_state_probability": stats("hmm_state_probability"),
        "hmm_trend_probability": stats("hmm_trend_probability"),
        "hmm_range_probability": stats("hmm_range_probability"),
        "hmm_stress_probability": stats("hmm_stress_probability"),
        "stat_regime_confidence": stats("stat_regime_confidence"),
        "stat_regime_vote_counts": stat_vote.value_counts().to_dict() if len(stat_vote) else {},
        "hmm_state_counts": hmm_state.value_counts().to_dict() if len(hmm_state) else {},
        "stat_regime_disagreement_count": int(pd.to_numeric(features.get("stat_regime_disagreement"), errors="coerce").fillna(0).sum()),
        "latest_stat_regime_vote": features.get("stat_regime_vote", pd.Series(["--"])).iloc[-1] if len(features) else "--",
        "latest_stat_regime_confidence": round(float(features.get("stat_regime_confidence", pd.Series([0])).iloc[-1] or 0), 4) if len(features) else 0,
        "latest_hmm_state": features.get("hmm_state", pd.Series(["--"])).iloc[-1] if len(features) else "--",
        "latest_stat_regime_summary": features.get("stat_regime_summary", pd.Series([""])).iloc[-1] if len(features) else "",
        "drift_strength": stats("drift_strength"),
        "channel_slope": stats("channel_slope"),
        "atr_percentile_distribution": _bucket_counts(features["atr_percentile"], [("low_0_25", 0, 25), ("normal_25_75", 25, 75), ("high_75_90", 75, 90), ("shock_90_100", 90, 101)]),
        "spread_percentile_distribution": _bucket_counts(features["spread_percentile"], [("normal_0_70", 0, 70), ("caution_70_90", 70, 90), ("stress_90_100", 90, 101)]),
        "spread_by_session": spread_by_session,
        "htf_bullish_count": int((htf == "bullish").sum()),
        "htf_bearish_count": int((htf == "bearish").sum()),
        "ltf_bullish_count": int((ltf == "bullish").sum()),
        "ltf_bearish_count": int((ltf == "bearish").sum()),
        "mtf_agreement_count": int(((htf == ltf) & (htf != "neutral")).sum()) if len(features) else 0,
        "mtf_conflict_count": int(((htf != ltf) & (htf != "neutral") & (ltf != "neutral")).sum()) if len(features) else 0,
        "sweep_high_count": int(pd.to_numeric(features.get("sweep_high_flag"), errors="coerce").fillna(0).sum()),
        "sweep_low_count": int(pd.to_numeric(features.get("sweep_low_flag"), errors="coerce").fillna(0).sum()),
        "near_range_high_count": int(pd.to_numeric(features.get("near_range_high"), errors="coerce").fillna(0).sum()),
        "near_range_low_count": int(pd.to_numeric(features.get("near_range_low"), errors="coerce").fillna(0).sum()),
        "false_upside_breakout_count": int(pd.to_numeric(features.get("false_upside_breakout"), errors="coerce").fillna(0).sum()),
        "false_downside_breakout_count": int(pd.to_numeric(features.get("false_downside_breakout"), errors="coerce").fillna(0).sum()),
        "opening_range_breakout_up_count": int(pd.to_numeric(features.get("orb_up"), errors="coerce").fillna(0).sum()),
        "opening_range_breakout_down_count": int(pd.to_numeric(features.get("orb_down"), errors="coerce").fillna(0).sum()),
        "chop_score": stats("chop_score"),
        "dead_market_score": stats("dead_market_score"),
        "trend_weakening_count": int(pd.to_numeric(features.get("trend_weakening"), errors="coerce").fillna(0).sum()),
        "bull_pullback_failure_count": int(pd.to_numeric(features.get("bull_pullback_failure"), errors="coerce").fillna(0).sum()),
        "bear_pullback_failure_count": int(pd.to_numeric(features.get("bear_pullback_failure"), errors="coerce").fillna(0).sum()),
        "vwap_extreme_high_count": int(pd.to_numeric(features.get("vwap_extreme_high"), errors="coerce").fillna(0).sum()),
        "vwap_extreme_low_count": int(pd.to_numeric(features.get("vwap_extreme_low"), errors="coerce").fillna(0).sum()),
        "post_stress_normalization_count": int(pd.to_numeric(features.get("post_stress_normalization"), errors="coerce").fillna(0).sum()),
        "gap_count": int(pd.to_numeric(features.get("gap_flag"), errors="coerce").fillna(0).sum()),
        "data_quality_issue_count": int(pd.to_numeric(features.get("data_quality_flag"), errors="coerce").fillna(0).sum()),
        "data_quality_warmup_count": int(pd.to_numeric(features.get("data_quality_warmup_flag"), errors="coerce").fillna(0).sum()),
        "data_quality_bad_data_count": int(pd.to_numeric(features.get("data_quality_bad_data_flag"), errors="coerce").fillna(0).sum()),
        "r40_warmup_count": int((features.get("data_quality_category", pd.Series(dtype=str)) == "R40-WARMUP").sum()),
        "r40_bad_data_count": int(features.get("data_quality_category", pd.Series(dtype=str)).astype(str).str.contains("R40-BAD-DATA", regex=False).sum()) if "data_quality_category" in features else 0,
        "raw_regime_switches": _switch_count(features.get("raw_regime_id", [])),
        "stable_regime_switches": _switch_count(features.get("regime_id", [])),
        "hysteresis_suppressed_flips": int(pd.to_numeric(features.get("regime_hysteresis_applied"), errors="coerce").fillna(0).sum()),
        "mtf_conflict_score": stats("mtf_conflict_score"),
        "distance_from_vwap_atr": stats("distance_from_vwap_atr"),
        "gap_atr": stats("gap_atr"),
        "overlap_trend_count": int(pd.to_numeric(features.get("overlap_trend"), errors="coerce").fillna(0).sum()),
        "asia_range_count": int(pd.to_numeric(features.get("asia_range"), errors="coerce").fillna(0).sum()),
        "month_end_count": int(pd.to_numeric(features.get("is_month_end"), errors="coerce").fillna(0).sum()),
        "fixing_window_count": int(pd.to_numeric(features.get("is_fixing_window"), errors="coerce").fillna(0).sum()),
        "usd_bias": features.get("usd_bias", pd.Series(["NEUTRAL"])).iloc[-1] if len(features) else "NEUTRAL",
        "risk_sentiment": features.get("risk_sentiment", pd.Series(["NEUTRAL"])).iloc[-1] if len(features) else "NEUTRAL",
        "cb_divergence": features.get("cb_divergence", pd.Series(["NEUTRAL"])).iloc[-1] if len(features) else "NEUTRAL",
        "modifier_counts": dict(Counter(modifiers)),
    }


def _regime_confidence_summary(features: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    total = len(features)
    for (regime_id, regime_name), group in features.groupby(["regime_id", "regime_name"], dropna=False):
        if regime_id == "NONE":
            continue
        confidence = pd.to_numeric(group["regime_confidence"], errors="coerce")
        modifiers = [m for mods in group.get("modifiers", []) for m in (mods or [])]
        rows.append({
            "regime_id": regime_id,
            "regime_name": regime_name,
            "candles_detected": int(len(group)),
            "active_percent": round(len(group) / total * 100, 2) if total else 0,
            "average_confidence": round(float(confidence.mean()), 4) if confidence.notna().any() else 0,
            "min_confidence": round(float(confidence.min()), 4) if confidence.notna().any() else 0,
            "max_confidence": round(float(confidence.max()), 4) if confidence.notna().any() else 0,
            "most_common_modifier": Counter(modifiers).most_common(1)[0][0] if modifiers else None,
        })
    return sorted(rows, key=lambda x: x["regime_id"])


def _strict_block_reasons(row: pd.Series, modifiers: dict[str, Any], alpha: dict[str, Any], options: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    regime_id = row.get("regime_id")
    mods = set(modifiers.get("modifiers", []))
    session = row.get("session")
    spreadp = float(row.get("spread_percentile") or 0)

    for reason in modifiers.get("hard_block_reasons", []):
        reasons.append(str(reason))

    if options.get("strict_clean_trend") and regime_id in {"R01", "R02"}:
        active_strict = set(STRICT_BLOCK_MODIFIERS)
        if not options.get("reject_m08_conflict", True):
            active_strict.discard("M08")
        if not options.get("reject_m11_exhaustion", True):
            active_strict.discard("M11")
        if not options.get("reject_rollover", True):
            active_strict.discard("M13")
        if not options.get("reject_news", True):
            active_strict.discard("M07")
        found = sorted(mods & active_strict)
        if found:
            reasons.append(f"Strict clean-trend block: {', '.join(found)} present.")
        if "M12" not in mods:
            reasons.append("Strict clean-trend block: M12 multi-timeframe agreement is required.")

    if options.get("strict_regime_validation"):
        failed = row.get("regime_failed_conditions") or []
        if isinstance(failed, str):
            failed = [failed]
        failed = [str(item) for item in failed if str(item).strip()]
        critical_terms = [
            "bias is",
            "data",
            "missing",
            "invalid",
            "duplicate",
            "zero-range",
            "news flag is false",
            "session is not rollover",
            "htf unavailable",
            "manual review",
        ]
        critical_failed = [
            item for item in failed
            if any(term in item.lower() for term in critical_terms)
        ]
        max_failed = int(options.get("strict_regime_max_failed_conditions", 0))
        min_confidence = float(options.get("strict_regime_min_confidence", 0.75))
        confidence = float(row.get("regime_confidence") or 0)
        if critical_failed:
            reasons.append(f"Strict regime validation: critical failed conditions: {'; '.join(critical_failed)}.")
        elif failed and (len(failed) > max_failed or confidence < min_confidence):
            reasons.append(
                f"Strict regime validation: {len(failed)} failed conditions with confidence {confidence:.2f}; "
                f"allowed failed <= {max_failed} and confidence >= {min_confidence:.2f}. Failed: {'; '.join(failed)}."
            )

    if options.get("reject_trend_weakening") and int(row.get("trend_weakening") or 0) == 1:
        reasons.append("Strict validation: trend weakening is active.")

    if regime_id in {"R01", "R02"}:
        min_er = float(options.get("min_clean_trend_er", 0.25))
        if options.get("reject_low_er_clean_trend") and float(row.get("er") or 0) < min_er:
            reasons.append(f"Strict clean-trend block: ER {float(row.get('er') or 0):.2f} is below {min_er:.2f}.")
        adx = float(row.get("adx") or 0)
        adx_min = float(options.get("clean_trend_adx_min", 18))
        adx_max = float(options.get("clean_trend_adx_max", 35))
        if options.get("reject_adx_outside_clean_trend") and not adx_min <= adx <= adx_max:
            reasons.append(f"Strict clean-trend block: ADX {adx:.2f} is outside {adx_min:g}-{adx_max:g}.")

    mtf_score = float(row.get("mtf_conflict_score") or 0)
    if options.get("reject_mtf_conflict_score") and regime_id not in {"R31", "R37"} and mtf_score > float(options.get("max_mtf_conflict_score", 0)):
        reasons.append(f"Strict validation: MTF conflict score {mtf_score:.0f} is above 0.")

    if options.get("use_statistical_regime") and options.get("statistical_regime_mode") == "hard_filter":
        stat_vote = str(row.get("stat_regime_vote") or "neutral").lower()
        stat_confidence = float(row.get("stat_regime_confidence") or 0)
        min_stat_confidence = float(options.get("stat_min_confidence", 0.55))
        structural_break_score = float(row.get("structural_break_score") or 0)
        structural_break_active = int(row.get("structural_break_flag") or 0) == 1
        max_break_score = float(options.get("stat_max_structural_break_score", 2.5))
        if stat_confidence < min_stat_confidence:
            reasons.append(
                f"Statistical regime hard filter: ensemble confidence {stat_confidence:.2f} is below {min_stat_confidence:.2f}."
            )
        if stat_vote == "stress" and regime_id not in STAT_STRESS_REGIMES:
            reasons.append(f"Statistical regime hard filter: ensemble vote is stress, not tradable {regime_id}.")
        if regime_id in STAT_TREND_REGIMES and stat_vote not in {"trend"}:
            reasons.append(f"Statistical regime hard filter: {regime_id} requires trend vote; got {stat_vote}.")
        if regime_id in STAT_RANGE_REGIMES and stat_vote not in {"range"}:
            reasons.append(f"Statistical regime hard filter: {regime_id} requires range vote; got {stat_vote}.")
        if (
            options.get("stat_block_structural_break", True)
            and structural_break_active
            and structural_break_score >= max_break_score
            and regime_id not in STAT_STRESS_REGIMES | {"R31"}
        ):
            reasons.append(
                f"Statistical regime hard filter: structural break score {structural_break_score:.2f} is above {max_break_score:.2f}."
            )

    if options.get("killzone_mode") == "hard_filter":
        allowed_sessions = set(options.get("allowed_sessions") or TREND_KILLZONES)
        if regime_id in {"R01", "R02", "R04", "R05", "R11", "R12", "R13", "R14", "R21", "R25", "R26", "R27", "R28", "R29", "R41", "R44", "R46", "R47"} and session not in allowed_sessions:
            reasons.append(f"Kill-zone hard filter: {regime_id} trend trades require {', '.join(sorted(allowed_sessions))}; found {session}.")
        if regime_id == "R03" and session not in VALID_SESSIONS:
            reasons.append(f"Kill-zone hard filter: range/sweep research blocks {session}.")

    max_spread = float(options.get("max_spread_percentile", 70))
    if options.get("spread_filter_mode") == "hard_filter" and spreadp >= max_spread:
        reasons.append(f"Spread hard filter: spread percentile {spreadp:.1f} is above threshold {max_spread:.1f}.")

    min_alpha = float(options.get("min_alpha_score", 5))
    if options.get("use_alpha") and options.get("alpha_mode") == "hard_minimum" and float(alpha.get("alpha_score") or 0) < min_alpha:
        reasons.append(f"Alpha hard minimum: score {alpha.get('alpha_score')} is below threshold {min_alpha}.")

    return reasons


def _bool_option(source: dict[str, Any], key: str, default: bool = True) -> bool:
    return bool(source.get(key, default))


def _pattern_options(request: dict[str, Any]) -> dict[str, Any]:
    pattern_engine = request.get("pattern_engine") if isinstance(request.get("pattern_engine"), dict) else {}
    ict_settings = pattern_engine.get("ict_settings") if isinstance(pattern_engine.get("ict_settings"), dict) else {}
    vwap_settings = pattern_engine.get("vwap_settings") if isinstance(pattern_engine.get("vwap_settings"), dict) else {}
    round_settings = pattern_engine.get("round_number_settings") if isinstance(pattern_engine.get("round_number_settings"), dict) else {}

    def val(key: str, default: Any) -> Any:
        if key in pattern_engine:
            return pattern_engine[key]
        if key in ict_settings:
            return ict_settings[key]
        if key in vwap_settings:
            return vwap_settings[key]
        if key in round_settings:
            return round_settings[key]
        return request.get(key, default)

    use_mvwap = val("use_mvwap", val("use_moving_vwap", True))
    return {
        "use_patterns": bool(val("use_patterns", True)),
        "use_ict": bool(val("use_ict", True)),
        "use_fvg": bool(val("use_fvg", True)),
        "use_order_blocks": bool(val("use_order_blocks", True)),
        "use_bos": bool(val("use_bos", True)),
        "use_mss": bool(val("use_mss", True)),
        "use_liquidity_pools": bool(val("use_liquidity_pools", True)),
        "use_round_numbers": bool(val("use_round_numbers", True)),
        "use_vwap": bool(val("use_vwap", True)),
        "use_mvwap": bool(use_mvwap),
        "use_moving_vwap": bool(use_mvwap),
        "use_session_vwap": bool(val("use_session_vwap", True)),
        "pattern_score_mode": str(val("pattern_score_mode", "score_only")),
        "min_pattern_score": float(val("min_pattern_score", 2)),
        "fvg_min_size_atr": float(val("fvg_min_size_atr", 0.20)),
        "fvg_max_age_bars": int(val("fvg_max_age_bars", 30)),
        "ob_displacement_body_ratio_min": float(val("ob_displacement_body_ratio_min", 0.60)),
        "ob_displacement_candle_range_atr_min": float(val("ob_displacement_candle_range_atr_min", 1.20)),
        "ob_max_age_bars": int(val("ob_max_age_bars", 60)),
        "vwap_reversion_distance_atr": float(val("vwap_reversion_distance_atr", 1.50)),
        "bos_atr_buffer": float(val("bos_atr_buffer", 0.10)),
        "round_number_tolerance_atr": float(val("near_round_number_tolerance_atr", 0.25)),
    }


def _pattern_block_reasons(pattern_result: dict[str, Any], options: dict[str, Any]) -> list[str]:
    if not options.get("use_patterns", True):
        return []
    if options.get("pattern_score_mode") != "hard_minimum":
        return []
    score = float(pattern_result.get("pattern_score") or 0)
    min_score = float(options.get("min_pattern_score", 2))
    if score < min_score:
        return [f"Pattern hard minimum: score {score:.2f} is below threshold {min_score:.2f}."]
    return []


def _setup_context(row: pd.Series) -> dict[str, Any]:
    return {
        "adx": round(float(row.get("adx") or 0), 4),
        "er": round(float(row.get("er") or 0), 4),
        "atr_percentile": round(float(row.get("atr_percentile") or 0), 2),
        "spread": round(float(row.get("spread") or 0), 4),
        "spread_percentile": round(float(row.get("spread_percentile") or 0), 2),
        "mtf_conflict_score": round(float(row.get("mtf_conflict_score") or 0), 2),
        "distance_from_ema20_atr": round(float(row.get("distance_from_ema20_atr") or 0), 4),
        "distance_from_vwap_atr": round(float(row.get("distance_from_vwap_atr") or 0), 4),
        "gap_atr": round(float(row.get("gap_atr") or 0), 4),
        "candle_range_atr": round(float(row.get("candle_range_atr") or 0), 4),
        "hurst_exponent": round(float(row.get("hurst_exponent") or 0), 4),
        "fractal_dimension": round(float(row.get("fractal_dimension") or 0), 4),
        "kalman_slope": round(float(row.get("kalman_slope") or 0), 4),
        "garch_vol_percentile": round(float(row.get("garch_vol_percentile") or 0), 2),
        "structural_break_score": round(float(row.get("structural_break_score") or 0), 4),
        "structural_break_flag": int(row.get("structural_break_flag") or 0),
        "hmm_state": row.get("hmm_state") or "",
        "hmm_state_probability": round(float(row.get("hmm_state_probability") or 0), 4),
        "stat_regime_vote": row.get("stat_regime_vote") or "",
        "stat_regime_confidence": round(float(row.get("stat_regime_confidence") or 0), 4),
        "stat_regime_summary": row.get("stat_regime_summary") or "",
        "trend_weakening": int(row.get("trend_weakening") or 0),
        "bull_pullback_failure": int(row.get("bull_pullback_failure") or 0),
        "bear_pullback_failure": int(row.get("bear_pullback_failure") or 0),
        "vwap_extreme_high": int(row.get("vwap_extreme_high") or 0),
        "vwap_extreme_low": int(row.get("vwap_extreme_low") or 0),
        "post_stress_normalization": int(row.get("post_stress_normalization") or 0),
        "gap_flag": int(row.get("gap_flag") or 0),
        "raw_regime_id": row.get("raw_regime_id"),
        "raw_regime_name": row.get("raw_regime_name"),
        "raw_regime_confidence": round(float(row.get("raw_regime_confidence") or 0), 4),
        "stable_regime_id": row.get("regime_id"),
        "stable_regime_name": row.get("regime_name"),
        "regime_hysteresis_applied": int(row.get("regime_hysteresis_applied") or 0),
        "regime_hysteresis_reason": row.get("regime_hysteresis_reason") or "",
        "data_quality_flag": int(row.get("data_quality_flag") or 0),
        "data_quality_category": row.get("data_quality_category") or "OK",
        "data_quality_warmup_flag": int(row.get("data_quality_warmup_flag") or 0),
        "data_quality_bad_data_flag": int(row.get("data_quality_bad_data_flag") or 0),
        "data_quality_reasons": row.get("data_quality_reasons") or "",
        "data_quality_warmup_reasons": row.get("data_quality_warmup_reasons") or "",
        "data_quality_bad_data_reasons": row.get("data_quality_bad_data_reasons") or "",
    }


def _skipped_payload(
    row: pd.Series,
    signal: dict[str, Any],
    modifiers: dict[str, Any],
    alpha: dict[str, Any],
    reasons: list[str],
    pattern_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pattern_result = pattern_result or {"patterns_detected": [], "pattern_score": 0.0, "pattern_decision": "OFF", "pattern_summary": ""}
    return {
        "time": row["timestamp"].isoformat(),
        "regime_candidate": f"{row.get('regime_id')} {row.get('regime_name')}",
        "strategy_candidate": f"{signal.get('strategy_id')} {signal.get('strategy_name')}",
        "decision": "BLOCKED",
        "block_reason": "; ".join(reasons),
        "alpha_score": alpha.get("alpha_score"),
        "alpha_components": alpha.get("components", {}),
        "patterns_detected": pattern_result.get("patterns_detected", []),
        "pattern_score": pattern_result.get("pattern_score", 0.0),
        "pattern_decision": pattern_result.get("pattern_decision", "OFF"),
        "pattern_summary": pattern_result.get("pattern_summary", ""),
        "final_score": round(float(alpha.get("alpha_score") or 0) + float(pattern_result.get("pattern_score") or 0), 2),
        "failed_condition": reasons[0] if reasons else None,
        "session": row.get("session"),
        "regime_id": row.get("regime_id"),
        "regime_name": row.get("regime_name"),
        "spread_at_entry": round(float(row.get("spread") or 0), 4),
        "spread_percentile": round(float(row.get("spread_percentile") or 0), 2),
        "modifiers": modifiers.get("modifiers", []),
        "distance_from_ema20_atr": round(float(row.get("distance_from_ema20_atr") or 0), 4),
        "data_quality_category": row.get("data_quality_category") or "OK",
        "data_quality_reasons": row.get("data_quality_reasons") or "",
        "setup_context": _setup_context(row),
    }


def _group_performance(trades: list[dict[str, Any]], key_func, meta_func, rr: float) -> list[dict[str, Any]]:
    groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        groups[key_func(trade)].append(trade)
    return [_performance_from_trades(meta_func(key, group), group, rr) for key, group in groups.items()]


def _pattern_performance(trades: list[dict[str, Any]], rr: float) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    names: dict[str, str] = {}
    for trade in trades:
        positive = [p for p in trade.get("patterns_detected", []) if float(p.get("score") or 0) > 0]
        if not positive:
            groups["NO_PATTERN"].append(trade)
            names["NO_PATTERN"] = "No Positive Pattern"
            continue
        for pattern in positive:
            pid = str(pattern.get("pattern_id") or "UNKNOWN_PATTERN")
            groups[pid].append(trade)
            names[pid] = str(pattern.get("pattern_name") or pid)
    return [
        _performance_from_trades({"pattern_id": key, "pattern_name": names.get(key, key)}, group, rr)
        for key, group in groups.items()
    ]


def _spread_slippage_diagnostics(
    symbol: str,
    features: pd.DataFrame,
    trades: list[dict[str, Any]],
    skipped_setups: list[dict[str, Any]],
) -> dict[str, Any]:
    """Research visibility for spread/slippage pressure without changing trade decisions."""

    def avg(values: list[float]) -> float:
        return round(float(np.mean(values)), 6) if values else 0.0

    def p90(series: pd.Series) -> float:
        values = pd.to_numeric(series, errors="coerce").dropna()
        return round(float(values.quantile(0.90)), 4) if len(values) else 0.0

    cost_words = ("spread", "cost", "slippage", "rollover")
    cost_failed_by_regime: Counter[str] = Counter()
    all_candidates_by_regime: Counter[str] = Counter()
    for trade in trades:
        rid = str(trade.get("regime_id") or "UNKNOWN")
        all_candidates_by_regime[rid] += 1
    for skipped in skipped_setups:
        rid = str(skipped.get("regime_id") or str(skipped.get("regime_candidate") or "UNKNOWN").split(" ")[0])
        reason = str(skipped.get("block_reason") or skipped.get("failed_condition") or "").lower()
        all_candidates_by_regime[rid] += 1
        if any(word in reason for word in cost_words):
            cost_failed_by_regime[rid] += 1

    session_rows = []
    if "session" in features and "spread" in features:
        trades_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for trade in trades:
            trades_by_session[str(trade.get("session") or "UNKNOWN")].append(trade)
        for session, group in features.groupby("session", dropna=False):
            session_key = str(session or "UNKNOWN")
            session_trades = trades_by_session.get(session_key, [])
            cost_values = [float(t.get("total_cost_R") or 0) for t in session_trades]
            slippage_values = [float(t.get("estimated_slippage_R") or 0) for t in session_trades]
            slippage_points = [float(t.get("estimated_slippage_points") or 0) for t in session_trades]
            spreads = pd.to_numeric(group.get("spread"), errors="coerce").dropna()
            session_rows.append({
                "session": session_key,
                "feature_rows": int(len(group)),
                "trade_count": len(session_trades),
                "avg_spread": round(float(spreads.mean()), 4) if len(spreads) else 0.0,
                "spread_p90": p90(group.get("spread")),
                "avg_spread_percentile": round(float(pd.to_numeric(group.get("spread_percentile"), errors="coerce").mean()), 2) if len(group) else 0.0,
                "slippage_estimate_R": avg(slippage_values),
                "slippage_estimate_points": avg(slippage_points),
                "avg_cost_R": avg(cost_values),
                "total_cost_R": round(sum(cost_values), 4),
            })

    regime_rows = []
    trades_by_regime: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        trades_by_regime[str(trade.get("regime_id") or "UNKNOWN")].append(trade)
    regime_names = {str(t.get("regime_id")): t.get("regime_name") for t in trades}
    for rid, group in features.groupby("regime_id", dropna=False):
        regime_id = str(rid or "UNKNOWN")
        if regime_id == "NONE":
            continue
        regime_trades = trades_by_regime.get(regime_id, [])
        spreads = [float(t.get("spread_at_entry") or 0) for t in regime_trades]
        cost_failures = cost_failed_by_regime.get(regime_id, 0)
        candidates = all_candidates_by_regime.get(regime_id, len(regime_trades))
        spread_pct = pd.to_numeric(group.get("spread_percentile"), errors="coerce").fillna(0)
        regime_rows.append({
            "regime_id": regime_id,
            "regime_name": regime_names.get(regime_id) or str(group.get("regime_name", pd.Series([regime_id])).iloc[0]),
            "trade_count": len(regime_trades),
            "avg_spread": avg(spreads),
            "spread_stress_count": int((spread_pct >= 90).sum()),
            "cost_blocked_setups": int(cost_failures),
            "candidate_count": int(candidates),
            "failed_cost_percent": round((cost_failures / candidates) * 100, 2) if candidates else 0.0,
            "avg_cost_R": avg([float(t.get("total_cost_R") or 0) for t in regime_trades]),
        })

    symbol_trade_spreads = [float(t.get("spread_at_entry") or 0) for t in trades]
    session_cost_rank = sorted(
        [row for row in session_rows if row["trade_count"] > 0],
        key=lambda row: (row["avg_cost_R"], row["avg_spread"], row["session"]),
    )
    symbol_rows = [{
        "symbol": symbol,
        "trade_count": len(trades),
        "avg_spread": avg(symbol_trade_spreads),
        "avg_cost_R": avg([float(t.get("total_cost_R") or 0) for t in trades]),
        "best_session": session_cost_rank[0]["session"] if session_cost_rank else "--",
        "worst_session": session_cost_rank[-1]["session"] if session_cost_rank else "--",
    }]
    return {
        "session": session_rows,
        "regime": regime_rows,
        "symbol": symbol_rows,
        "notes": [
            "Spread diagnostics use candle spread fields from MT5/CSV when available.",
            "Slippage estimate is model-based unless imported MT5 tester reports supply broker-realized values.",
            "Failed cost percent counts setup candidates blocked by spread/cost/slippage/rollover reasons.",
        ],
    }


def _execution_failure_summary(trades: list[dict[str, Any]], skipped_setups: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    for trade in trades:
        for check in trade.get("execution_failure_checks") or []:
            name = str(check.get("check") or "unknown")
            counts[name] += 1
            if str(check.get("status") or "").upper() != "PASS":
                warning_counts[name] += 1
    skipped_reason_counts = Counter()
    failure_words = {
        "spread": "spread_failure",
        "slippage": "slippage_failure",
        "bid/ask": "bid_ask_candle_problem",
        "liquidity": "liquidity_failure",
        "rollover": "liquidity_failure",
        "margin": "margin_leverage_failure",
        "leverage": "margin_leverage_failure",
        "mtf": "multi_timeframe_sync_failure",
        "multi-timeframe": "multi_timeframe_sync_failure",
        "data": "data_quality_failure",
    }
    for skipped in skipped_setups:
        text = str(skipped.get("block_reason") or skipped.get("failed_condition") or "").lower()
        for needle, bucket in failure_words.items():
            if needle in text:
                skipped_reason_counts[bucket] += 1
    rows = []
    for name in sorted(set(counts) | set(warning_counts) | set(skipped_reason_counts)):
        rows.append(
            {
                "failure_type": name,
                "trade_checks": counts.get(name, 0),
                "trade_warnings": warning_counts.get(name, 0),
                "skipped_blocks": skipped_reason_counts.get(name, 0),
                "status": "REVIEW" if warning_counts.get(name, 0) or skipped_reason_counts.get(name, 0) else "PASS",
            }
        )
    return {
        "rows": rows,
        "warning_count": int(sum(warning_counts.values()) + sum(skipped_reason_counts.values())),
        "notes": [
            "These checks flag candle-backtest risks that often fail in live/demo execution: spread, slippage, bid/ask path, liquidity, margin/leverage, MTF sync, and data quality.",
            "A PASS here does not replace MT5 real-tick validation; it only prevents obvious candle-model blind spots from being hidden.",
        ],
    }


def _mt5_model_comparison(request: dict[str, Any]) -> list[dict[str, Any]]:
    mt5_backtest = request.get("mt5_backtest") if isinstance(request.get("mt5_backtest"), dict) else {}
    supplied = mt5_backtest.get("model_comparison") or request.get("mt5_model_comparison")
    if isinstance(supplied, list) and supplied:
        rows = []
        for row in supplied:
            if not isinstance(row, dict):
                continue
            model = str(row.get("model") or row.get("test_model") or "")
            rows.append(
                {
                    "model": model,
                    "model_name": row.get("model_name") or dict(MT5_MODEL_ROWS).get(model, model),
                    "trade_count": row.get("trade_count", row.get("trades", 0)),
                    "win_rate": row.get("win_rate", 0),
                    "profit_factor": row.get("profit_factor", 0),
                    "expectancy_R": row.get("expectancy_R", row.get("expectancy", 0)),
                    "net_profit": row.get("net_profit", 0),
                    "status": row.get("status", "IMPORTED"),
                    "source": row.get("source", "MT5 Strategy Tester report"),
                }
            )
        return rows

    requested = mt5_backtest.get("test_model") or request.get("mt5_test_model")
    return [
        {
            "model": model,
            "model_name": label,
            "trade_count": 0,
            "win_rate": 0,
            "profit_factor": 0,
            "expectancy_R": 0,
            "net_profit": 0,
            "status": "CONFIG REQUESTED" if requested == model else "NOT RUN",
            "source": "Waiting for MT5 Strategy Tester report import.",
        }
        for model, label in MT5_MODEL_ROWS
    ]


def _equity_curves(trades: list[dict[str, Any]], initial_equity: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    equity = initial_equity
    cumulative_r = 0.0
    peak_r = 0.0
    peak_equity = initial_equity
    equity_curve = []
    drawdown_curve = []
    for trade in trades:
        equity += float(trade["profit"])
        cumulative_r += float(trade["result_R"])
        peak_r = max(peak_r, cumulative_r)
        peak_equity = max(peak_equity, equity)
        equity_curve.append({"time": trade["exit_time"], "equity": round(equity, 2), "cumulative_R": round(cumulative_r, 4)})
        drawdown_curve.append({"time": trade["exit_time"], "drawdown_R": round(cumulative_r - peak_r, 4), "drawdown_amount": round(equity - peak_equity, 2)})
    return equity_curve, drawdown_curve


def _approval_checklist(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checklists = []
    for row in rows:
        trade_count = int(row.get("trade_count", 0))
        expectancy = float(row.get("expectancy_R", 0) or 0)
        pf = float(row.get("profit_factor", 0) or 0)
        max_dd = float(row.get("max_drawdown_R", 0) or 0)
        checks = [
            {"label": "100+ trades for statistical usability", "passed": trade_count >= 100, "value": trade_count},
            {"label": "Positive expectancy", "passed": expectancy > 0, "value": expectancy},
            {"label": "Profit factor >= 1.20", "passed": pf >= 1.2, "value": pf},
            {"label": "Max drawdown not worse than -8R", "passed": max_dd >= -8, "value": max_dd},
        ]
        failed = [c["label"] for c in checks if not c["passed"]]
        checklists.append({
            "scope": row.get("strategy_id") or row.get("regime_id") or row.get("combination_key") or "summary",
            "name": row.get("strategy_name") or row.get("regime_name") or row.get("combination_key") or "Summary",
            "status": row.get("status", "WATCHLIST"),
            "checks": checks,
            "decision_reason": "Approved for research use." if not failed and row.get("status") == "APPROVED" else f"Not approved yet: {', '.join(failed) if failed else row.get('status')}",
        })
    return checklists


def _next_tests(summary: dict[str, Any], skipped: list[dict[str, Any]]) -> list[str]:
    suggestions = []
    if skipped:
        common = Counter(s["failed_condition"] for s in skipped if s.get("failed_condition")).most_common(1)
        if common:
            suggestions.append(f"Review the most common block reason: {common[0][0]} ({common[0][1]} setup candidates).")
    if summary.get("profit_factor", 0) < 1.2:
        suggestions.append("Compare kill-zone hard filter vs score-only mode to see whether London/NewYork/Overlap improves profit factor.")
    if summary.get("actual_vs_break_even", 0) < 0:
        suggestions.append("Actual win rate is below break-even; test stricter alpha minimum and compare RR 1:2 vs 1:3.")
    suggestions.append("Compare M15 against M5 and H1 for the same regime + strategy mapping before approving live research use.")
    suggestions.append("Run the same configuration on EURUSD, GBPUSD, USDJPY, and XAUUSD to find symbol-specific calibration differences.")
    return suggestions


def run_backtest(request: dict[str, Any], persist: bool = True) -> dict[str, Any]:
    global COST_R
    request = _apply_research_mode_preset(request)
    resolved_mode_preset = dict(request.get("_resolved_mode_preset") or resolve_research_mode_preset(request.get("research_mode_preset")))
    calibration = resolve_calibration(request)
    request = apply_calibration_to_request(request, calibration)
    run_id = str(uuid.uuid4())
    symbol = request["symbol"]
    timeframe = request["timeframe"]
    filters = request.get("filters") or {}
    costs = resolve_cost_model(request.get("costs") or {})
    rr = float(request.get("rr", 2.0))
    risk_percent = float(request.get("risk_percent", 1.0))
    initial_equity = float(request.get("initial_equity", 100000.0))
    sentiment = request.get("sentiment", "NEUTRAL")
    usd_bias = request.get("usd_bias", "NEUTRAL")
    risk_sentiment = request.get("risk_sentiment", "NEUTRAL")
    cb_divergence = request.get("cb_divergence", "NEUTRAL")
    macro_evidence = request.get("macro_evidence") if isinstance(request.get("macro_evidence"), dict) else {}
    regime_controls = request.get("regime_controls") if isinstance(request.get("regime_controls"), dict) else {}
    strategy_controls = request.get("strategy_controls") if isinstance(request.get("strategy_controls"), dict) else {}
    regime_filter = request.get("regime_filter", "ALL")
    strategy_filter = request.get("strategy_filter", "ALL")
    pattern_options = _pattern_options(request)
    statistical_regime = request.get("statistical_regime") if isinstance(request.get("statistical_regime"), dict) else {}
    use_killzone = bool(filters.get("use_killzone", request.get("use_killzone", True)))
    use_spread_filter = bool(filters.get("use_spread_filter", request.get("use_spread_filter", True)))
    use_sweeps = bool(request.get("use_sweeps", True))
    use_feature_cache = bool(request.get("use_feature_cache", request.get("feature_cache", True)))
    use_alpha = bool(filters.get("use_alpha", request.get("use_alpha", True)))
    COST_R = float(costs.get("cost_r_per_trade", COST_R))
    killzone_mode = filters.get("killzone_mode", request.get("killzone_mode", "score_only"))
    if killzone_mode == "score":
        killzone_mode = "score_only"
    spread_mode = filters.get("spread_filter_mode", request.get("spread_filter_mode", "score_only"))
    if spread_mode == "score":
        spread_mode = "score_only"
    options = {
        "killzone_mode": killzone_mode if use_killzone else "off",
        "spread_filter_mode": spread_mode if use_spread_filter else "off",
        "alpha_mode": filters.get("alpha_mode", request.get("alpha_mode", "hard_minimum")),
        "strict_clean_trend": bool(request.get("strict_clean_trend", True)),
        "use_alpha": use_alpha,
        "allowed_sessions": filters.get("allowed_sessions", ["London", "NewYork", "Overlap"]),
        "max_spread_percentile": float(filters.get("max_spread_percentile", 70)),
        "min_alpha_score": float(filters.get("min_alpha_score", 5)),
        "strict_regime_validation": bool(filters.get("strict_regime_validation", False)),
        "reject_trend_weakening": bool(filters.get("reject_trend_weakening", False)),
        "reject_low_er_clean_trend": bool(filters.get("reject_low_er_clean_trend", False)),
        "reject_adx_outside_clean_trend": bool(filters.get("reject_adx_outside_clean_trend", False)),
        "reject_mtf_conflict_score": bool(filters.get("reject_mtf_conflict_score", False)),
        "strict_regime_max_failed_conditions": int(filters.get("strict_regime_max_failed_conditions", 0)),
        "strict_regime_min_confidence": float(filters.get("strict_regime_min_confidence", 0.75)),
        "min_clean_trend_er": float(filters.get("min_clean_trend_er", 0.25)),
        "clean_trend_adx_min": float(filters.get("clean_trend_adx_min", 18)),
        "clean_trend_adx_max": float(filters.get("clean_trend_adx_max", 35)),
        "max_mtf_conflict_score": float(filters.get("max_mtf_conflict_score", 0)),
        "reject_m08_conflict": bool(filters.get("reject_m08_conflict", True)),
        "reject_m11_exhaustion": bool(filters.get("reject_m11_exhaustion", True)),
        "reject_rollover": bool(filters.get("reject_rollover", True)),
        "reject_news": bool(filters.get("reject_news", True)),
        "allow_news_regime_only": bool(filters.get("allow_news_regime_only", False)),
        "use_statistical_regime": bool(statistical_regime.get("use_statistical_regime", True)),
        "statistical_regime_mode": str(statistical_regime.get("mode", statistical_regime.get("statistical_regime_mode", "diagnostic"))),
        "stat_min_confidence": float(statistical_regime.get("stat_min_confidence", 0.55)),
        "stat_block_structural_break": bool(statistical_regime.get("stat_block_structural_break", True)),
        "stat_max_structural_break_score": float(statistical_regime.get("stat_max_structural_break_score", 2.5)),
    }

    candles, df = _prepare_features(
        symbol,
        timeframe,
        request["start_date"],
        request["end_date"],
        sentiment,
        usd_bias,
        risk_sentiment,
        cb_divergence,
        macro_evidence,
        use_killzone,
        use_spread_filter,
        use_sweeps,
        regime_controls,
        calibration,
        request.get("data_source_controls", {}),
        use_feature_cache,
    )
    trades: list[dict[str, Any]] = []
    skipped_setups: list[dict[str, Any]] = []
    equity = initial_equity
    tradable_rows = 0
    i = 0
    while i < len(df) - 1:
        row = df.iloc[i]
        if row.get("regime_id") == "NONE":
            i += 1
            continue
        if regime_filter != "ALL" and row.get("regime_id") != regime_filter:
            i += 1
            continue

        regime_result = {
            "is_active": True,
            "allowed_strategies": STRATEGIES.keys() if row.get("regime_id") else [],
        }
        allowed = {
            "R01": ["T1", "T2", "T3"],
            "R02": ["T4", "T5", "T6"],
            "R03": ["R1", "R2", "S1", "S2"],
            "R04": ["B1", "B2", "B3"],
            "R05": ["B4", "B5", "B6"],
            "R06": ["C1", "C2", "C3", "C4", "D1"],
            "R07": ["D1", "E1", "E2"],
            "R08": ["D1", "E3", "E4"],
            "R09": ["D0", "N1", "N2"],
            "R10": ["D0"],
            "R11": ["L1", "L2", "L3"],
            "R12": ["L4", "L5", "L6"],
            "R13": ["CH1", "CH2", "CH3"],
            "R14": ["CH4", "CH5", "CH6"],
            "R15": ["RH1", "RH2", "RH3"],
            "R16": ["RL1", "RL2", "RL3"],
            "R17": ["FB1", "FB2", "FB3"],
            "R18": ["FB4", "FB5", "FB6"],
            "R19": ["LO1", "LO2", "LO3", "LO4", "LO5"],
            "R20": ["NY1", "NY2", "NY3", "NY4", "NY5"],
            "R21": ["OV1", "OV2", "OV3", "OV4"],
            "R22": ["AR1", "AR2", "AR3", "AR4", "AR5"],
            "R23": ["D0", "NC1"],
            "R24": ["D0", "DL1"],
            "R25": ["USD1", "USD2", "USD3"],
            "R26": ["USD4", "USD5", "USD6"],
            "R27": ["RO1", "RO2", "RO3"],
            "R28": ["RF1", "RF2", "RF3"],
            "R29": ["CB1", "CB2", "CB3"],
            "R30": ["D0", "MF1", "MF2"],
            "R31": ["D1", "TR1", "TR2"],
            "R32": ["D1", "TW1", "TW2"],
            "R33": ["D1", "TW3", "TW4"],
            "R34": ["LS1", "LS2", "LS3"],
            "R35": ["LS4", "LS5", "LS6"],
            "R36": ["VW1", "VW2", "VW3"],
            "R37": ["D1", "MT1", "MT2"],
            "R38": ["PS1", "PS2", "D1"],
            "R39": ["D1", "G1", "G2"],
            "R40": ["D0", "DQ1"],
            "R41": ["AS1", "AS2", "AS3"],
            "R42": ["OF1", "OF2"],
            "R43": ["PD1", "PD2"],
            "R44": ["TD1", "TD2", "TD3"],
            "R45": ["CX1", "CX2"],
            "R46": ["VT1", "VT2"],
            "R47": ["SQ1", "SQ2"],
            "R48": ["MM1", "MM2"],
            "R49": ["XS1", "XS2"],
            "R50": ["D1", "EC1"],
        }.get(row.get("regime_id"), [])
        if not use_sweeps:
            allowed = [s for s in allowed if s not in {"S1", "S2"}]
        if strategy_filter != "ALL":
            allowed = [s for s in allowed if s == strategy_filter]

        entered = False
        for strategy_id in allowed:
            signal = evaluate_strategy(df, i, strategy_id, rr)
            if not signal.get("triggered"):
                continue
            signal["symbol"] = symbol
            signal, stop_realism = _apply_stop_realism_controls(symbol, row, signal, rr, strategy_controls)
            modifiers = detect_modifiers(row.to_dict(), signal["direction"])
            alpha = calculate_alpha(row, signal, modifiers)
            pattern_result = detect_patterns(df, i, signal, pattern_options)
            block_reasons = _strict_block_reasons(row, modifiers, alpha, options) + _pattern_block_reasons(pattern_result, pattern_options)
            if stop_realism.get("stop_blocked"):
                block_reasons.extend(stop_realism.get("reasons") or ["Stop realism controls blocked this candidate."])
            if bool(costs.get("rollover_block", True)) and row.get("session") == "Rollover":
                block_reasons.append("Rollover blocked by transaction-cost model.")
            if block_reasons:
                skipped_setups.append(_skipped_payload(row, signal, modifiers, alpha, block_reasons, pattern_result))
                continue

            tradable_rows += 1
            exit_idx, exit_price, exit_reason = _simulate_exit(df, i, signal)
            mae_mfe = _mae_mfe_for_trade(df, i, exit_idx, signal)
            risk_amount = equity * risk_percent / 100
            risk_distance = signal["risk_distance"]
            if risk_distance <= 0:
                skipped_setups.append(_skipped_payload(row, signal, modifiers, alpha, ["Invalid risk distance."], pattern_result))
                continue
            position_size = risk_amount / risk_distance
            if signal["direction"] == "long":
                profit = (exit_price - signal["entry"]) * position_size
            else:
                profit = (signal["entry"] - exit_price) * position_size
            initial_risk = risk_distance * position_size
            gross_profit = profit
            gross_result_r = profit / initial_risk if initial_risk else 0.0
            cost_breakdown = calculate_trade_cost(
                symbol=symbol,
                row=row,
                signal=signal,
                costs=costs,
                initial_risk=initial_risk,
            )
            execution_failure_checks = _execution_failure_checks(row, signal, cost_breakdown, position_size, equity, strategy_controls)
            trade_cost_r = float(cost_breakdown.get("total_cost_R") or 0.0)
            result_r = gross_result_r - trade_cost_r
            profit -= trade_cost_r * initial_risk
            equity += profit

            trade = {
                "symbol": symbol,
                "timeframe": timeframe,
                "entry_time": row["timestamp"].isoformat(),
                "exit_time": df.iloc[exit_idx]["timestamp"].isoformat(),
                "regime_id": row["regime_id"],
                "regime_name": row["regime_name"],
                "modifiers": modifiers["modifiers"],
                "strategy_id": strategy_id,
                "strategy_name": STRATEGIES[strategy_id]["strategy_name"],
                "direction": signal["direction"],
                "entry": round(signal["entry"], 6),
                "sl": round(signal["sl"], 6),
                "tp": round(signal["tp"], 6),
                "exit_price": round(float(exit_price), 6),
                "initial_risk": round(initial_risk, 4),
                "mae_price": mae_mfe["mae_price"],
                "mfe_price": mae_mfe["mfe_price"],
                "mae_R": mae_mfe["mae_R"],
                "mfe_R": mae_mfe["mfe_R"],
                "mae_percent_of_stop": mae_mfe["mae_percent_of_stop"],
                "mfe_to_mae_ratio": mae_mfe["mfe_to_mae_ratio"],
                "max_adverse_price": mae_mfe["max_adverse_price"],
                "max_favorable_price": mae_mfe["max_favorable_price"],
                "bars_held": mae_mfe["bars_held"],
                "stop_distance": mae_mfe["stop_distance"],
                "stop_realism": signal.get("stop_realism", {}),
                "gross_result_R": round(gross_result_r, 4),
                "gross_profit": round(gross_profit, 2),
                "spread_at_entry": round(float(row.get("spread") or 0), 4),
                "spread_percentile": round(float(row.get("spread_percentile") or 0), 2),
                "estimated_slippage_R": round(float(cost_breakdown.get("slippage_R") or 0), 6),
                "estimated_slippage_points": round(float(cost_breakdown.get("slippage_points") or 0), 4),
                "total_cost_R": round(trade_cost_r, 6),
                "cost_model": cost_breakdown.get("cost_model", costs.get("cost_mode", "fixed_r")),
                "cost_breakdown": cost_breakdown,
                "execution_failure_checks": execution_failure_checks,
                "result_R": round(result_r, 4),
                "profit": round(profit, 2),
                "alpha_score": alpha["alpha_score"],
                "alpha_components": alpha.get("components", {}),
                "alpha_reason": alpha.get("reason", ""),
                "patterns_detected": pattern_result.get("patterns_detected", []),
                "pattern_score": pattern_result.get("pattern_score", 0.0),
                "pattern_decision": pattern_result.get("pattern_decision", "OFF"),
                "pattern_summary": pattern_result.get("pattern_summary", ""),
                "final_score": round(float(alpha.get("alpha_score") or 0) + float(pattern_result.get("pattern_score") or 0), 2),
                "entry_reason": signal["reason"],
                "exit_reason": exit_reason,
                "session": row["session"],
                "setup_context": _setup_context(row),
            }
            trades.append(trade)
            i = exit_idx + 1
            entered = True
            break
        if not entered:
            i += 1

    results = [float(t["result_R"]) for t in trades]
    profits = [float(t["profit"]) for t in trades]
    summary_perf = _performance_from_trades({}, trades, rr)
    by_regime: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_strategy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_combo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        by_regime[trade["regime_id"]].append(trade)
        by_strategy[trade["strategy_id"]].append(trade)
        modifiers = trade["modifiers"] or ["NONE"]
        for modifier in modifiers:
            key = f"{trade['regime_id']}_{trade['strategy_id']}_{trade['session']}_{modifier}"
            by_combo[key].append(trade)

    regime_performance = [
        _performance_from_trades(
            {"regime_id": key, "regime_name": group[0]["regime_name"]},
            group,
            rr,
        )
        for key, group in by_regime.items()
    ]
    strategy_performance = [
        _performance_from_trades(
            {"strategy_id": key, "strategy_name": group[0]["strategy_name"]},
            group,
            rr,
        )
        for key, group in by_strategy.items()
    ]
    combination_performance = [
        _performance_from_trades({"combination_key": key, "modifier_sample_note": "Modifier rows overlap; one trade can appear under multiple modifiers."}, group, rr)
        for key, group in by_combo.items()
    ]

    unique_combination_performance = _group_performance(
        trades,
        lambda t: f"{t['regime_id']}_{t['strategy_id']}_{t['session']}_{','.join(sorted(t.get('modifiers') or ['NONE']))}",
        lambda key, group: {"combination_key": key, "modifiers_are_unique_set": True},
        rr,
    )
    modifier_impact = combination_performance
    session_performance = _group_performance(
        trades,
        lambda t: t.get("session") or "Unknown",
        lambda key, group: {"session": key},
        rr,
    )
    monthly_performance = _group_performance(
        trades,
        lambda t: str(pd.Timestamp(t["entry_time"]).strftime("%Y-%m")),
        lambda key, group: {"month": key},
        rr,
    )
    pattern_performance = _pattern_performance(trades, rr)
    mae_mfe_analysis = _mae_mfe_analysis(trades)
    pattern_summary = {
        "enabled": bool(pattern_options.get("use_patterns", True)),
        "score_mode": pattern_options.get("pattern_score_mode", "score_only"),
        "min_pattern_score": pattern_options.get("min_pattern_score", 2),
        "active_switches": {
            key: pattern_options.get(key)
            for key in [
                "use_ict",
                "use_fvg",
                "use_order_blocks",
                "use_bos",
                "use_mss",
                "use_liquidity_pools",
                "use_round_numbers",
                "use_vwap",
                "use_mvwap",
                "use_session_vwap",
            ]
        },
        "pattern_rows": len(pattern_performance),
        "note": "Patterns are measurable OHLC/tick-volume confirmations. Real ticks validate execution quality, not the candle pattern itself.",
    }
    mt5_model_comparison = _mt5_model_comparison(request)
    institutional_data_quality = evaluate_institutional_data_quality(
        candles=candles,
        features=df,
        trades=trades,
        request=request,
        mt5_model_comparison=mt5_model_comparison,
    )

    best_regime = max(regime_performance, key=lambda x: x["expectancy_R"], default={}).get("regime_name")
    worst_regime = min(regime_performance, key=lambda x: x["expectancy_R"], default={}).get("regime_name")
    best_strategy = max(strategy_performance, key=lambda x: x["expectancy_R"], default={}).get("strategy_name")
    worst_strategy = min(strategy_performance, key=lambda x: x["expectancy_R"], default={}).get("strategy_name")
    best_session = max(session_performance, key=lambda x: x["expectancy_R"], default={}).get("session")
    worst_session = min(session_performance, key=lambda x: x["expectancy_R"], default={}).get("session")
    equity_curve, drawdown_curve = _equity_curves(trades, initial_equity)
    ending_equity = equity_curve[-1]["equity"] if equity_curve else initial_equity
    summary = {
        "total_trades": len(trades),
        "win_rate": summary_perf["win_rate"],
        "loss_rate": summary_perf["loss_rate"],
        "profit_factor": summary_perf["profit_factor"],
        "expectancy_R": summary_perf["expectancy_R"],
        "average_R": summary_perf["average_R"],
        "average_win_R": summary_perf["avg_win_R"],
        "average_loss_R": summary_perf["avg_loss_R"],
        "break_even_win_rate": summary_perf["break_even_win_rate"],
        "actual_vs_break_even": summary_perf["actual_vs_break_even"],
        "payoff_ratio": summary_perf["payoff_ratio"],
        "recovery_factor": summary_perf["recovery_factor"],
        "sharpe_like_R": summary_perf["sharpe_like_R"],
        "average_pattern_score": round(float(np.mean([float(t.get("pattern_score") or 0) for t in trades])), 4) if trades else 0.0,
        "average_final_score": round(float(np.mean([float(t.get("final_score") or 0) for t in trades])), 4) if trades else 0.0,
        "average_cost_R": summary_perf["average_cost_R"],
        "total_cost_R": summary_perf["total_cost_R"],
        "max_drawdown_R": summary_perf["max_drawdown_R"],
        "max_losing_streak": summary_perf["max_losing_streak"],
        "net_profit": round(sum(profits), 2),
        "gross_profit": round(sum(p for p in profits if p > 0), 2),
        "gross_loss": round(sum(p for p in profits if p < 0), 2),
        "initial_equity": round(initial_equity, 2),
        "ending_equity": round(ending_equity, 2),
        "roi_percent": round(((ending_equity - initial_equity) / initial_equity) * 100, 4),
        "best_regime": best_regime,
        "worst_regime": worst_regime,
        "best_strategy": best_strategy,
        "worst_strategy": worst_strategy,
        "best_session": best_session,
        "worst_session": worst_session,
        "skipped_setups": len(skipped_setups),
        "data_grade": institutional_data_quality.get("data_grade"),
        "data_score": institutional_data_quality.get("data_score"),
        "data_validation_status": institutional_data_quality.get("validation_status"),
        "mae_mfe_decision": mae_mfe_analysis.get("summary", {}).get("decision"),
        "avg_mae_R": mae_mfe_analysis.get("summary", {}).get("avg_mae_R", 0),
        "avg_mfe_R": mae_mfe_analysis.get("summary", {}).get("avg_mfe_R", 0),
        "winner_p75_mae_R": mae_mfe_analysis.get("summary", {}).get("winner_p75_mae_R", 0),
        "loser_p75_mfe_R": mae_mfe_analysis.get("summary", {}).get("loser_p75_mfe_R", 0),
        "strict_thresholds": {
            "mode_preset": request.get("research_mode_preset"),
            "strict_regime_validation": options["strict_regime_validation"],
            "strict_regime_max_failed_conditions": options["strict_regime_max_failed_conditions"],
            "strict_regime_min_confidence": options["strict_regime_min_confidence"],
            "min_clean_trend_er": options["min_clean_trend_er"],
            "clean_trend_adx_min": options["clean_trend_adx_min"],
            "clean_trend_adx_max": options["clean_trend_adx_max"],
            "min_alpha_score": options["min_alpha_score"],
            "max_spread_percentile": options["max_spread_percentile"],
        },
    }
    cost_summary = {
        "cost_mode": costs.get("cost_mode", "fixed_r"),
        "total_cost_R": summary["total_cost_R"],
        "average_cost_R": summary["average_cost_R"],
        "total_cost_currency": round(sum(float(t.get("total_cost_R") or 0) * float(t.get("initial_risk") or 0) for t in trades), 2),
        "spread_cost_R": round(sum(float((t.get("cost_breakdown") or {}).get("spread_cost_R") or 0) for t in trades), 4),
        "commission_R": round(sum(float((t.get("cost_breakdown") or {}).get("commission_R") or 0) for t in trades), 4),
        "slippage_R": round(sum(float((t.get("cost_breakdown") or {}).get("slippage_R") or 0) for t in trades), 4),
        "session_multipliers": costs.get("session_cost_multiplier") or costs.get("session_multipliers") or "defaults",
        "news_cost_multiplier": costs.get("news_cost_multiplier", 2.0),
        "rollover_block": bool(costs.get("rollover_block", True)),
        "note": "Trade result_R and profit are net of transaction costs; gross_result_R/gross_profit preserve pre-cost values.",
    }
    data_health = _data_health(candles, df, {**request, "symbol": symbol, "timeframe": timeframe}, tradable_rows)
    feature_summary = _feature_summary(df)
    spread_slippage_diagnostics = _spread_slippage_diagnostics(symbol, df, trades, skipped_setups)
    execution_failure_summary = _execution_failure_summary(trades, skipped_setups)
    calibration_info = calibration_summary(calibration, regime_filter)
    macro_context = {
        "source": df.get("macro_source", pd.Series(["manual"])).iloc[-1] if len(df) else "manual",
        "usd_bias": df.get("usd_bias", pd.Series([usd_bias])).iloc[-1] if len(df) else usd_bias,
        "risk_sentiment": df.get("risk_sentiment", pd.Series([risk_sentiment])).iloc[-1] if len(df) else risk_sentiment,
        "cb_divergence": df.get("cb_divergence", pd.Series([cb_divergence])).iloc[-1] if len(df) else cb_divergence,
        "usd_confidence": df.get("macro_usd_confidence", pd.Series([0])).iloc[-1] if len(df) else 0,
        "risk_confidence": df.get("macro_risk_confidence", pd.Series([0])).iloc[-1] if len(df) else 0,
        "cb_confidence": df.get("macro_cb_confidence", pd.Series([0])).iloc[-1] if len(df) else 0,
        "reasons": df.get("macro_reasons", pd.Series([""])).iloc[-1] if len(df) else "",
        "activation_threshold": 0.50,
        "activation_allowed": {
            "R25": (df.get("usd_bias", pd.Series(["NEUTRAL"])).iloc[-1] == "USD_BULLISH" and float(df.get("macro_usd_confidence", pd.Series([0])).iloc[-1] or 0) >= 0.50 and str(df.get("macro_source", pd.Series(["manual"])).iloc[-1]).lower() in {"evidence", "macro_data"}) if len(df) else False,
            "R26": (df.get("usd_bias", pd.Series(["NEUTRAL"])).iloc[-1] == "USD_BEARISH" and float(df.get("macro_usd_confidence", pd.Series([0])).iloc[-1] or 0) >= 0.50 and str(df.get("macro_source", pd.Series(["manual"])).iloc[-1]).lower() in {"evidence", "macro_data"}) if len(df) else False,
            "R27": (df.get("risk_sentiment", pd.Series(["NEUTRAL"])).iloc[-1] == "RISK_ON" and float(df.get("macro_risk_confidence", pd.Series([0])).iloc[-1] or 0) >= 0.50 and str(df.get("macro_source", pd.Series(["manual"])).iloc[-1]).lower() in {"evidence", "macro_data"}) if len(df) else False,
            "R28": (df.get("risk_sentiment", pd.Series(["NEUTRAL"])).iloc[-1] == "RISK_OFF" and float(df.get("macro_risk_confidence", pd.Series([0])).iloc[-1] or 0) >= 0.50 and str(df.get("macro_source", pd.Series(["manual"])).iloc[-1]).lower() in {"evidence", "macro_data"}) if len(df) else False,
            "R29": (df.get("cb_divergence", pd.Series(["NEUTRAL"])).iloc[-1] != "NEUTRAL" and float(df.get("macro_cb_confidence", pd.Series([0])).iloc[-1] or 0) >= 0.50 and str(df.get("macro_source", pd.Series(["manual"])).iloc[-1]).lower() in {"evidence", "macro_data"}) if len(df) else False,
        },
    }
    regime_confidence = _regime_confidence_summary(df)
    approval_checklist = _approval_checklist(regime_performance + strategy_performance)
    explanation = explain_backtest_summary(summary, regime_performance, strategy_performance)
    explanation.setdefault("what_to_test_next", _next_tests(summary, skipped_setups))
    explanation.setdefault("warnings", [])
    if skipped_setups:
        explanation["warnings"].append(f"{len(skipped_setups)} triggered setup candidates were blocked by research filters or strict R01/R02 rules.")
    result = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode_preset": {
            **resolved_mode_preset,
            "applied": {
                "filters": {
                    "killzone_mode": options["killzone_mode"],
                    "spread_filter_mode": options["spread_filter_mode"],
                    "alpha_mode": options["alpha_mode"],
                    "min_alpha_score": options["min_alpha_score"],
                    "max_spread_percentile": options["max_spread_percentile"],
                    "strict_regime_validation": options["strict_regime_validation"],
                    "strict_regime_max_failed_conditions": options["strict_regime_max_failed_conditions"],
                    "strict_regime_min_confidence": options["strict_regime_min_confidence"],
                    "reject_trend_weakening": options["reject_trend_weakening"],
                    "reject_low_er_clean_trend": options["reject_low_er_clean_trend"],
                    "reject_adx_outside_clean_trend": options["reject_adx_outside_clean_trend"],
                    "reject_mtf_conflict_score": options["reject_mtf_conflict_score"],
                    "min_clean_trend_er": options["min_clean_trend_er"],
                    "clean_trend_adx_min": options["clean_trend_adx_min"],
                    "clean_trend_adx_max": options["clean_trend_adx_max"],
                    "statistical_regime_mode": options["statistical_regime_mode"],
                    "stat_min_confidence": options["stat_min_confidence"],
                    "stat_block_structural_break": options["stat_block_structural_break"],
                    "stat_max_structural_break_score": options["stat_max_structural_break_score"],
                },
                "pattern_engine": pattern_options,
                "statistical_regime": request.get("statistical_regime", {}),
                "mt5_backtest": request.get("mt5_backtest", {}),
                "calibration": request.get("calibration", {}),
            },
        },
        "request": {
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": request["start_date"],
            "end_date": request["end_date"],
            "research_mode_preset": request.get("research_mode_preset"),
            "regime_filter": regime_filter,
            "strategy_filter": strategy_filter,
            "risk_percent": risk_percent,
            "rr": rr,
            "initial_equity": initial_equity,
            "use_killzone": use_killzone,
            "use_spread_filter": use_spread_filter,
            "use_sweeps": use_sweeps,
            "use_alpha": use_alpha,
            "usd_bias": usd_bias,
            "risk_sentiment": risk_sentiment,
            "cb_divergence": cb_divergence,
            "resolved_macro_context": macro_context,
            "macro_evidence": macro_evidence,
            "killzone_mode": options["killzone_mode"],
            "spread_filter_mode": options["spread_filter_mode"],
            "alpha_mode": options["alpha_mode"],
            "strict_clean_trend": options["strict_clean_trend"],
            "filters": filters,
            "pattern_engine": pattern_options,
            "statistical_regime": request.get("statistical_regime", {}),
            "mt5_backtest": request.get("mt5_backtest", {}),
            "data_source_controls": request.get("data_source_controls", {}),
            "costs": costs,
            "calibration": request.get("calibration", {}),
            "execution_assumption": request.get("execution_assumption", {"entry_price": "signal_close", "same_candle_sl_tp": "sl_first", "one_trade_at_a_time": True}),
            "regime_controls": request.get("regime_controls", {}),
            "strategy_controls": request.get("strategy_controls", {}),
            "risk_controls": request.get("risk_controls", {}),
        },
        "summary": summary,
        "cost_summary": cost_summary,
        "calibration_summary": calibration_info,
        "data_health": data_health,
        "feature_summary": feature_summary,
        "spread_slippage_diagnostics": spread_slippage_diagnostics,
        "execution_failure_summary": execution_failure_summary,
        "institutional_data_quality": institutional_data_quality,
        "macro_context": macro_context,
        "regime_confidence": regime_confidence,
        "regime_performance": regime_performance,
        "strategy_performance": strategy_performance,
        "combination_performance": combination_performance,
        "unique_combination_performance": unique_combination_performance,
        "modifier_impact": modifier_impact,
        "session_performance": session_performance,
        "monthly_performance": monthly_performance,
        "pattern_performance": pattern_performance,
        "pattern_summary": pattern_summary,
        "mae_mfe_analysis": mae_mfe_analysis,
        "mt5_model_comparison": mt5_model_comparison,
        "skipped_setups": skipped_setups,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "approval_checklist": approval_checklist,
        "trades": trades,
        "explanation": explanation,
    }
    if persist:
        save_backtest_result(result)
    return result
