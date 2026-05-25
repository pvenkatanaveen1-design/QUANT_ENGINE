from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from backend.backtest_engine import run_backtest


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(str(value)[:10]).date()


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    month_lengths = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(value.day, month_lengths[month - 1])
    return date(year, month, day)


def _start_iso(value: date) -> str:
    return datetime.combine(value, time.min, tzinfo=timezone.utc).isoformat()


def _end_iso(value: date) -> str:
    return datetime.combine(value, time.max.replace(microsecond=0), tzinfo=timezone.utc).isoformat()


def _total_r(result: dict[str, Any]) -> float:
    return round(sum(float(trade.get("result_R") or 0) for trade in result.get("trades", [])), 4)


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("summary", {})
    return {
        "run_id": result.get("run_id"),
        "total_trades": int(summary.get("total_trades") or 0),
        "win_rate": float(summary.get("win_rate") or 0),
        "profit_factor": float(summary.get("profit_factor") or 0),
        "expectancy_R": float(summary.get("expectancy_R") or 0),
        "average_R": float(summary.get("average_R") or 0),
        "max_drawdown_R": float(summary.get("max_drawdown_R") or 0),
        "max_losing_streak": int(summary.get("max_losing_streak") or 0),
        "net_profit": float(summary.get("net_profit") or 0),
        "roi_percent": float(summary.get("roi_percent") or 0),
        "total_R": _total_r(result),
        "skipped_setups": int(summary.get("skipped_setups") or 0),
    }


def _window_status(test: dict[str, Any], min_test_trades: int, min_pf: float) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if test["total_trades"] < min_test_trades:
        reasons.append(f"Only {test['total_trades']} out-of-sample trades; minimum is {min_test_trades}.")
    if test["expectancy_R"] <= 0:
        reasons.append("Out-of-sample expectancy is not positive.")
    if test["profit_factor"] < min_pf:
        reasons.append(f"Out-of-sample profit factor is below {min_pf}.")
    if not reasons:
        return "PASS", ["Out-of-sample test met trade count, expectancy, and profit-factor rules."]
    if test["total_trades"] >= max(10, min_test_trades // 2) and test["expectancy_R"] > 0:
        return "WATCHLIST", reasons
    return "FAIL", reasons


def run_walk_forward(request: dict[str, Any]) -> dict[str, Any]:
    train_months = int(request.get("train_months") or 2)
    test_months = int(request.get("test_months") or 1)
    step_months = int(request.get("step_months") or 1)
    min_test_trades = int(request.get("min_test_trades") or 20)
    min_test_profit_factor = float(request.get("min_test_profit_factor") or 1.1)

    if train_months < 1 or test_months < 1 or step_months < 1:
        raise ValueError("train_months, test_months, and step_months must be at least 1.")

    global_start = _parse_date(request["start_date"])
    global_end = _parse_date(request["end_date"])
    windows: list[dict[str, Any]] = []
    warnings: list[str] = []
    cursor = global_start
    index = 1

    while True:
        train_start = cursor
        train_end = _add_months(train_start, train_months) - timedelta(days=1)
        test_start = train_end + timedelta(days=1)
        test_end = _add_months(test_start, test_months) - timedelta(days=1)
        if test_start > global_end or test_end > global_end:
            break

        base_payload = deepcopy(request)
        for key in ["train_months", "test_months", "step_months", "min_test_trades", "min_test_profit_factor"]:
            base_payload.pop(key, None)

        train_payload = {**deepcopy(base_payload), "start_date": _start_iso(train_start), "end_date": _end_iso(train_end)}
        test_payload = {**deepcopy(base_payload), "start_date": _start_iso(test_start), "end_date": _end_iso(test_end)}

        window: dict[str, Any] = {
            "window": index,
            "train_start": train_start.isoformat(),
            "train_end": train_end.isoformat(),
            "test_start": test_start.isoformat(),
            "test_end": test_end.isoformat(),
        }
        try:
            train_result = run_backtest(train_payload, persist=False)
            test_result = run_backtest(test_payload, persist=False)
            train = _summary(train_result)
            test = _summary(test_result)
            status, reasons = _window_status(test, min_test_trades, min_test_profit_factor)
            wfe = round(test["total_R"] / train["total_R"], 4) if train["total_R"] > 0 else None
            window.update(
                {
                    "train": train,
                    "test": test,
                    "walk_forward_efficiency": wfe,
                    "status": status,
                    "reasons": reasons,
                }
            )
        except ValueError as exc:
            window.update(
                {
                    "train": {},
                    "test": {},
                    "walk_forward_efficiency": None,
                    "status": "NO_DATA",
                    "reasons": [str(exc)],
                }
            )
        windows.append(window)
        cursor = _add_months(cursor, step_months)
        index += 1

    passed = sum(1 for row in windows if row["status"] == "PASS")
    watchlist = sum(1 for row in windows if row["status"] == "WATCHLIST")
    failed = sum(1 for row in windows if row["status"] in {"FAIL", "NO_DATA"})
    wfe_values = [row["walk_forward_efficiency"] for row in windows if isinstance(row.get("walk_forward_efficiency"), (int, float))]
    average_wfe = round(sum(wfe_values) / len(wfe_values), 4) if wfe_values else None
    total_train_r = round(sum(float(row.get("train", {}).get("total_R") or 0) for row in windows), 4)
    total_test_r = round(sum(float(row.get("test", {}).get("total_R") or 0) for row in windows), 4)
    aggregate_wfe = round(total_test_r / total_train_r, 4) if total_train_r > 0 else None
    pass_rate = round(passed / len(windows), 4) if windows else 0.0

    if not windows:
        warnings.append("No walk-forward windows could be created. Increase date range or reduce train/test months.")
    if any(row["status"] == "NO_DATA" for row in windows):
        warnings.append("One or more windows had no candle data for the selected symbol/timeframe/date range.")
    if average_wfe is not None and average_wfe < 0.5:
        warnings.append("Average walk-forward efficiency is below 0.50; the setup may be unstable out-of-sample.")
    if pass_rate < 0.6 and windows:
        warnings.append("Fewer than 60% of out-of-sample windows passed.")

    stable = bool(windows) and pass_rate >= 0.6 and (average_wfe is None or average_wfe >= 0.5)
    return {
        "summary": {
            "windows": len(windows),
            "passed_windows": passed,
            "watchlist_windows": watchlist,
            "failed_windows": failed,
            "pass_rate": pass_rate,
            "average_walk_forward_efficiency": average_wfe,
            "aggregate_walk_forward_efficiency": aggregate_wfe,
            "total_train_R": total_train_r,
            "total_test_R": total_test_r,
            "stable": stable,
            "min_test_trades": min_test_trades,
            "min_test_profit_factor": min_test_profit_factor,
        },
        "windows": windows,
        "warnings": warnings,
        "request": {
            "symbol": request.get("symbol"),
            "timeframe": request.get("timeframe"),
            "start_date": request.get("start_date"),
            "end_date": request.get("end_date"),
            "regime_filter": request.get("regime_filter", "ALL"),
            "strategy_filter": request.get("strategy_filter", "ALL"),
            "train_months": train_months,
            "test_months": test_months,
            "step_months": step_months,
        },
    }
