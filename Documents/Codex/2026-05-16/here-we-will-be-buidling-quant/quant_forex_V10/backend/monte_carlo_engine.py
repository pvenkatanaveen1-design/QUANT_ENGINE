from __future__ import annotations

from typing import Any

import numpy as np

from backend.backtest_engine import run_backtest


def _percentiles(values: list[float], digits: int = 4) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "p05": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p95": 0.0, "max": 0.0, "mean": 0.0}
    arr = np.array(values, dtype=float)
    return {
        "min": round(float(np.min(arr)), digits),
        "p05": round(float(np.percentile(arr, 5)), digits),
        "p25": round(float(np.percentile(arr, 25)), digits),
        "p50": round(float(np.percentile(arr, 50)), digits),
        "p75": round(float(np.percentile(arr, 75)), digits),
        "p95": round(float(np.percentile(arr, 95)), digits),
        "max": round(float(np.max(arr)), digits),
        "mean": round(float(np.mean(arr)), digits),
    }


def _max_drawdown_r(results: list[float]) -> float:
    peak = 0.0
    cumulative = 0.0
    max_dd = 0.0
    for value in results:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    return max_dd


def _max_losing_streak(results: list[float]) -> int:
    current = 0
    worst = 0
    for value in results:
        if value < 0:
            current += 1
            worst = max(worst, current)
        else:
            current = 0
    return worst


def _downsample_fan(path_percentiles: dict[str, list[float]], max_points: int = 240) -> list[dict[str, Any]]:
    length = len(next(iter(path_percentiles.values()), []))
    if length == 0:
        return []
    step = max(1, int(np.ceil(length / max_points)))
    rows = []
    for index in range(0, length, step):
        rows.append(
            {
                "trade": index,
                "p05_equity": round(path_percentiles["p05"][index], 2),
                "p50_equity": round(path_percentiles["p50"][index], 2),
                "p95_equity": round(path_percentiles["p95"][index], 2),
            }
        )
    if rows[-1]["trade"] != length - 1:
        last = length - 1
        rows.append(
            {
                "trade": last,
                "p05_equity": round(path_percentiles["p05"][last], 2),
                "p50_equity": round(path_percentiles["p50"][last], 2),
                "p95_equity": round(path_percentiles["p95"][last], 2),
            }
        )
    return rows


def _status(
    trade_count: int,
    min_trades: int,
    probability_loss: float,
    probability_drawdown_breach: float,
    probability_losing_streak_breach: float,
    total_r_p05: float,
    total_r_p50: float,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if trade_count < min_trades:
        reasons.append(f"Only {trade_count} trades; Monte Carlo needs at least {min_trades} for a useful distribution.")
    if total_r_p50 <= 0:
        reasons.append("Median simulated total R is not positive.")
    if total_r_p05 <= 0:
        reasons.append("Worst 5% simulated total R is not positive.")
    if probability_loss > 0.25:
        reasons.append(f"Probability of ending below starting equity is {probability_loss:.1%}.")
    if probability_drawdown_breach > 0.10:
        reasons.append(f"Drawdown breach probability is {probability_drawdown_breach:.1%}.")
    if probability_losing_streak_breach > 0.20:
        reasons.append(f"Losing-streak breach probability is {probability_losing_streak_breach:.1%}.")

    if trade_count < min_trades:
        return "INSUFFICIENT_DATA", reasons
    if probability_drawdown_breach > 0.20 or probability_loss > 0.35 or total_r_p50 <= 0:
        return "FAIL", reasons
    if reasons:
        return "WATCHLIST", reasons
    return "PASS", ["Monte Carlo distribution stayed positive with acceptable drawdown and losing-streak risk."]


def _no_data_response(request: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "summary": {
            "status": "NO_DATA",
            "source_trades": 0,
            "simulations": 0,
            "sample_mode": request.get("sample_mode", "bootstrap"),
            "message": message,
        },
        "observed": {},
        "distribution": {},
        "equity_fan": [],
        "risk_of_ruin": {},
        "reasons": [message],
        "warnings": ["Monte Carlo needs executed backtest trades. Check symbol, date range, regime, strategy, and filters."],
        "request": request,
    }


def run_monte_carlo(request: dict[str, Any]) -> dict[str, Any]:
    simulations = int(request.get("simulations") or 1000)
    sample_mode = str(request.get("sample_mode") or "bootstrap")
    min_trades = int(request.get("min_trades") or 30)
    max_total_drawdown_percent = float(request.get("max_total_drawdown_percent") or 10.0)
    max_losing_streak_limit = int(request.get("max_losing_streak_limit") or 5)
    seed = request.get("seed", 42)
    rng = np.random.default_rng(None if seed is None else int(seed))

    try:
        backtest = run_backtest(request, persist=False)
    except ValueError as exc:
        return _no_data_response(request, str(exc))

    trades = backtest.get("trades", [])
    r_values = [float(trade.get("result_R") or 0.0) for trade in trades]
    trade_count = len(r_values)
    if not r_values:
        return _no_data_response(request, "Backtest completed but produced no executed trades for Monte Carlo.")

    initial_equity = float(request.get("initial_equity") or backtest.get("summary", {}).get("initial_equity") or 100000)
    risk_percent = float(request.get("risk_percent") or backtest.get("request", {}).get("risk_percent") or 1.0)
    risk_fraction = risk_percent / 100.0
    simulations = max(1, min(simulations, 10000))

    ending_equities: list[float] = []
    total_rs: list[float] = []
    max_drawdown_rs: list[float] = []
    max_drawdown_percents: list[float] = []
    max_losing_streaks: list[int] = []
    equity_paths = np.empty((simulations, trade_count + 1), dtype=float)

    for sim in range(simulations):
        if sample_mode == "shuffle":
            sampled = rng.permutation(r_values).astype(float)
        else:
            sampled = np.array(rng.choice(r_values, size=trade_count, replace=True), dtype=float)

        equity = initial_equity
        peak_equity = initial_equity
        max_dd_percent = 0.0
        path = [initial_equity]
        for result_r in sampled:
            equity += equity * risk_fraction * float(result_r)
            peak_equity = max(peak_equity, equity)
            max_dd_percent = min(max_dd_percent, ((equity - peak_equity) / peak_equity) * 100 if peak_equity else 0.0)
            path.append(equity)

        sequence = sampled.tolist()
        ending_equities.append(float(equity))
        total_rs.append(float(np.sum(sampled)))
        max_drawdown_rs.append(float(_max_drawdown_r(sequence)))
        max_drawdown_percents.append(float(max_dd_percent))
        max_losing_streaks.append(_max_losing_streak(sequence))
        equity_paths[sim, :] = np.array(path, dtype=float)

    path_percentiles = {
        "p05": np.percentile(equity_paths, 5, axis=0).tolist(),
        "p50": np.percentile(equity_paths, 50, axis=0).tolist(),
        "p95": np.percentile(equity_paths, 95, axis=0).tolist(),
    }
    probability_loss = float(np.mean(np.array(ending_equities) < initial_equity))
    probability_drawdown_breach = float(np.mean(np.array(max_drawdown_percents) <= -abs(max_total_drawdown_percent)))
    probability_losing_streak_breach = float(np.mean(np.array(max_losing_streaks) >= max_losing_streak_limit))
    total_r_stats = _percentiles(total_rs)
    status, reasons = _status(
        trade_count,
        min_trades,
        probability_loss,
        probability_drawdown_breach,
        probability_losing_streak_breach,
        total_r_stats["p05"],
        total_r_stats["p50"],
    )

    warnings = [
        "Monte Carlo stress-tests trade ordering and resampling risk. It does not replace out-of-sample, walk-forward, or MT5 real-tick validation."
    ]
    if sample_mode == "shuffle":
        warnings.append("Shuffle mode preserves the exact trade distribution and changes only trade order; use bootstrap mode for distribution uncertainty.")
    if trade_count < min_trades:
        warnings.append("Low trade count makes Monte Carlo tails unstable. Treat the result as diagnostic only.")

    return {
        "summary": {
            "status": status,
            "source_trades": trade_count,
            "simulations": simulations,
            "sample_mode": sample_mode,
            "initial_equity": round(initial_equity, 2),
            "risk_percent": risk_percent,
            "max_total_drawdown_percent": max_total_drawdown_percent,
            "max_losing_streak_limit": max_losing_streak_limit,
            "median_ending_equity": _percentiles(ending_equities, 2)["p50"],
            "p05_ending_equity": _percentiles(ending_equities, 2)["p05"],
            "p95_ending_equity": _percentiles(ending_equities, 2)["p95"],
            "median_total_R": total_r_stats["p50"],
            "p05_total_R": total_r_stats["p05"],
            "median_max_drawdown_percent": _percentiles(max_drawdown_percents)["p50"],
            "worst_5pct_max_drawdown_percent": _percentiles(max_drawdown_percents)["p05"],
            "probability_profit": round(1 - probability_loss, 4),
            "probability_loss": round(probability_loss, 4),
            "probability_drawdown_breach": round(probability_drawdown_breach, 4),
            "probability_losing_streak_breach": round(probability_losing_streak_breach, 4),
        },
        "observed": {
            "total_R": round(float(np.sum(r_values)), 4),
            "max_drawdown_R": round(_max_drawdown_r(r_values), 4),
            "max_losing_streak": _max_losing_streak(r_values),
            "ending_equity": backtest.get("summary", {}).get("ending_equity"),
            "profit_factor": backtest.get("summary", {}).get("profit_factor"),
            "expectancy_R": backtest.get("summary", {}).get("expectancy_R"),
        },
        "distribution": {
            "ending_equity": _percentiles(ending_equities, 2),
            "total_R": total_r_stats,
            "max_drawdown_R": _percentiles(max_drawdown_rs),
            "max_drawdown_percent": _percentiles(max_drawdown_percents),
            "max_losing_streak": _percentiles(max_losing_streaks, 2),
        },
        "equity_fan": _downsample_fan(path_percentiles),
        "risk_of_ruin": {
            "loss_probability": round(probability_loss, 4),
            "drawdown_breach_probability": round(probability_drawdown_breach, 4),
            "losing_streak_breach_probability": round(probability_losing_streak_breach, 4),
            "thresholds": {
                "max_total_drawdown_percent": max_total_drawdown_percent,
                "max_losing_streak_limit": max_losing_streak_limit,
            },
        },
        "reasons": reasons,
        "warnings": warnings,
        "request": {
            "symbol": request.get("symbol"),
            "timeframe": request.get("timeframe"),
            "start_date": request.get("start_date"),
            "end_date": request.get("end_date"),
            "regime_filter": request.get("regime_filter"),
            "strategy_filter": request.get("strategy_filter"),
            "sample_mode": sample_mode,
            "simulations": simulations,
        },
    }
