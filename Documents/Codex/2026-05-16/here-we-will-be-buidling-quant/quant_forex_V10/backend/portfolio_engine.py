from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd

from backend.backtest_engine import run_backtest


DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
DEFAULT_TIMEFRAMES = ["M15", "M5", "H1"]


def _clean_list(values: Any, fallback: list[str]) -> list[str]:
    if isinstance(values, str):
        items = [item.strip().upper() for item in values.split(",") if item.strip()]
    elif isinstance(values, list):
        items = [str(item).strip().upper() for item in values if str(item).strip()]
    else:
        items = []
    return items or fallback


def _profit_factor(results: list[float]) -> float:
    gross_profit = sum(value for value in results if value > 0)
    gross_loss = abs(sum(value for value in results if value < 0))
    if gross_loss == 0:
        return 999.0 if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def _max_drawdown(values: list[float]) -> float:
    peak = 0.0
    cumulative = 0.0
    max_dd = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    return max_dd


def _max_losing_streak(values: list[float]) -> int:
    current = 0
    maximum = 0
    for value in values:
        if value < 0:
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return maximum


def _performance_from_trades(trades: list[dict[str, Any]]) -> dict[str, Any]:
    results = [float(trade.get("result_R", 0) or 0) for trade in trades]
    profits = [float(trade.get("profit", 0) or 0) for trade in trades]
    wins = [value for value in results if value > 0]
    losses = [value for value in results if value < 0]
    count = len(results)
    win_rate = len(wins) / count if count else 0.0
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    loss_rate = len(losses) / count if count else 0.0
    return {
        "trade_count": count,
        "win_rate": round(win_rate, 4),
        "loss_rate": round(loss_rate, 4),
        "profit_factor": round(_profit_factor(results), 4),
        "expectancy_R": round(float(np.mean(results)) if results else 0.0, 4),
        "average_R": round(float(np.mean(results)) if results else 0.0, 4),
        "average_win_R": round(avg_win, 4),
        "average_loss_R": round(avg_loss, 4),
        "total_R": round(sum(results), 4),
        "max_drawdown_R": round(_max_drawdown(results), 4),
        "max_losing_streak": _max_losing_streak(results),
        "net_profit": round(sum(profits), 2),
        "gross_profit": round(sum(value for value in profits if value > 0), 2),
        "gross_loss": round(sum(value for value in profits if value < 0), 2),
    }


def _portfolio_curves(trades: list[dict[str, Any]], initial_equity: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted(trades, key=lambda trade: str(trade.get("exit_time") or trade.get("entry_time") or ""))
    equity = initial_equity
    peak_equity = initial_equity
    cumulative_r = 0.0
    peak_r = 0.0
    equity_curve = []
    drawdown_curve = []
    for trade in ordered:
        profit = float(trade.get("profit", 0) or 0)
        result_r = float(trade.get("result_R", 0) or 0)
        equity += profit
        cumulative_r += result_r
        peak_equity = max(peak_equity, equity)
        peak_r = max(peak_r, cumulative_r)
        when = trade.get("exit_time") or trade.get("entry_time")
        equity_curve.append({"time": when, "equity": round(equity, 2), "cumulative_R": round(cumulative_r, 4)})
        drawdown_curve.append(
            {
                "time": when,
                "drawdown_R": round(cumulative_r - peak_r, 4),
                "drawdown_amount": round(equity - peak_equity, 2),
            }
        )
    return equity_curve, drawdown_curve


def _rows_by_key(trades: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get(key) or "Unknown")].append(trade)
    rows = []
    for value, group in grouped.items():
        rows.append({key: value, **_performance_from_trades(group)})
    rows.sort(key=lambda item: (item["trade_count"], item["net_profit"]), reverse=True)
    return rows


def _trade_currencies(symbol: str) -> tuple[str, str]:
    clean = "".join(ch for ch in str(symbol or "").upper() if ch.isalnum())
    if len(clean) >= 6:
        return clean[:3], clean[3:6]
    return clean or "UNKNOWN", "UNKNOWN"


def _trade_exposure_weight(trade: dict[str, Any]) -> float:
    initial_risk = abs(float(trade.get("initial_risk", 0) or 0))
    profit = abs(float(trade.get("profit", 0) or 0))
    result_r = abs(float(trade.get("result_R", 0) or 0))
    if initial_risk > 0:
        return initial_risk
    if profit > 0:
        return profit
    if result_r > 0:
        return result_r
    return 1.0


def _currency_exposure_rows(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exposure: dict[str, dict[str, float]] = defaultdict(lambda: {"net_weight": 0.0, "gross_weight": 0.0, "trades": 0.0})
    for trade in trades:
        base, quote = _trade_currencies(str(trade.get("symbol") or ""))
        direction = str(trade.get("direction") or "").lower()
        if direction not in {"long", "short"}:
            continue
        sign = 1.0 if direction == "long" else -1.0
        weight = _trade_exposure_weight(trade)
        exposure[base]["net_weight"] += sign * weight
        exposure[base]["gross_weight"] += weight
        exposure[base]["trades"] += 1
        exposure[quote]["net_weight"] -= sign * weight
        exposure[quote]["gross_weight"] += weight
        exposure[quote]["trades"] += 1

    total_gross = sum(row["gross_weight"] for row in exposure.values())
    rows = []
    for currency, row in exposure.items():
        net = row["net_weight"]
        direction = "long" if net > 0 else "short" if net < 0 else "flat"
        rows.append(
            {
                "currency": currency,
                "direction": direction,
                "net_weight": round(net, 4),
                "gross_weight": round(row["gross_weight"], 4),
                "share": round(row["gross_weight"] / total_gross, 4) if total_gross else 0.0,
                "trades": int(row["trades"]),
            }
        )
    rows.sort(key=lambda item: item["share"], reverse=True)
    return rows


def _concentration_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    total_trades = sum(int(row.get("trade_count", 0) or 0) for row in rows)
    total_abs_profit = sum(abs(float(row.get("net_profit", 0) or 0)) for row in rows)
    output = []
    for row in rows:
        trades = int(row.get("trade_count", 0) or 0)
        abs_profit = abs(float(row.get("net_profit", 0) or 0))
        output.append(
            {
                key: row.get(key),
                "trade_count": trades,
                "trade_share": round(trades / total_trades, 4) if total_trades else 0.0,
                "abs_profit_share": round(abs_profit / total_abs_profit, 4) if total_abs_profit else 0.0,
                "net_profit": row.get("net_profit", 0),
                "expectancy_R": row.get("expectancy_R", 0),
                "profit_factor": row.get("profit_factor", 0),
            }
        )
    output.sort(key=lambda item: (item["trade_share"], item["abs_profit_share"]), reverse=True)
    return output


def _daily_risk(trades: list[dict[str, Any]]) -> dict[str, Any]:
    daily: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        try:
            day = pd.Timestamp(trade.get("entry_time") or trade.get("exit_time")).strftime("%Y-%m-%d")
        except Exception:
            day = "Unknown"
        daily[day].append(trade)
    rows = []
    for day, group in daily.items():
        result_r = sum(float(trade.get("result_R", 0) or 0) for trade in group)
        profit = sum(float(trade.get("profit", 0) or 0) for trade in group)
        rows.append({"date": day, "trades": len(group), "net_R": round(result_r, 4), "net_profit": round(profit, 2)})
    rows.sort(key=lambda item: item["date"])
    worst = min(rows, key=lambda item: item["net_R"], default={})
    best = max(rows, key=lambda item: item["net_R"], default={})
    return {
        "rows": rows,
        "days_with_trades": len(rows),
        "max_trades_in_day": max((row["trades"] for row in rows), default=0),
        "worst_day_R": worst.get("net_R", 0),
        "worst_day": worst.get("date"),
        "best_day_R": best.get("net_R", 0),
        "best_day": best.get("date"),
    }


def _risk_check(name: str, passed: bool, value: Any, limit: Any, severity: str, reason: str) -> dict[str, Any]:
    return {
        "check": name,
        "passed": bool(passed),
        "value": value,
        "limit": limit,
        "severity": severity,
        "reason": reason,
    }


def _portfolio_risk_diagnostics(
    trades: list[dict[str, Any]],
    symbol_rows: list[dict[str, Any]],
    timeframe_rows: list[dict[str, Any]],
    robustness_rows: list[dict[str, Any]],
    correlation: dict[str, Any],
    perf: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    controls = request.get("portfolio_risk") or {}
    max_symbol_trade_share = float(controls.get("max_symbol_trade_share", 0.50) or 0.50)
    max_symbol_abs_profit_share = float(controls.get("max_symbol_abs_profit_share", 0.60) or 0.60)
    max_timeframe_trade_share = float(controls.get("max_timeframe_trade_share", 0.60) or 0.60)
    max_drawdown_r = float(controls.get("max_drawdown_R", 12.0) or 12.0)
    max_currency_exposure_share = float(controls.get("max_currency_exposure_share", 0.65) or 0.65)
    min_symbols_with_trades = int(controls.get("min_symbols_with_trades", 2) or 2)
    min_robust_regimes = int(controls.get("min_robust_regimes", 1) or 1)
    max_average_correlation = float(controls.get("max_average_correlation", 0.75) or 0.75)
    max_trades_per_day = int(controls.get("max_trades_per_day", 20) or 20)

    if not trades:
        return {
            "status": "NO_TRADES",
            "risk_score": 0,
            "checks": [
                _risk_check(
                    "portfolio_has_trades",
                    False,
                    0,
                    "> 0",
                    "critical",
                    "No trades were produced, so portfolio risk cannot be evaluated.",
                )
            ],
            "currency_exposure": [],
            "symbol_concentration": [],
            "timeframe_concentration": [],
            "daily_risk": {"rows": [], "days_with_trades": 0, "max_trades_in_day": 0},
            "recommendations": ["Load data or relax filters enough to produce a minimum portfolio sample before assessing risk."],
        }

    symbol_concentration = _concentration_rows(symbol_rows, "symbol")
    timeframe_concentration = _concentration_rows(timeframe_rows, "timeframe")
    currency_exposure = _currency_exposure_rows(trades)
    daily = _daily_risk(trades)
    robust_regimes = sum(1 for row in robustness_rows if row.get("robust_across_instruments"))
    max_symbol_trade = max((row["trade_share"] for row in symbol_concentration), default=0.0)
    max_symbol_profit = max((row["abs_profit_share"] for row in symbol_concentration), default=0.0)
    max_timeframe_trade = max((row["trade_share"] for row in timeframe_concentration), default=0.0)
    max_currency_share = max((row["share"] for row in currency_exposure), default=0.0)
    avg_corr = correlation.get("average_pairwise_correlation")
    drawdown = abs(float(perf.get("max_drawdown_R", 0) or 0))
    symbols_with_trades = len([row for row in symbol_rows if int(row.get("trade_count", 0) or 0) > 0])

    checks = [
        _risk_check(
            "min_symbols_with_trades",
            symbols_with_trades >= min_symbols_with_trades,
            symbols_with_trades,
            min_symbols_with_trades,
            "major",
            "A portfolio setup should not rely on one instrument only.",
        ),
        _risk_check(
            "max_symbol_trade_share",
            max_symbol_trade <= max_symbol_trade_share,
            round(max_symbol_trade, 4),
            max_symbol_trade_share,
            "major",
            "Too many trades from one symbol can hide single-instrument overfit.",
        ),
        _risk_check(
            "max_symbol_abs_profit_share",
            max_symbol_profit <= max_symbol_abs_profit_share,
            round(max_symbol_profit, 4),
            max_symbol_abs_profit_share,
            "major",
            "If one symbol carries most absolute P/L, portfolio robustness is weak.",
        ),
        _risk_check(
            "max_timeframe_trade_share",
            max_timeframe_trade <= max_timeframe_trade_share,
            round(max_timeframe_trade, 4),
            max_timeframe_trade_share,
            "minor",
            "Timeframe concentration can indicate the setup is not portable.",
        ),
        _risk_check(
            "max_portfolio_drawdown_R",
            drawdown <= max_drawdown_r,
            round(drawdown, 4),
            max_drawdown_r,
            "critical",
            "Portfolio drawdown must fit the research and funded-account risk budget.",
        ),
        _risk_check(
            "max_currency_exposure_share",
            max_currency_share <= max_currency_exposure_share,
            round(max_currency_share, 4),
            max_currency_exposure_share,
            "major",
            "Dominant currency exposure means the portfolio may be one macro bet.",
        ),
        _risk_check(
            "min_robust_regimes",
            robust_regimes >= min_robust_regimes,
            robust_regimes,
            min_robust_regimes,
            "major",
            "At least one regime should survive across multiple symbols and timeframes.",
        ),
        _risk_check(
            "max_average_symbol_correlation",
            avg_corr is None or float(avg_corr) <= max_average_correlation,
            avg_corr if avg_corr is not None else "not_enough_months",
            max_average_correlation,
            "minor",
            "High monthly symbol correlation reduces diversification value.",
        ),
        _risk_check(
            "max_trades_per_day",
            daily.get("max_trades_in_day", 0) <= max_trades_per_day,
            daily.get("max_trades_in_day", 0),
            max_trades_per_day,
            "minor",
            "A large trade cluster on one day can indicate event or session crowding.",
        ),
    ]

    penalties = {"critical": 25, "major": 15, "minor": 8}
    risk_score = 100 - sum(penalties.get(check["severity"], 10) for check in checks if not check["passed"])
    risk_score = max(0, min(100, risk_score))
    failed_critical = any((not check["passed"]) and check["severity"] == "critical" for check in checks)
    failed_major = any((not check["passed"]) and check["severity"] == "major" for check in checks)
    if failed_critical or risk_score < 60:
        status = "PORTFOLIO_RISK_FAIL"
    elif failed_major or risk_score < 85:
        status = "PORTFOLIO_RISK_REVIEW"
    else:
        status = "PORTFOLIO_RISK_OK"

    recommendations = []
    failed = [check for check in checks if not check["passed"]]
    for check in failed:
        if check["check"] == "min_symbols_with_trades":
            recommendations.append("Test the setup on more symbols before treating it as portfolio-ready.")
        elif check["check"] == "max_symbol_trade_share":
            recommendations.append("Reduce symbol concentration by testing wider pairs or filtering the dominant symbol separately.")
        elif check["check"] == "max_currency_exposure_share":
            recommendations.append("Review currency exposure; the setup may be mostly a USD, JPY, or XAU directional bet.")
        elif check["check"] == "max_portfolio_drawdown_R":
            recommendations.append("Lower risk, tighten filters, or reject the setup until portfolio drawdown improves.")
        elif check["check"] == "min_robust_regimes":
            recommendations.append("Require at least one regime to pass across multiple symbols and timeframes.")
    if not recommendations:
        recommendations.append("Portfolio risk checks are acceptable for research; still confirm with OOS, walk-forward, Monte Carlo, and MT5 real-tick evidence.")

    return {
        "status": status,
        "risk_score": risk_score,
        "checks": checks,
        "currency_exposure": currency_exposure,
        "symbol_concentration": symbol_concentration,
        "timeframe_concentration": timeframe_concentration,
        "daily_risk": daily,
        "dominant_currency": currency_exposure[0]["currency"] if currency_exposure else None,
        "max_symbol_trade_share": round(max_symbol_trade, 4),
        "max_symbol_abs_profit_share": round(max_symbol_profit, 4),
        "max_timeframe_trade_share": round(max_timeframe_trade, 4),
        "max_currency_exposure_share": round(max_currency_share, 4),
        "recommendations": recommendations,
    }


def _leg_rows_by_status(legs: list[dict[str, Any]]) -> Counter:
    return Counter(str(leg.get("status", "UNKNOWN")) for leg in legs)


def _symbol_timeframe_matrix(legs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for leg in legs:
        if leg.get("status") == "NO_DATA":
            rows.append(
                {
                    "symbol": leg["symbol"],
                    "timeframe": leg["timeframe"],
                    "status": "NO_DATA",
                    "trade_count": 0,
                    "profit_factor": 0,
                    "expectancy_R": 0,
                    "net_profit": 0,
                    "max_drawdown_R": 0,
                }
            )
            continue
        summary = leg.get("summary", {})
        rows.append(
            {
                "symbol": leg["symbol"],
                "timeframe": leg["timeframe"],
                "status": leg.get("status", "COMPLETE"),
                "trade_count": summary.get("total_trades", 0),
                "profit_factor": summary.get("profit_factor", 0),
                "expectancy_R": summary.get("expectancy_R", 0),
                "net_profit": summary.get("net_profit", 0),
                "max_drawdown_R": summary.get("max_drawdown_R", 0),
                "best_regime": summary.get("best_regime"),
                "best_strategy": summary.get("best_strategy"),
            }
        )
    return rows


def _monthly_symbol_correlation(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {"average_pairwise_correlation": None, "matrix": [], "warnings": ["No trades available for correlation."]}
    rows = []
    for trade in trades:
        try:
            month = pd.Timestamp(trade["entry_time"]).strftime("%Y-%m")
        except Exception:
            month = "Unknown"
        rows.append({"month": month, "symbol": trade.get("symbol", "Unknown"), "profit": float(trade.get("profit", 0) or 0)})
    frame = pd.DataFrame(rows)
    pivot = frame.pivot_table(index="month", columns="symbol", values="profit", aggfunc="sum").fillna(0)
    if pivot.shape[1] < 2 or pivot.shape[0] < 2:
        return {
            "average_pairwise_correlation": None,
            "matrix": [],
            "warnings": ["Need at least two symbols and two months of trades for useful correlation."],
        }
    corr = pivot.corr()
    matrix = []
    values = []
    for left in corr.columns:
        for right in corr.columns:
            value = float(corr.loc[left, right])
            if np.isnan(value):
                value = 0.0
            matrix.append({"symbol_1": left, "symbol_2": right, "correlation": round(value, 4)})
            if left < right:
                values.append(value)
    clean_values = [value for value in values if not np.isnan(value)]
    avg = float(np.mean(clean_values)) if clean_values else None
    warnings = []
    if avg is not None and avg >= 0.75:
        warnings.append("High average symbol correlation; portfolio may be one macro bet rather than diversified alpha.")
    return {"average_pairwise_correlation": round(avg, 4) if avg is not None else None, "matrix": matrix, "warnings": warnings}


def _concentration_warnings(symbol_rows: list[dict[str, Any]], timeframe_rows: list[dict[str, Any]]) -> list[str]:
    warnings = []
    total_trades = sum(int(row.get("trade_count", 0) or 0) for row in symbol_rows)
    total_abs_profit = sum(abs(float(row.get("net_profit", 0) or 0)) for row in symbol_rows)
    for row in symbol_rows:
        trade_share = (int(row.get("trade_count", 0) or 0) / total_trades) if total_trades else 0
        profit_share = (abs(float(row.get("net_profit", 0) or 0)) / total_abs_profit) if total_abs_profit else 0
        if trade_share >= 0.50:
            warnings.append(f"{row['symbol']} contributes {trade_share:.0%} of trades; symbol concentration is high.")
        if profit_share >= 0.60:
            warnings.append(f"{row['symbol']} contributes {profit_share:.0%} of absolute P/L; profit concentration is high.")
    total_tf_trades = sum(int(row.get("trade_count", 0) or 0) for row in timeframe_rows)
    for row in timeframe_rows:
        share = (int(row.get("trade_count", 0) or 0) / total_tf_trades) if total_tf_trades else 0
        if share >= 0.60:
            warnings.append(f"{row['timeframe']} contributes {share:.0%} of trades; timeframe concentration is high.")
    return warnings


def _regime_robustness(all_trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in all_trades:
        grouped[str(trade.get("regime_id") or "Unknown")].append(trade)
    rows = []
    for regime_id, trades in grouped.items():
        symbols = sorted({str(trade.get("symbol")) for trade in trades if trade.get("symbol")})
        timeframes = sorted({str(trade.get("timeframe")) for trade in trades if trade.get("timeframe")})
        perf = _performance_from_trades(trades)
        robust = len(symbols) >= 2 and len(timeframes) >= 2 and perf["trade_count"] >= 30 and perf["expectancy_R"] > 0 and perf["profit_factor"] >= 1.1
        rows.append(
            {
                "regime_id": regime_id,
                "regime_name": trades[0].get("regime_name"),
                "symbols_with_trades": len(symbols),
                "timeframes_with_trades": len(timeframes),
                "symbols": ", ".join(symbols),
                "timeframes": ", ".join(timeframes),
                "robust_across_instruments": robust,
                **perf,
            }
        )
    rows.sort(key=lambda item: (item["robust_across_instruments"], item["symbols_with_trades"], item["trade_count"]), reverse=True)
    return rows


def _status(summary: dict[str, Any], completed_legs: int, total_legs: int, robust_regimes: int) -> str:
    if total_legs == 0:
        return "NO_INPUTS"
    if completed_legs == 0:
        return "NO_DATA"
    if completed_legs < max(2, total_legs // 3):
        return "INSUFFICIENT_PORTFOLIO_DATA"
    if summary.get("total_trades", 0) >= 100 and summary.get("expectancy_R", 0) > 0 and summary.get("profit_factor", 0) >= 1.15 and robust_regimes > 0:
        return "PORTFOLIO_WATCHLIST"
    return "RESEARCH_ONLY"


def run_portfolio_backtest(request: dict[str, Any]) -> dict[str, Any]:
    symbols = _clean_list(request.get("symbols"), DEFAULT_SYMBOLS)
    timeframes = _clean_list(request.get("timeframes"), DEFAULT_TIMEFRAMES)
    max_legs = int(request.get("max_legs", 60) or 60)
    initial_equity = float(request.get("initial_equity", 100000) or 100000)
    legs = []
    all_trades: list[dict[str, Any]] = []
    warnings = [
        "Portfolio research reuses the Python candle backtest per symbol/timeframe. Confirm candidates with MT5 real-tick reports before trusting execution.",
        "Portfolio aggregation is a research view; it does not enforce margin, exposure caps, or simultaneous-position limits yet.",
    ]
    requested_pairs = [(symbol, timeframe) for symbol in symbols for timeframe in timeframes][:max_legs]
    if len(symbols) * len(timeframes) > max_legs:
        warnings.append(f"Requested {len(symbols) * len(timeframes)} legs but max_legs={max_legs}; truncated the portfolio run.")

    for symbol, timeframe in requested_pairs:
        payload = deepcopy(request)
        payload["symbol"] = symbol
        payload["timeframe"] = timeframe
        payload.pop("symbols", None)
        payload.pop("timeframes", None)
        payload.pop("max_legs", None)
        try:
            result = run_backtest(payload, persist=False)
        except ValueError as exc:
            legs.append({"symbol": symbol, "timeframe": timeframe, "status": "NO_DATA", "error": str(exc), "summary": {}, "trades": 0})
            continue
        leg_trades = result.get("trades", [])
        for trade in leg_trades:
            all_trades.append({**trade, "portfolio_leg": f"{symbol}_{timeframe}"})
        legs.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "status": "COMPLETE",
                "run_id": result.get("run_id"),
                "summary": result.get("summary", {}),
                "data_health": result.get("data_health", {}),
                "regime_rows": len(result.get("regime_performance", [])),
                "strategy_rows": len(result.get("strategy_performance", [])),
                "trades": len(leg_trades),
            }
        )

    completed = [leg for leg in legs if leg.get("status") == "COMPLETE"]
    perf = _performance_from_trades(all_trades)
    equity_curve, drawdown_curve = _portfolio_curves(all_trades, initial_equity)
    ending_equity = equity_curve[-1]["equity"] if equity_curve else initial_equity
    symbol_performance = _rows_by_key(all_trades, "symbol")
    timeframe_performance = _rows_by_key(all_trades, "timeframe")
    matrix = _symbol_timeframe_matrix(legs)
    correlation = _monthly_symbol_correlation(all_trades)
    robustness = _regime_robustness(all_trades)
    robust_regimes = sum(1 for row in robustness if row.get("robust_across_instruments"))
    concentration = _concentration_warnings(symbol_performance, timeframe_performance)
    risk_diagnostics = _portfolio_risk_diagnostics(
        all_trades,
        symbol_performance,
        timeframe_performance,
        robustness,
        correlation,
        perf,
        request,
    )
    warnings.extend(correlation.get("warnings", []))
    warnings.extend(concentration)
    warnings.extend(risk_diagnostics.get("recommendations", []))
    status = _status(perf, len(completed), len(requested_pairs), robust_regimes)
    best_symbol = max(symbol_performance, key=lambda row: row["expectancy_R"], default={}).get("symbol")
    worst_symbol = min(symbol_performance, key=lambda row: row["expectancy_R"], default={}).get("symbol")
    best_timeframe = max(timeframe_performance, key=lambda row: row["expectancy_R"], default={}).get("timeframe")
    worst_timeframe = min(timeframe_performance, key=lambda row: row["expectancy_R"], default={}).get("timeframe")
    no_data_legs = [leg for leg in legs if leg.get("status") == "NO_DATA"]
    summary = {
        "status": status,
        "symbols_requested": symbols,
        "timeframes_requested": timeframes,
        "legs_requested": len(requested_pairs),
        "legs_completed": len(completed),
        "legs_no_data": len(no_data_legs),
        "initial_equity": round(initial_equity, 2),
        "ending_equity": round(ending_equity, 2),
        "roi_percent": round(((ending_equity - initial_equity) / initial_equity) * 100, 4) if initial_equity else 0,
        "best_symbol": best_symbol,
        "worst_symbol": worst_symbol,
        "best_timeframe": best_timeframe,
        "worst_timeframe": worst_timeframe,
        "robust_regime_count": robust_regimes,
        "average_symbol_correlation": correlation.get("average_pairwise_correlation"),
        "portfolio_risk_status": risk_diagnostics.get("status"),
        "portfolio_risk_score": risk_diagnostics.get("risk_score"),
        "dominant_currency": risk_diagnostics.get("dominant_currency"),
        "max_symbol_trade_share": risk_diagnostics.get("max_symbol_trade_share"),
        "max_currency_exposure_share": risk_diagnostics.get("max_currency_exposure_share"),
        **perf,
    }
    return {
        "summary": summary,
        "legs": legs,
        "symbol_performance": symbol_performance,
        "timeframe_performance": timeframe_performance,
        "symbol_timeframe_matrix": matrix,
        "correlation": correlation,
        "concentration_warnings": concentration,
        "risk_diagnostics": risk_diagnostics,
        "regime_robustness": robustness,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "warnings": warnings,
        "request": {**request, "symbols": symbols, "timeframes": timeframes},
    }
