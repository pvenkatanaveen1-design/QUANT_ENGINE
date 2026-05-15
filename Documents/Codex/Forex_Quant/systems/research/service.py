from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from core.config_manager import ConfigManager
from core.time_utils import classify_session
from systems.data import backend as data_backend
from systems.data.service import load_cleaned_rows
from systems.regime import research as regime_research
from systems.regime import service as regime_service
from systems.strategy_router import backend as strategy_backend


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXECUTABLE_FAMILIES = {"trend_momentum", "breakout", "mean_reversion", "sweep_reversal", "defensive"}


def _risk_rules() -> dict[str, Any]:
    return ConfigManager(PROJECT_ROOT).load_yaml("config/risk_rules.yaml")


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    multiplier = 2 / (period + 1)
    seed_size = min(period, len(values))
    ema = mean(values[:seed_size])
    for value in values[seed_size:]:
        ema = (value - ema) * multiplier + ema
    return ema


def _atr(rows: list[dict[str, Any]], period: int = 14) -> float:
    if len(rows) < 2:
        return 0.0
    ranges = []
    for index, row in enumerate(rows[-period:]):
        high = float(row["high"])
        low = float(row["low"])
        if index == 0:
            ranges.append(high - low)
        else:
            prev_close = float(rows[-period + index - 1]["close"])
            ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return mean(ranges) if ranges else 0.0


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) <= period:
        return 50.0
    gains = []
    losses = []
    for index in range(len(closes) - period, len(closes)):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))
    avg_gain = mean(gains) if gains else 0.0
    avg_loss = mean(losses) if losses else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _find_strategy(strategy_id: str) -> dict[str, Any] | None:
    return next((item for item in strategy_backend.get_registry() if item["id"] == strategy_id), None)


def _family(strategy: dict[str, Any]) -> str:
    name = strategy.get("name", "").lower()
    family = str(strategy.get("family", "general"))
    if "sweep" in name or family in {"liquidity", "sweep_reversal"}:
        return "sweep_reversal"
    if "bollinger" in name or "rsi" in name or "fade" in name:
        return "mean_reversion"
    if "break" in name or "donchian" in name or "channel" in name or "atr" in name:
        return "breakout"
    if "no-trade" in name or "defensive" in name or "circuit" in name:
        return "defensive"
    return family


def _setup_direction(rows: list[dict[str, Any]], family: str, breakout_enabled: bool, sweep_enabled: bool, alpha_enabled: bool) -> tuple[str | None, str]:
    if len(rows) < 35:
        return None, "data quality issue"
    current = rows[-1]
    closes = [float(row["close"]) for row in rows]
    close = float(current["close"])
    ema20 = _ema(closes[-35:], 20)
    atr = _atr(rows)
    if atr <= 0:
        return None, "stop too tight"

    if family == "defensive":
        return None, "no-trade defensive"
    if family == "trend_momentum":
        if close > ema20 and close > closes[-2]:
            return "long", "trend alpha"
        if close < ema20 and close < closes[-2]:
            return "short", "trend alpha"
        return None, "no setup"
    if family == "breakout":
        if not breakout_enabled:
            return None, "breakout disabled"
        prior = rows[-21:-1]
        prior_high = max(float(row["high"]) for row in prior)
        prior_low = min(float(row["low"]) for row in prior)
        if close > prior_high:
            return "long", "breakout alpha"
        if close < prior_low:
            return "short", "breakout alpha"
        return None, "no setup"
    if family == "mean_reversion":
        rsi = _rsi(closes)
        sma = mean(closes[-20:])
        sigma = math.sqrt(mean([(value - sma) ** 2 for value in closes[-20:]]))
        if close <= sma - 1.6 * sigma or rsi < 32:
            return "long", "range alpha"
        if close >= sma + 1.6 * sigma or rsi > 68:
            return "short", "range alpha"
        return None, "no setup"
    if family == "sweep_reversal":
        if not sweep_enabled:
            return None, "sweep failed"
        prior = rows[-21:-1]
        prior_high = max(float(row["high"]) for row in prior)
        prior_low = min(float(row["low"]) for row in prior)
        if float(current["high"]) > prior_high and close < prior_high:
            return "short", "liquidity sweep"
        if float(current["low"]) < prior_low and close > prior_low:
            return "long", "liquidity sweep"
        return None, "sweep failed"
    if alpha_enabled:
        return None, "logic not implemented"
    return None, "logic not implemented"


def _hit_outcome(entry: float, stop: float, target: float, side: str, future_rows: list[dict[str, Any]], target_r: float) -> float:
    for row in future_rows:
        high = float(row["high"])
        low = float(row["low"])
        if side == "long":
            if low <= stop:
                return -1.0
            if high >= target:
                return target_r
        else:
            if high >= stop:
                return -1.0
            if low <= target:
                return target_r
    close = float(future_rows[-1]["close"]) if future_rows else entry
    risk = abs(entry - stop) or 1e-12
    if side == "long":
        return max(-1.0, min(target_r, (close - entry) / risk))
    return max(-1.0, min(target_r, (entry - close) / risk))


def run_scenario(
    symbol: str,
    timeframe: str,
    selected_regime: str,
    selected_strategy: str,
    investment_amount: float = 10000.0,
    bars: int = 672,
    source: str = "mt5_demo",
    regime_scope: str | None = None,
    killzone_enabled: bool = True,
    breakout_enabled: bool = True,
    sweep_enabled: bool = True,
    alpha_enabled: bool = True,
    spread_filter_enabled: bool = True,
) -> dict[str, Any]:
    if source != "mt5_demo":
        return {"blocked": True, "reason": "Only MT5 data is supported in the runtime app. Offline fallback is disabled.", "label": "scenario estimate"}
    strategy = _find_strategy(selected_strategy)
    if not strategy:
        return {"blocked": True, "reason": f"Unknown strategy {selected_strategy}", "label": "scenario estimate"}
    strategy = regime_research.enrich_strategy(strategy, selected_regime)
    regime_model = regime_research.regime_model(selected_regime)
    strategy_research = strategy.get("research_spec") or {}
    family = _family(strategy)
    if family not in EXECUTABLE_FAMILIES or not bool(strategy_research.get("scenario_executable", False)):
        return {
            "blocked": True,
            "reason": "logic not implemented",
            "strategy": strategy,
            "research_model": regime_model,
            "strategy_research": strategy_research,
            "label": "scenario estimate",
        }
    if family == "defensive" or float(regime_model.get("risk_multiplier") or 0.0) <= 0.0:
        return {
            "blocked": True,
            "reason": "risk model blocks new trades for this defensive or no-trade regime",
            "strategy": strategy,
            "research_model": regime_model,
            "strategy_research": strategy_research,
            "label": "scenario estimate",
        }

    data_result = data_backend.fetch_mt5_bars(symbol.upper(), timeframe.upper(), bars=bars)
    symbol = data_result.symbol
    timeframe = data_result.timeframe
    rows = load_cleaned_rows(symbol.upper(), timeframe.upper())[-bars:]
    if len(rows) < 60:
        return {"blocked": True, "reason": "data quality issue: not enough bars", "strategy": strategy, "label": "scenario estimate"}

    rules = _risk_rules()
    risk_multiplier = float(regime_model.get("risk_multiplier") or 0.0)
    risk_amount = float(investment_amount) * float(rules.get("base_risk_per_trade_percent", 0.25)) / 100.0 * risk_multiplier
    target_r = max(1.0, min(4.0, float(strategy_research.get("expected_rrr") or regime_model.get("expected_rrr") or 1.5)))
    sessions_config = ConfigManager(PROJECT_ROOT).load_yaml("config/sessions.yaml")
    fail_reasons: Counter[str] = Counter()
    institutional_flags: Counter[str] = Counter()
    failure_events: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    consecutive_losses = 0
    max_consecutive_losses = 0

    for index in range(40, len(rows) - 6):
        window = rows[: index + 1]
        detected = regime_service.detect_regime_for_rows(window, symbol=symbol, timeframe=timeframe)
        microstructure = detected.features.extra or {}
        if float(microstructure.get("institutional_trap_score") or 0.0) >= 60.0:
            institutional_flags["high_trap_score"] += 1
        if microstructure.get("volume_spike"):
            institutional_flags["volume_spike"] += 1
        if microstructure.get("near_round_number"):
            institutional_flags["round_number_zone"] += 1
        for zone in microstructure.get("retail_stop_zones", []):
            institutional_flags[f"retail_stop_{zone}"] += 1
        news_proxy = microstructure.get("news_proxy") or {}
        if float(news_proxy.get("jump_z") or 0.0) >= 2.0 or float(news_proxy.get("spread_percentile") or 0.0) >= 90.0 or float(news_proxy.get("tick_volume_ratio") or 0.0) >= 2.0:
            institutional_flags["news_proxy_shock"] += 1
        if regime_scope != "all_observed" and detected.regime_id != selected_regime:
            fail_reasons["wrong regime"] += 1
            if len(failure_events) < 200:
                failure_events.append({"time": rows[index]["time"].isoformat(), "reason": "wrong regime", "regime_id": detected.regime_id, "trap_score": microstructure.get("institutional_trap_score")})
            continue
        row = rows[index]
        if killzone_enabled and classify_session(row["time"], sessions_config).get("session") not in {"London_Open", "London_NY_Overlap"}:
            fail_reasons["killzone blocked"] += 1
            if len(failure_events) < 200:
                failure_events.append({"time": row["time"].isoformat(), "reason": "killzone blocked", "regime_id": detected.regime_id, "trap_score": microstructure.get("institutional_trap_score")})
            continue
        if spread_filter_enabled and detected.features.spread_percentile > float(rules.get("max_allowed_spread_percentile", 80)):
            fail_reasons["spread too high"] += 1
            if len(failure_events) < 200:
                failure_events.append({"time": row["time"].isoformat(), "reason": "spread too high", "regime_id": detected.regime_id, "trap_score": microstructure.get("institutional_trap_score")})
            continue
        side, reason = _setup_direction(window, family, breakout_enabled, sweep_enabled, alpha_enabled)
        if not side:
            fail_reasons[reason] += 1
            if len(failure_events) < 200:
                failure_events.append({"time": row["time"].isoformat(), "reason": reason, "regime_id": detected.regime_id, "trap_score": microstructure.get("institutional_trap_score")})
            continue
        atr = _atr(window)
        entry = float(row["close"])
        if side == "long":
            stop = entry - atr
            target = entry + atr * target_r
        else:
            stop = entry + atr
            target = entry - atr * target_r
        r_result = _hit_outcome(entry, stop, target, side, rows[index + 1 : index + 7], target_r=target_r)
        spread_cost = float(row.get("spread", 0) or 0) * 0.02
        pnl = risk_amount * r_result - spread_cost
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
        if pnl < 0:
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
        else:
            consecutive_losses = 0
        trades.append(
            {
                "trade_number": len(trades) + 1,
                "time": row["time"].isoformat(),
                "side": side,
                "entry": round(entry, 6),
                "stop": round(stop, 6),
                "target": round(target, 6),
                "r": round(r_result, 3),
                "pnl": round(pnl, 2),
                "cumulative_pnl": round(equity, 2),
                "reason": reason,
                "regime_id": detected.regime_id,
                "trap_score": microstructure.get("institutional_trap_score"),
                "retail_stop_zones": microstructure.get("retail_stop_zones"),
                "tick_volume_ratio": microstructure.get("tick_volume_ratio"),
                "liquidity_sweep_direction": microstructure.get("liquidity_sweep_direction"),
                "bars_held_max": 6,
            }
        )
        equity_curve.append({"time": row["time"].isoformat(), "equity": round(float(investment_amount) + equity, 2), "net_pl": round(equity, 2)})

    wins = [trade for trade in trades if trade["pnl"] > 0]
    losses = [trade for trade in trades if trade["pnl"] <= 0]
    gross_profit = sum(trade["pnl"] for trade in wins)
    gross_loss = abs(sum(trade["pnl"] for trade in losses))
    net_pnl = gross_profit - gross_loss
    spread_cost = sum(float(row.get("spread", 0) or 0) * 0.02 for row in rows[-len(trades) :]) if trades else 0.0
    avg_win = mean([trade["pnl"] for trade in wins]) if wins else 0.0
    avg_loss = abs(mean([trade["pnl"] for trade in losses])) if losses else 0.0
    period = {
        "start": rows[0]["time"].isoformat(),
        "end": rows[-1]["time"].isoformat(),
        "bars": len(rows),
    }
    source_keys = sorted(set((regime_model.get("sources") or []) + (strategy_research.get("sources") or [])))
    return {
        "blocked": False,
        "label": "scenario estimate",
        "api_request": {
            "method": "POST",
            "url": "/api/backtests/run",
            "body": {
                "symbol": symbol.upper(),
                "timeframe": timeframe.upper(),
                "selected_regime": selected_regime,
                "selected_strategy": selected_strategy,
                "investment_amount": investment_amount,
                "bars": bars,
                "source": source,
                "regime_scope": regime_scope,
                "killzone_enabled": killzone_enabled,
                "breakout_enabled": breakout_enabled,
                "sweep_enabled": sweep_enabled,
                "alpha_enabled": alpha_enabled,
                "spread_filter_enabled": spread_filter_enabled,
            },
        },
        "symbol": symbol.upper(),
        "timeframe": timeframe.upper(),
        "period": period,
        "selected_regime": selected_regime,
        "strategy": strategy,
        "strategy_family": family,
        "research_model": regime_model,
        "strategy_research": strategy_research,
        "evidence_sources": regime_research.source_details(source_keys),
        "news_sentiment_status": regime_research.news_sentiment_status(),
        "risk_amount_per_trade": round(risk_amount, 2),
        "risk_multiplier": round(risk_multiplier, 3),
        "target_r_multiple": round(target_r, 2),
        "candidate_trades": len(trades) + fail_reasons["no setup"],
        "executed_simulated_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(100.0 * len(wins) / len(trades), 2) if trades else 0.0,
        "loss_rate": round(100.0 * len(losses) / len(trades), 2) if trades else 0.0,
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "net_pl": round(net_pnl, 2),
        "return_percent": round(100.0 * net_pnl / float(investment_amount), 3) if investment_amount else 0.0,
        "spread_cost": round(spread_cost, 2),
        "slippage_estimate": round(len(trades) * risk_amount * 0.02, 2),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else (round(gross_profit, 3) if gross_profit else 0.0),
        "expectancy": round(net_pnl / len(trades), 2) if trades else 0.0,
        "average_win": round(avg_win, 2),
        "average_loss": round(avg_loss, 2),
        "ratio_avg_win_loss": round(avg_win / avg_loss, 3) if avg_loss else 0.0,
        "average_r": round(mean([trade["r"] for trade in trades]), 3) if trades else 0.0,
        "average_bars_in_trade": 6 if trades else 0,
        "trade_frequency_per_100_bars": round(100.0 * len(trades) / len(rows), 2),
        "max_drawdown": round(abs(max_drawdown), 2),
        "max_consecutive_losses": max_consecutive_losses,
        "best_trade": max(trades, key=lambda trade: trade["pnl"], default=None),
        "worst_trade": min(trades, key=lambda trade: trade["pnl"], default=None),
        "fail_reason_counts": dict(fail_reasons),
        "institutional_impact_flags": {
            **dict(institutional_flags),
            "liquidity_sweep": fail_reasons.get("liquidity sweep", 0),
            "spread_stress": fail_reasons.get("spread too high", 0),
            "news_feed_status": "unavailable_without_feed",
            "low_liquidity": fail_reasons.get("killzone blocked", 0),
            "false_breakout": fail_reasons.get("false breakout", 0),
            "trend_exhaustion": fail_reasons.get("trend exhausted", 0),
        },
        "alpha_notes": [
            str(strategy_research.get("entry_logic") or "strategy formula"),
            str(strategy_research.get("invalid_when") or "invalid conditions not configured"),
            "P/L uses MT5 OHLC bars and configured R-multiple assumptions; no live order is sent.",
        ],
        "failure_events": failure_events[-40:],
        "equity_curve": equity_curve[-120:],
        "trades": trades[-25:],
    }
