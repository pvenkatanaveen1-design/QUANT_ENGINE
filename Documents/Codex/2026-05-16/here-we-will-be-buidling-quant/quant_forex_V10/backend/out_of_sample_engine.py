from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from backend.backtest_engine import run_backtest


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(str(value)[:10]).date()


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
        "average_win_R": float(summary.get("average_win_R") or 0),
        "average_loss_R": float(summary.get("average_loss_R") or 0),
        "max_drawdown_R": float(summary.get("max_drawdown_R") or 0),
        "max_losing_streak": int(summary.get("max_losing_streak") or 0),
        "net_profit": float(summary.get("net_profit") or 0),
        "roi_percent": float(summary.get("roi_percent") or 0),
        "total_R": _total_r(result),
        "best_regime": summary.get("best_regime"),
        "best_strategy": summary.get("best_strategy"),
        "best_session": summary.get("best_session"),
        "worst_session": summary.get("worst_session"),
        "skipped_setups": int(summary.get("skipped_setups") or 0),
    }


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _split_dates(request: dict[str, Any]) -> tuple[date, date, date, date]:
    start = _parse_date(request["start_date"])
    end = _parse_date(request["end_date"])
    if end <= start:
        raise ValueError("end_date must be after start_date.")

    split_date = request.get("split_date")
    if split_date:
        split = _parse_date(split_date)
    else:
        oos_percent = float(request.get("oos_percent") or 30)
        if not 5 <= oos_percent <= 80:
            raise ValueError("oos_percent must be between 5 and 80.")
        total_days = max(1, (end - start).days + 1)
        in_sample_days = max(1, round(total_days * (1 - oos_percent / 100)))
        split = start + timedelta(days=in_sample_days - 1)

    if split <= start:
        raise ValueError("split_date leaves no in-sample period.")
    if split >= end:
        raise ValueError("split_date leaves no out-of-sample period.")

    return start, split, split + timedelta(days=1), end


def _status(in_sample: dict[str, Any], out_sample: dict[str, Any], min_oos_trades: int, min_oos_profit_factor: float) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if in_sample["total_trades"] == 0:
        reasons.append("In-sample produced no trades, so there is no setup to validate.")
    if out_sample["total_trades"] < min_oos_trades:
        reasons.append(f"Out-of-sample has {out_sample['total_trades']} trades; minimum is {min_oos_trades}.")
    if out_sample["expectancy_R"] <= 0:
        reasons.append("Out-of-sample expectancy is not positive.")
    if out_sample["profit_factor"] < min_oos_profit_factor:
        reasons.append(f"Out-of-sample profit factor is below {min_oos_profit_factor}.")
    if in_sample["expectancy_R"] > 0 and out_sample["expectancy_R"] <= 0:
        reasons.append("Positive in-sample edge did not survive out-of-sample.")
    if not reasons:
        return "PASS", ["Out-of-sample test met trade count, expectancy, and profit-factor rules."]
    if out_sample["total_trades"] >= max(10, min_oos_trades // 2) and out_sample["expectancy_R"] > 0:
        return "WATCHLIST", reasons
    return "FAIL", reasons


def run_out_of_sample(request: dict[str, Any]) -> dict[str, Any]:
    min_oos_trades = int(request.get("min_oos_trades") or 20)
    min_oos_profit_factor = float(request.get("min_oos_profit_factor") or 1.1)
    start, in_end, oos_start, end = _split_dates(request)

    base_payload = deepcopy(request)
    for key in ["split_date", "oos_percent", "min_oos_trades", "min_oos_profit_factor"]:
        base_payload.pop(key, None)

    in_payload = {**deepcopy(base_payload), "start_date": _start_iso(start), "end_date": _end_iso(in_end)}
    oos_payload = {**deepcopy(base_payload), "start_date": _start_iso(oos_start), "end_date": _end_iso(end)}

    warnings: list[str] = []
    in_result = run_backtest(in_payload, persist=False)
    oos_result = run_backtest(oos_payload, persist=False)
    in_sample = _summary(in_result)
    out_sample = _summary(oos_result)
    status, reasons = _status(in_sample, out_sample, min_oos_trades, min_oos_profit_factor)

    expectancy_retention = _ratio(out_sample["expectancy_R"], in_sample["expectancy_R"])
    pf_retention = _ratio(out_sample["profit_factor"], in_sample["profit_factor"])
    r_efficiency = _ratio(out_sample["total_R"], in_sample["total_R"])
    drawdown_expansion = _ratio(abs(out_sample["max_drawdown_R"]), abs(in_sample["max_drawdown_R"]))
    retention_inputs = [value for value in [expectancy_retention, pf_retention, r_efficiency] if isinstance(value, (int, float))]
    performance_retention = round(sum(min(value, 1.5) for value in retention_inputs) / len(retention_inputs), 4) if retention_inputs else None

    if expectancy_retention is not None and expectancy_retention < 0.5:
        warnings.append("Out-of-sample expectancy retained less than 50% of in-sample expectancy.")
    if r_efficiency is not None and r_efficiency < 0.5:
        warnings.append("Out-of-sample total R retained less than 50% of in-sample total R.")
    if drawdown_expansion is not None and drawdown_expansion > 1.5:
        warnings.append("Out-of-sample drawdown expanded more than 1.5x versus in-sample.")

    stable = status == "PASS" and (performance_retention is None or performance_retention >= 0.5)
    return {
        "summary": {
            "status": status,
            "stable": stable,
            "split_date": in_end.isoformat(),
            "in_sample_start": start.isoformat(),
            "in_sample_end": in_end.isoformat(),
            "out_sample_start": oos_start.isoformat(),
            "out_sample_end": end.isoformat(),
            "min_oos_trades": min_oos_trades,
            "min_oos_profit_factor": min_oos_profit_factor,
            "expectancy_retention": expectancy_retention,
            "profit_factor_retention": pf_retention,
            "total_R_efficiency": r_efficiency,
            "drawdown_expansion": drawdown_expansion,
            "performance_retention": performance_retention,
        },
        "in_sample": in_sample,
        "out_of_sample": out_sample,
        "comparison": {
            "trade_count_delta": out_sample["total_trades"] - in_sample["total_trades"],
            "win_rate_delta": round(out_sample["win_rate"] - in_sample["win_rate"], 4),
            "profit_factor_delta": round(out_sample["profit_factor"] - in_sample["profit_factor"], 4),
            "expectancy_R_delta": round(out_sample["expectancy_R"] - in_sample["expectancy_R"], 4),
            "total_R_delta": round(out_sample["total_R"] - in_sample["total_R"], 4),
            "net_profit_delta": round(out_sample["net_profit"] - in_sample["net_profit"], 2),
        },
        "reasons": reasons,
        "warnings": warnings,
        "request": {
            "symbol": request.get("symbol"),
            "timeframe": request.get("timeframe"),
            "regime_filter": request.get("regime_filter", "ALL"),
            "strategy_filter": request.get("strategy_filter", "ALL"),
            "start_date": request.get("start_date"),
            "end_date": request.get("end_date"),
            "split_date": in_end.isoformat(),
            "oos_percent": request.get("oos_percent", 30),
        },
    }
