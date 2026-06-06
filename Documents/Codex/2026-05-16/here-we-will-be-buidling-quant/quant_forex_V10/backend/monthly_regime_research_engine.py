from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from backend.common.config_loader import load_regimes, load_strategies
from backend.database import load_candles
from backend.optimizer_engine import run_optimizer_grid


NO_TRADE_STRATEGIES = {"D0", "D1", "DQ1", "TR2", "AR5", "DL1", "MF1"}
MACRO_REGIMES = {"R25", "R26", "R27", "R28", "R29"}
DEFENSIVE_REGIMES = {"R09", "R10", "R23", "R24", "R30", "R38", "R39", "R40", "R50"}


def _parse_csv(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    return [item.strip().upper() for item in str(value).split(",") if item.strip()]


def _parse_float_list(value: Any, fallback: list[float]) -> list[float]:
    if value is None or value == "":
        return fallback
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value).split(",")
    parsed = []
    for item in raw:
        try:
            parsed.append(float(item))
        except (TypeError, ValueError):
            continue
    return parsed or fallback


def _month_windows(request: dict[str, Any]) -> list[dict[str, str]]:
    end_raw = request.get("end_date") or datetime.now(timezone.utc).date().isoformat()
    end = pd.Timestamp(end_raw, tz="UTC") if pd.Timestamp(end_raw).tzinfo is None else pd.Timestamp(end_raw).tz_convert("UTC")
    months_back = max(1, min(int(request.get("months_back") or 6), 12))
    start_raw = request.get("research_start_date") or request.get("start_date")
    start = pd.Timestamp(start_raw, tz="UTC") if start_raw else end - pd.DateOffset(months=months_back)
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    start = start.normalize()
    end = end.normalize()
    if end <= start:
        end = start + pd.DateOffset(months=1)

    windows = []
    cursor = pd.Timestamp(year=start.year, month=start.month, day=1, tz="UTC")
    while cursor <= end:
        next_month = cursor + pd.DateOffset(months=1)
        win_start = max(cursor, start)
        win_end = min(next_month - pd.Timedelta(seconds=1), end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
        if win_end >= win_start:
            windows.append(
                {
                    "month": cursor.strftime("%Y-%m"),
                    "start_date": win_start.date().isoformat(),
                    "end_date": (win_end + pd.Timedelta(seconds=1)).date().isoformat(),
                }
            )
        cursor = next_month
    return windows[-months_back:]


def _regime_universe(request: dict[str, Any]) -> list[dict[str, Any]]:
    regimes = load_regimes()
    by_id = {item["regime_id"].upper(): item for item in regimes}
    requested = _parse_csv(request.get("regime_filters") or request.get("regimes"))
    single = str(request.get("regime_filter") or "").upper()
    if single and single != "ALL":
        requested = [single]
    if not requested or "ALL" in requested:
        return regimes
    return [by_id[rid] for rid in requested if rid in by_id]


def _strategies_for_regime(regime: dict[str, Any], request: dict[str, Any]) -> list[str]:
    explicit = _parse_csv(request.get("strategy_filters") or request.get("strategies"))
    single = str(request.get("strategy_filter") or "").upper()
    allowed = [str(item).upper() for item in regime.get("allowed_strategies", [])]
    if single and single != "ALL":
        explicit = [single]
    strategies = explicit if explicit and "ALL" not in explicit else allowed
    if not bool(request.get("include_no_trade_strategies", False)):
        strategies = [sid for sid in strategies if sid not in NO_TRADE_STRATEGIES]
    return [sid for sid in strategies if sid in allowed or explicit]


def _candidate_passes(row: dict[str, Any], request: dict[str, Any]) -> tuple[bool, list[str]]:
    min_trades = int(request.get("min_monthly_trades") or 1)
    min_pf = float(request.get("min_monthly_profit_factor") or 1.05)
    require_profit = bool(request.get("require_positive_monthly_profit", True))
    reasons = []
    if int(row.get("total_trades") or 0) < min_trades:
        reasons.append(f"Trade count below monthly minimum {min_trades}.")
    if float(row.get("expectancy_R") or 0) <= 0:
        reasons.append("Expectancy is not positive.")
    if float(row.get("profit_factor") or 0) < min_pf:
        reasons.append(f"Profit factor below monthly minimum {min_pf:.2f}.")
    if require_profit and float(row.get("net_profit") or 0) <= 0:
        reasons.append("Net profit is not positive for this month.")
    if str(row.get("status") or "") in {"NO_DATA", "NO_TRADES"}:
        reasons.append(f"Optimizer status is {row.get('status')}.")
    return not reasons, reasons


def _failure_bucket(reason: str, regime_id: str) -> str:
    text = reason.lower()
    if "no candles" in text or "no data" in text:
        return "data_not_found"
    if "trade count" in text or "no_trades" in text:
        return "insufficient_trades"
    if "spread" in text:
        return "spread_failure"
    if "slippage" in text:
        return "slippage_failure"
    if "stop" in text or "bid/ask" in text:
        return "bid_ask_or_stop_failure"
    if "liquidity" in text or "rollover" in text:
        return "liquidity_failure"
    if "mtf" in text or "multi-timeframe" in text or "conflict" in text:
        return "multi_timeframe_sync_failure"
    if regime_id in MACRO_REGIMES and "macro" in text:
        return "macro_evidence_failure"
    if regime_id in DEFENSIVE_REGIMES:
        return "defensive_or_no_trade_regime"
    if "expectancy" in text or "profit" in text or "factor" in text:
        return "no_positive_edge"
    return "research_gate_failure"


def _monthly_optimizer_payload(
    base: dict[str, Any],
    *,
    window: dict[str, str],
    regime: dict[str, Any],
    strategies: list[str],
    request: dict[str, Any],
) -> dict[str, Any]:
    payload = deepcopy(base)
    payload["start_date"] = window["start_date"]
    payload["end_date"] = window["end_date"]
    payload["regime_filter"] = regime["regime_id"]
    payload["strategy_filter"] = "ALL"
    payload["use_feature_cache"] = bool(request.get("use_feature_cache", True))
    payload["max_combinations"] = int(request.get("max_combinations_per_regime_month") or 24)
    payload["min_trades"] = int(request.get("min_monthly_trades") or 1)
    payload["min_profit_factor"] = float(request.get("min_monthly_profit_factor") or 1.05)
    payload["max_drawdown_r"] = float(request.get("max_monthly_drawdown_r") or 8)
    payload["validate_top_n"] = 0
    payload["persist_validated_candidates"] = False
    strategy_controls = dict(payload.get("strategy_controls") or {})
    strategy_controls.setdefault("min_effective_stop_mode", request.get("min_effective_stop_mode", "widen"))
    payload["strategy_controls"] = strategy_controls

    base_grid = dict(request.get("grid") or {})
    payload["grid"] = {
        "regime_filters": [regime["regime_id"]],
        "strategy_filters": strategies,
        "rr_values": base_grid.get("rr_values") or _parse_float_list(request.get("rr_values"), [float(base.get("rr") or 2.0)]),
        "min_alpha_scores": base_grid.get("min_alpha_scores") or _parse_float_list(request.get("min_alpha_scores"), [float((base.get("filters") or {}).get("min_alpha_score") or 7)]),
        "max_spread_percentiles": base_grid.get("max_spread_percentiles") or _parse_float_list(request.get("max_spread_percentiles"), [65.0, 70.0]),
        "killzone_modes": base_grid.get("killzone_modes") or [str((base.get("filters") or {}).get("killzone_mode") or "hard_filter")],
        "alpha_modes": base_grid.get("alpha_modes") or [str((base.get("filters") or {}).get("alpha_mode") or "hard_minimum")],
        "spread_filter_modes": base_grid.get("spread_filter_modes") or [str((base.get("filters") or {}).get("spread_filter_mode") or "hard_filter")],
        "pattern_score_modes": base_grid.get("pattern_score_modes") or ["score_only", "hard_minimum"],
        "min_pattern_scores": base_grid.get("min_pattern_scores") or _parse_float_list(request.get("min_pattern_scores"), [0.0, 2.0]),
        "calibration_profiles": base_grid.get("calibration_profiles") or _parse_csv(request.get("calibration_profiles") or "balanced,conservative,funded_style"),
        "stop_atr_values": base_grid.get("stop_atr_values") or _parse_float_list(request.get("stop_atr_grid"), [0.25, 0.35, 0.50, 0.75, 1.00, 1.25]),
        "stop_override_modes": base_grid.get("stop_override_modes") or [str(request.get("stop_override_mode") or "widen_only")],
        "min_effective_stop_spread_mult_values": base_grid.get("min_effective_stop_spread_mult_values") or _parse_float_list(request.get("min_effective_stop_spread_mult"), [10.0]),
        "use_symbol_session_stop_profile_values": base_grid.get("use_symbol_session_stop_profile_values") or [bool(request.get("use_symbol_session_stop_profile", True))],
    }
    for key, value in base_grid.items():
        payload["grid"].setdefault(key, value)
    return payload


def run_monthly_regime_research(request: dict[str, Any]) -> dict[str, Any]:
    """Run a controlled month-by-month regime/strategy sweep and persist only passing candidates at the API layer."""
    base = deepcopy(request)
    windows = _month_windows(request)
    regimes = _regime_universe(request)
    strategies_by_id = {item["strategy_id"]: item for item in load_strategies()}
    symbol = str(request.get("symbol") or "EURUSD").upper()
    timeframe = str(request.get("timeframe") or "M15").upper()
    warnings: list[str] = [
        "This sweep does not force profitability. It records profitable candidates and keeps failed months visible to avoid curve-fitting blindness.",
        "Passing candidates still need OOS, walk-forward, Monte Carlo, and MT5 real-tick validation before semi-manual use.",
    ]

    month_summaries: list[dict[str, Any]] = []
    worked_candidates: list[dict[str, Any]] = []
    failed_regimes: list[dict[str, Any]] = []
    optimizer_runs: list[dict[str, Any]] = []
    failure_counter: Counter[str] = Counter()
    regime_month_counter: dict[str, Counter[str]] = defaultdict(Counter)

    for window in windows:
        candles = load_candles(
            symbol,
            timeframe,
            window["start_date"],
            window["end_date"],
            data_source=(request.get("data_source_controls") or {}).get("data_source"),
        )
        if candles.empty:
            reason = f"No candles found for {symbol} {timeframe} during {window['month']}."
            month_summaries.append({**window, "status": "NO_DATA", "candles": 0, "worked_candidates": 0, "failed_regimes": len(regimes), "reason": reason})
            failure_counter["data_not_found"] += len(regimes)
            for regime in regimes:
                failed_regimes.append({**window, "regime_id": regime["regime_id"], "regime_name": regime["regime_name"], "status": "NO_DATA", "reason": reason, "failure_bucket": "data_not_found"})
            continue

        month_worked = 0
        month_failed = 0
        for regime in regimes:
            regime_id = regime["regime_id"]
            strategies = _strategies_for_regime(regime, request)
            if not strategies:
                reason = "No tradable strategy mapped after excluding no-trade/watchlist strategies."
                failed_regimes.append({**window, "regime_id": regime_id, "regime_name": regime["regime_name"], "status": "NON_TRADABLE_REFERENCE", "reason": reason, "failure_bucket": "defensive_or_no_trade_regime"})
                failure_counter["defensive_or_no_trade_regime"] += 1
                month_failed += 1
                regime_month_counter[regime_id]["failed"] += 1
                continue

            payload = _monthly_optimizer_payload(base, window=window, regime=regime, strategies=strategies, request=request)
            try:
                optimizer = run_optimizer_grid(payload)
            except ValueError as exc:
                reason = str(exc)
                bucket = _failure_bucket(reason, regime_id)
                failed_regimes.append({**window, "regime_id": regime_id, "regime_name": regime["regime_name"], "status": "ERROR", "reason": reason, "failure_bucket": bucket})
                failure_counter[bucket] += 1
                month_failed += 1
                regime_month_counter[regime_id]["failed"] += 1
                continue

            top_rows = optimizer.get("results", [])[: int(request.get("top_candidates_per_regime_month") or 3)]
            optimizer_runs.append(
                {
                    "month": window["month"],
                    "regime_id": regime_id,
                    "regime_name": regime["regime_name"],
                    "strategies": strategies,
                    "summary": optimizer.get("summary", {}),
                    "top_rows": top_rows,
                    "warnings": optimizer.get("warnings", []),
                }
            )
            passed_rows = []
            row_failure_reasons: list[str] = []
            for row in top_rows:
                passed, reasons = _candidate_passes(row, request)
                if passed:
                    strategy_id = str(row.get("strategy_filter") or "")
                    passed_rows.append(
                        {
                            **window,
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "regime_id": regime_id,
                            "regime_name": regime["regime_name"],
                            "strategy_id": strategy_id,
                            "strategy_name": strategies_by_id.get(strategy_id, {}).get("strategy_name", strategy_id),
                            "status": "WORKED_IN_MONTH",
                            "optimizer_status": row.get("status"),
                            "rank": row.get("rank"),
                            "total_trades": row.get("total_trades"),
                            "win_rate": row.get("win_rate"),
                            "profit_factor": row.get("profit_factor"),
                            "expectancy_R": row.get("expectancy_R"),
                            "max_drawdown_R": row.get("max_drawdown_R"),
                            "net_profit": row.get("net_profit"),
                            "roi_percent": row.get("roi_percent"),
                            "optimizer_score": row.get("optimizer_score"),
                            "settings": row.get("parameters", {}),
                            "pattern_mode": row.get("pattern_score_mode"),
                            "min_pattern_score": row.get("min_pattern_score"),
                            "stop_atr": row.get("stop_atr"),
                            "min_effective_stop_spread_mult": row.get("min_effective_stop_spread_mult"),
                            "calibration_profile": row.get("calibration_profile"),
                            "reasons": row.get("reasons", []),
                        }
                    )
                else:
                    row_failure_reasons.extend(reasons or row.get("reasons") or [])
            if passed_rows:
                worked_candidates.extend(passed_rows)
                month_worked += len(passed_rows)
                regime_month_counter[regime_id]["worked"] += 1
            else:
                reason = "; ".join(row_failure_reasons[:3]) or "No optimizer candidate passed monthly profitability and sample gates."
                bucket = _failure_bucket(reason, regime_id)
                failed_regimes.append({**window, "regime_id": regime_id, "regime_name": regime["regime_name"], "status": "NO_WORKING_CANDIDATE", "reason": reason, "failure_bucket": bucket})
                failure_counter[bucket] += 1
                month_failed += 1
                regime_month_counter[regime_id]["failed"] += 1

        month_summaries.append(
            {
                **window,
                "status": "COMPLETE",
                "candles": int(len(candles)),
                "worked_candidates": month_worked,
                "failed_regimes": month_failed,
                "regimes_tested": len(regimes),
            }
        )

    regime_robustness = []
    for regime in regimes:
        counts = regime_month_counter.get(regime["regime_id"], Counter())
        tested = counts.get("worked", 0) + counts.get("failed", 0)
        regime_robustness.append(
            {
                "regime_id": regime["regime_id"],
                "regime_name": regime["regime_name"],
                "months_with_candidate": counts.get("worked", 0),
                "months_failed": counts.get("failed", 0),
                "tested_months": tested,
                "monthly_pass_rate": round(counts.get("worked", 0) / tested, 4) if tested else 0.0,
            }
        )
    regime_robustness.sort(key=lambda row: (row["monthly_pass_rate"], row["months_with_candidate"]), reverse=True)

    result = {
        "validation_run_id": None,
        "validation_saved": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "status": "CANDIDATES_FOUND" if worked_candidates else "NO_WORKING_CANDIDATES",
            "symbol": symbol,
            "timeframe": timeframe,
            "months_tested": len(windows),
            "regimes_tested": len(regimes),
            "optimizer_runs": len(optimizer_runs),
            "worked_candidates": len(worked_candidates),
            "failed_regime_months": len(failed_regimes),
            "saved_policy": "Save only working candidates in this research result." if bool(request.get("save_only_working", True)) else "Full result retained in validation run.",
            "best_month": max(worked_candidates, key=lambda row: float(row.get("net_profit") or 0), default={}).get("month"),
            "best_regime": max(worked_candidates, key=lambda row: float(row.get("expectancy_R") or 0), default={}).get("regime_id"),
            "best_strategy": max(worked_candidates, key=lambda row: float(row.get("expectancy_R") or 0), default={}).get("strategy_id"),
            "best_net_profit": max([float(row.get("net_profit") or 0) for row in worked_candidates], default=0.0),
        },
        "month_summaries": month_summaries,
        "worked_candidates": worked_candidates,
        "failed_regimes": failed_regimes,
        "failure_diagnostics": [{"failure_bucket": key, "count": value} for key, value in failure_counter.most_common()],
        "regime_robustness": regime_robustness,
        "optimizer_runs": optimizer_runs if not bool(request.get("save_only_working", True)) else [],
        "warnings": warnings,
        "request": {
            "symbol": symbol,
            "timeframe": timeframe,
            "months_back": request.get("months_back", 6),
            "regime_filters": request.get("regime_filters", request.get("regime_filter", "ALL")),
            "stop_atr_grid": _parse_float_list(request.get("stop_atr_grid"), [0.25, 0.35, 0.50, 0.75, 1.00, 1.25]),
            "min_effective_stop_spread_mult": _parse_float_list(request.get("min_effective_stop_spread_mult"), [10.0]),
            "max_combinations_per_regime_month": int(request.get("max_combinations_per_regime_month") or 24),
        },
    }
    return result
