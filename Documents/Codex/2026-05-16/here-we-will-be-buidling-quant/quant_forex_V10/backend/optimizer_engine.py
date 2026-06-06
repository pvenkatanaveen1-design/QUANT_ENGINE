from __future__ import annotations

from copy import deepcopy
from itertools import product
import math
from typing import Any

from backend.anti_overfit_engine import anti_overfit_gate, multiple_test_penalty
from backend.backtest_engine import run_backtest
from backend.monte_carlo_engine import run_monte_carlo
from backend.out_of_sample_engine import run_out_of_sample
from backend.walk_forward_engine import run_walk_forward


CALIBRATION_THRESHOLD_FIELDS = {
    "adx_min_values": "adx_min",
    "adx_max_values": "adx_max",
    "er_min_values": "er_min",
    "er_max_values": "er_max",
    "atr_percentile_min_values": "atr_percentile_min",
    "atr_percentile_max_values": "atr_percentile_max",
    "candle_range_atr_min_values": "candle_range_atr_min",
    "candle_range_atr_max_values": "candle_range_atr_max",
    "upper_wick_min_values": "upper_wick_min",
    "lower_wick_min_values": "lower_wick_min",
    "vwap_distance_atr_min_values": "vwap_distance_atr_min",
    "macro_confidence_min_values": "macro_confidence_min",
    "confidence_min_values": "confidence_min",
    "max_spread_percentile_values": "max_spread_percentile",
    "range_edge_tolerance_values": "range_edge_tolerance_atr",
}


def _as_list(value: Any, fallback: list[Any]) -> list[Any]:
    if value is None:
        return fallback
    if isinstance(value, list):
        return value or fallback
    return [value]


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("summary", {})
    total_r = round(sum(float(trade.get("result_R") or 0) for trade in result.get("trades", [])), 4)
    return {
        "total_trades": int(summary.get("total_trades") or 0),
        "win_rate": float(summary.get("win_rate") or 0),
        "profit_factor": float(summary.get("profit_factor") or 0),
        "expectancy_R": float(summary.get("expectancy_R") or 0),
        "average_R": float(summary.get("average_R") or 0),
        "max_drawdown_R": float(summary.get("max_drawdown_R") or 0),
        "max_losing_streak": int(summary.get("max_losing_streak") or 0),
        "net_profit": float(summary.get("net_profit") or 0),
        "roi_percent": float(summary.get("roi_percent") or 0),
        "total_R": total_r,
        "skipped_setups": int(summary.get("skipped_setups") or 0),
        "best_session": summary.get("best_session"),
        "worst_session": summary.get("worst_session"),
    }


def _status(metrics: dict[str, Any], min_trades: int, min_profit_factor: float, max_drawdown_r: float, trial_penalty: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    trial_penalty = trial_penalty or {}
    adjusted_min_trades = int(min_trades) + int(trial_penalty.get("extra_min_trades") or 0)
    adjusted_min_pf = float(min_profit_factor) + float(trial_penalty.get("extra_profit_factor") or 0)
    reasons: list[str] = []
    if metrics["total_trades"] < adjusted_min_trades:
        reasons.append(f"Trade count {metrics['total_trades']} is below anti-overfit adjusted minimum {adjusted_min_trades}.")
    if metrics["expectancy_R"] <= 0:
        reasons.append("Expectancy is not positive.")
    if metrics["profit_factor"] < adjusted_min_pf:
        reasons.append(f"Profit factor is below anti-overfit adjusted minimum {adjusted_min_pf:.2f}.")
    if abs(metrics["max_drawdown_R"]) > max_drawdown_r:
        reasons.append(f"Drawdown {metrics['max_drawdown_R']}R exceeds {max_drawdown_r}R limit.")
    if not reasons:
        detail = "Meets optimizer trade count, expectancy, profit-factor, drawdown, and multiple-test penalty rules."
        if trial_penalty.get("level") not in {None, "LOW"}:
            detail += f" Penalty level: {trial_penalty.get('level')}."
        return "APPROVED_CANDIDATE", [detail]
    if metrics["total_trades"] >= max(10, adjusted_min_trades // 2) and metrics["expectancy_R"] > 0 and metrics["profit_factor"] >= 1:
        return "WATCHLIST", reasons
    if metrics["total_trades"] == 0:
        return "NO_TRADES", reasons
    return "REJECTED", reasons


def _rank_score(metrics: dict[str, Any], min_trades: int) -> float:
    trade_quality = min(metrics["total_trades"] / max(min_trades, 1), 1.5)
    score = 0.0
    score += metrics["expectancy_R"] * 100
    score += min(metrics["profit_factor"], 3.0) * 12
    score += metrics["win_rate"] * 10
    score += metrics["total_R"] * 0.25
    score -= abs(metrics["max_drawdown_R"]) * 2.0
    score -= metrics["max_losing_streak"] * 0.35
    score += trade_quality * 8
    if metrics["total_trades"] < min_trades:
        score -= (min_trades - metrics["total_trades"]) * 0.5
    return round(score, 4)


def _edge_statistics(result: dict[str, Any], rr: float) -> dict[str, Any]:
    trades = result.get("trades") or []
    r_values = [float(trade.get("result_R") or 0.0) for trade in trades]
    n = len(r_values)
    wins = sum(1 for value in r_values if value > 0)
    if n == 0:
        return {
            "edge_t_stat": 0.0,
            "edge_p_value_approx": 1.0,
            "expectancy_standard_error_R": None,
            "win_rate_wilson_lower_95": 0.0,
            "break_even_win_rate": round(1 / (float(rr or 1) + 1), 4),
            "statistical_edge": "NO_TRADES",
        }
    mean = sum(r_values) / n
    if n > 1:
        variance = sum((value - mean) ** 2 for value in r_values) / (n - 1)
        std = math.sqrt(max(variance, 0.0))
        se = std / math.sqrt(n) if std > 0 else 0.0
    else:
        std = 0.0
        se = 0.0
    t_stat = mean / se if se > 0 else (99.0 if mean > 0 else 0.0)
    p_value = 0.5 * math.erfc(t_stat / math.sqrt(2)) if t_stat > -10 else 1.0

    z = 1.96
    p_hat = wins / n
    denominator = 1 + (z**2 / n)
    centre = p_hat + (z**2 / (2 * n))
    margin = z * math.sqrt((p_hat * (1 - p_hat) / n) + (z**2 / (4 * n**2)))
    wilson_lower = max(0.0, (centre - margin) / denominator)
    break_even = 1 / (float(rr or 1) + 1)

    if n < 30:
        label = "LOW_SAMPLE"
    elif mean <= 0:
        label = "NO_EDGE"
    elif p_value <= 0.05 and wilson_lower > break_even:
        label = "STATISTICALLY_STRONG"
    elif p_value <= 0.20:
        label = "PROMISING"
    else:
        label = "WEAK"
    return {
        "edge_t_stat": round(t_stat, 4),
        "edge_p_value_approx": round(max(0.0, min(1.0, p_value)), 4),
        "expectancy_standard_error_R": round(se, 4) if se else 0.0,
        "win_rate_wilson_lower_95": round(wilson_lower, 4),
        "break_even_win_rate": round(break_even, 4),
        "statistical_edge": label,
    }


def _build_combinations(request: dict[str, Any]) -> list[dict[str, Any]]:
    grid = request.get("grid") or {}
    regime_values = _as_list(grid.get("regime_filters"), [request.get("regime_filter", "ALL")])
    strategy_values = _as_list(grid.get("strategy_filters"), [request.get("strategy_filter", "ALL")])
    rr_values = _as_list(grid.get("rr_values"), [request.get("rr", 2.0)])
    alpha_values = _as_list(grid.get("min_alpha_scores"), [request.get("filters", {}).get("min_alpha_score", 5)])
    spread_values = _as_list(grid.get("max_spread_percentiles"), [request.get("filters", {}).get("max_spread_percentile", 70)])
    killzone_modes = _as_list(grid.get("killzone_modes"), [request.get("filters", {}).get("killzone_mode", request.get("killzone_mode", "score_only"))])
    alpha_modes = _as_list(grid.get("alpha_modes"), [request.get("filters", {}).get("alpha_mode", request.get("alpha_mode", "hard_minimum"))])
    spread_modes = _as_list(grid.get("spread_filter_modes"), [request.get("filters", {}).get("spread_filter_mode", request.get("spread_filter_mode", "score_only"))])
    pattern_modes = _as_list(grid.get("pattern_score_modes"), [request.get("pattern_engine", {}).get("pattern_score_mode", "score_only")])
    pattern_scores = _as_list(grid.get("min_pattern_scores"), [request.get("pattern_engine", {}).get("min_pattern_score", 2)])
    calibration_profiles = _as_list(grid.get("calibration_profiles"), [request.get("calibration", {}).get("profile", "balanced")])
    strategy_controls = request.get("strategy_controls") if isinstance(request.get("strategy_controls"), dict) else {}
    stop_atr_values = _as_list(grid.get("stop_atr_values"), [strategy_controls.get("stop_atr_override")])
    stop_override_modes = _as_list(grid.get("stop_override_modes"), [strategy_controls.get("stop_override_mode", "off")])
    min_stop_spread_mult_values = _as_list(grid.get("min_effective_stop_spread_mult_values"), [strategy_controls.get("min_effective_stop_spread_mult")])
    stop_profile_modes = _as_list(grid.get("use_symbol_session_stop_profile_values"), [strategy_controls.get("use_symbol_session_stop_profile", False)])

    threshold_keys = [key for key in CALIBRATION_THRESHOLD_FIELDS if grid.get(key) not in (None, [], "")]
    threshold_values = [_as_list(grid.get(key), [None]) for key in threshold_keys] or [[None]]

    combos = []
    for regime, strategy, rr, alpha, spread, kill_mode, alpha_mode, spread_mode, pattern_mode, pattern_score, calibration_profile, stop_atr, stop_override_mode, min_stop_mult, use_stop_profile, threshold_tuple in product(
        regime_values,
        strategy_values,
        rr_values,
        alpha_values,
        spread_values,
        killzone_modes,
        alpha_modes,
        spread_modes,
        pattern_modes,
        pattern_scores,
        calibration_profiles,
        stop_atr_values,
        stop_override_modes,
        min_stop_spread_mult_values,
        stop_profile_modes,
        product(*threshold_values),
    ):
        if not isinstance(threshold_tuple, tuple):
            threshold_tuple = (threshold_tuple,)
        calibration_overrides = {}
        if str(regime).upper() != "ALL":
            values = {
                "min_alpha_score": float(alpha),
                "max_spread_percentile": float(spread),
            }
            values.update(
                {
                    CALIBRATION_THRESHOLD_FIELDS[key]: float(value)
                    for key, value in zip(threshold_keys, threshold_tuple)
                    if value not in {None, ""}
                }
            )
            calibration_overrides[str(regime).upper()] = values
        combos.append(
            {
                "regime_filter": regime,
                "strategy_filter": strategy,
                "rr": float(rr),
                "min_alpha_score": float(alpha),
                "max_spread_percentile": float(spread),
                "killzone_mode": str(kill_mode),
                "alpha_mode": str(alpha_mode),
                "spread_filter_mode": str(spread_mode),
                "pattern_score_mode": str(pattern_mode),
                "min_pattern_score": float(pattern_score),
                "calibration_profile": str(calibration_profile),
                "calibration_overrides": calibration_overrides,
                "stop_atr": float(stop_atr) if stop_atr not in {None, ""} else None,
                "stop_override_mode": str(stop_override_mode or "off"),
                "min_effective_stop_spread_mult": float(min_stop_mult) if min_stop_mult not in {None, ""} else None,
                "use_symbol_session_stop_profile": bool(use_stop_profile),
            }
        )
    return combos


def _payload_for_combo(request: dict[str, Any], combo: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(request)
    for key in ["grid", "max_combinations", "min_trades", "min_profit_factor", "max_drawdown_r"]:
        payload.pop(key, None)
    payload["regime_filter"] = combo["regime_filter"]
    payload["strategy_filter"] = combo["strategy_filter"]
    payload["rr"] = combo["rr"]
    payload["killzone_mode"] = combo["killzone_mode"]
    payload["alpha_mode"] = combo["alpha_mode"]
    payload["spread_filter_mode"] = combo["spread_filter_mode"]
    payload.setdefault("filters", {})
    payload["filters"]["killzone_mode"] = combo["killzone_mode"]
    payload["filters"]["alpha_mode"] = combo["alpha_mode"]
    payload["filters"]["spread_filter_mode"] = combo["spread_filter_mode"]
    payload["filters"]["min_alpha_score"] = combo["min_alpha_score"]
    payload["filters"]["max_spread_percentile"] = combo["max_spread_percentile"]
    payload.setdefault("pattern_engine", {})
    payload["pattern_engine"]["pattern_score_mode"] = combo["pattern_score_mode"]
    payload["pattern_engine"]["min_pattern_score"] = combo["min_pattern_score"]
    payload["calibration"] = {
        "profile": combo.get("calibration_profile", "balanced"),
        "overrides": combo.get("calibration_overrides", {}),
    }
    payload.setdefault("strategy_controls", {})
    payload["strategy_controls"]["use_symbol_session_stop_profile"] = bool(combo.get("use_symbol_session_stop_profile"))
    if combo.get("stop_atr") is not None:
        payload["strategy_controls"]["stop_atr_override"] = combo["stop_atr"]
        payload["strategy_controls"]["stop_override_mode"] = combo.get("stop_override_mode") or "widen_only"
    if combo.get("min_effective_stop_spread_mult") is not None:
        payload["strategy_controls"]["min_effective_stop_spread_mult"] = combo["min_effective_stop_spread_mult"]
        payload["strategy_controls"].setdefault("min_effective_stop_mode", "widen")
    payload["use_feature_cache"] = bool(request.get("use_feature_cache", request.get("feature_cache", True)))
    return payload


def _merge_validation_payload(payload: dict[str, Any], settings: dict[str, Any], keys_to_drop: list[str]) -> dict[str, Any]:
    merged = {**deepcopy(payload), **deepcopy(settings)}
    for key in keys_to_drop:
        if settings.get(key) in {None, ""}:
            merged.pop(key, None)
    return merged


def _validate_candidate(
    *,
    request: dict[str, Any],
    combo: dict[str, Any],
    optimizer_summary: dict[str, Any],
    validation_settings: dict[str, Any],
) -> dict[str, Any]:
    payload = _payload_for_combo(request, combo)
    backtest = run_backtest(payload, persist=False)
    oos_settings = validation_settings.get("out_of_sample") if isinstance(validation_settings.get("out_of_sample"), dict) else {}
    wf_settings = validation_settings.get("walk_forward") if isinstance(validation_settings.get("walk_forward"), dict) else {}
    mc_settings = validation_settings.get("monte_carlo") if isinstance(validation_settings.get("monte_carlo"), dict) else {}
    thresholds = validation_settings.get("thresholds") if isinstance(validation_settings.get("thresholds"), dict) else {}

    oos = run_out_of_sample(_merge_validation_payload(payload, oos_settings, ["split_date"]))
    walk_forward = run_walk_forward(_merge_validation_payload(payload, wf_settings, []))
    monte_carlo = run_monte_carlo(_merge_validation_payload(payload, mc_settings, []))
    gate = anti_overfit_gate(
        backtest=backtest,
        out_of_sample=oos,
        walk_forward=walk_forward,
        monte_carlo=monte_carlo,
        optimizer={"summary": optimizer_summary},
        thresholds=thresholds,
    )

    return {
        "candidate_id": f"{combo.get('regime_filter')}_{combo.get('strategy_filter')}_{combo.get('rr')}_{combo.get('min_alpha_score')}_{combo.get('max_spread_percentile')}",
        "status": "VALIDATED_CANDIDATE" if gate.get("passed") else "VALIDATION_FAILED",
        "passed": bool(gate.get("passed")),
        "candidate": combo,
        "backtest": backtest,
        "out_of_sample": oos,
        "walk_forward": walk_forward,
        "monte_carlo": monte_carlo,
        "anti_overfit_gate": gate,
        "summary": {
            "status": "VALIDATED_CANDIDATE" if gate.get("passed") else "VALIDATION_FAILED",
            "regime_filter": combo.get("regime_filter"),
            "strategy_filter": combo.get("strategy_filter"),
            "rr": combo.get("rr"),
            "min_alpha_score": combo.get("min_alpha_score"),
            "max_spread_percentile": combo.get("max_spread_percentile"),
            "backtest_trades": backtest.get("summary", {}).get("total_trades", 0),
            "backtest_pf": backtest.get("summary", {}).get("profit_factor", 0),
            "backtest_expectancy_R": backtest.get("summary", {}).get("expectancy_R", 0),
            "oos_status": oos.get("summary", {}).get("status"),
            "oos_stable": oos.get("summary", {}).get("stable"),
            "oos_trades": oos.get("out_of_sample", {}).get("total_trades", 0),
            "oos_pf": oos.get("out_of_sample", {}).get("profit_factor", 0),
            "oos_expectancy_R": oos.get("out_of_sample", {}).get("expectancy_R", 0),
            "wf_pass_rate": walk_forward.get("summary", {}).get("pass_rate", 0),
            "wf_efficiency": walk_forward.get("summary", {}).get("average_walk_forward_efficiency"),
            "mc_status": monte_carlo.get("summary", {}).get("status"),
            "mc_loss_probability": monte_carlo.get("risk_of_ruin", {}).get("loss_probability"),
            "mc_drawdown_breach_probability": monte_carlo.get("risk_of_ruin", {}).get("drawdown_breach_probability"),
            "anti_overfit_status": gate.get("status"),
            "failed_checks": len(gate.get("failed_checks") or []),
        },
        "warnings": [
            *[str(item) for item in (oos.get("warnings") or [])],
            *[str(item) for item in (walk_forward.get("warnings") or [])],
            *[str(item) for item in (monte_carlo.get("warnings") or [])],
            *[str(item) for item in (gate.get("warnings") or [])],
        ],
        "request": payload,
    }


def _feature_cache_row(result: dict[str, Any]) -> dict[str, Any]:
    health = result.get("data_health") or {}
    cache = health.get("feature_cache") or {}
    return {
        "feature_cache_status": health.get("feature_cache_status") or cache.get("status") or "UNKNOWN",
        "feature_cache_hit": bool(health.get("feature_cache_hit") or cache.get("cache_hit")),
        "feature_cache_reason": cache.get("reason", ""),
        "feature_cache_key": cache.get("cache_key", ""),
    }


def run_optimizer_grid(request: dict[str, Any]) -> dict[str, Any]:
    max_combinations = int(request.get("max_combinations") or 50)
    min_trades = int(request.get("min_trades") or 30)
    min_profit_factor = float(request.get("min_profit_factor") or 1.2)
    max_drawdown_r = float(request.get("max_drawdown_r") or 10)
    validate_top_n = max(0, min(int(request.get("validate_top_n") or 0), 25))
    persist_validated_candidates = bool(request.get("persist_validated_candidates", True))
    validation_settings = request.get("validation") if isinstance(request.get("validation"), dict) else {}
    combinations = _build_combinations(request)
    warnings: list[str] = []
    if not combinations:
        raise ValueError("Optimizer grid produced no combinations.")
    if len(combinations) > max_combinations:
        warnings.append(f"Grid produced {len(combinations)} combinations; running first {max_combinations}. Narrow the grid for full coverage.")
        combinations = combinations[:max_combinations]
    trial_penalty = multiple_test_penalty(len(_build_combinations(request)))
    adjusted_min_trades = min_trades + int(trial_penalty.get("extra_min_trades") or 0)
    adjusted_min_pf = min_profit_factor + float(trial_penalty.get("extra_profit_factor") or 0)
    if trial_penalty["level"] != "LOW":
        warnings.append(
            f"Anti-overfit multiple-test penalty is {trial_penalty['level']}: min trades adjusted to {adjusted_min_trades}, min PF adjusted to {adjusted_min_pf:.2f}."
        )

    rows: list[dict[str, Any]] = []
    cache_hits = 0
    cache_misses = 0
    for index, combo in enumerate(combinations, start=1):
        payload = _payload_for_combo(request, combo)
        row = {"rank": None, "combo_id": index, "parameters": combo}
        try:
            result = run_backtest(payload, persist=False)
            metrics = _summary(result)
            stats = _edge_statistics(result, combo["rr"])
            cache_row = _feature_cache_row(result)
            if cache_row["feature_cache_hit"]:
                cache_hits += 1
            else:
                cache_misses += 1
            status, reasons = _status(metrics, min_trades, min_profit_factor, max_drawdown_r, trial_penalty)
            row.update(
                {
                    **combo,
                    **metrics,
                    **stats,
                    **cache_row,
                    "optimizer_score": _rank_score(metrics, min_trades),
                    "status": status,
                    "reasons": reasons,
                    "anti_overfit_penalty": trial_penalty,
                    "adjusted_min_trades": adjusted_min_trades,
                    "adjusted_min_profit_factor": round(adjusted_min_pf, 4),
                }
            )
        except ValueError as exc:
            row.update(
                {
                    **combo,
                    "total_trades": 0,
                    "win_rate": 0,
                    "profit_factor": 0,
                    "expectancy_R": 0,
                    "average_R": 0,
                    "max_drawdown_R": 0,
                    "max_losing_streak": 0,
                    "net_profit": 0,
                    "roi_percent": 0,
                    "total_R": 0,
                    "skipped_setups": 0,
                    "best_session": None,
                    "worst_session": None,
                    "feature_cache_status": "NO_DATA",
                    "feature_cache_hit": False,
                    "feature_cache_reason": "",
                    "feature_cache_key": "",
                    "optimizer_score": -9999,
                    "status": "NO_DATA",
                    "reasons": [str(exc)],
                    "anti_overfit_penalty": trial_penalty,
                    "adjusted_min_trades": adjusted_min_trades,
                    "adjusted_min_profit_factor": round(adjusted_min_pf, 4),
                }
            )
        rows.append(row)

    rows.sort(key=lambda item: item["optimizer_score"], reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank

    approved = [row for row in rows if row["status"] == "APPROVED_CANDIDATE"]
    watchlist = [row for row in rows if row["status"] == "WATCHLIST"]
    validation_results: list[dict[str, Any]] = []
    saved_validated_candidates: list[dict[str, Any]] = []
    if approved:
        warnings.append("Approved candidates are optimization candidates only. Confirm with out-of-sample, walk-forward, and MT5 real-tick testing before trusting them.")
    if not approved and watchlist:
        warnings.append("No approved candidates found; watchlist rows need out-of-sample validation and more trades.")
    if not approved and not watchlist:
        warnings.append("No viable candidates found under the current grid and thresholds.")

    optimizer_summary = {
        "combinations_requested": len(_build_combinations(request)),
        "combinations_run": len(rows),
        "approved_candidates": len(approved),
        "watchlist_candidates": len(watchlist),
        "min_trades": min_trades,
        "min_profit_factor": min_profit_factor,
        "max_drawdown_r": max_drawdown_r,
        "anti_overfit_penalty": trial_penalty,
    }
    if validate_top_n:
        validation_pool = [row for row in rows if row["status"] in {"APPROVED_CANDIDATE", "WATCHLIST"}][:validate_top_n]
        if not validation_pool:
            validation_pool = [row for row in rows if row["status"] != "NO_DATA"][:validate_top_n]
            warnings.append("Validation was requested, but no approved/watchlist rows were available. Validating the best rejected rows anyway so failure reasons are visible.")
        for row in validation_pool:
            combo = row["parameters"]
            try:
                validation = _validate_candidate(
                    request=request,
                    combo=combo,
                    optimizer_summary=optimizer_summary,
                    validation_settings=validation_settings,
                )
                validation_results.append(validation)
                summary = validation.get("summary", {})
                row.update(
                    {
                        "validation_status": validation.get("status"),
                        "oos_status": summary.get("oos_status"),
                        "oos_trades": summary.get("oos_trades"),
                        "oos_pf": summary.get("oos_pf"),
                        "oos_expectancy_R": summary.get("oos_expectancy_R"),
                        "wf_pass_rate": summary.get("wf_pass_rate"),
                        "wf_efficiency": summary.get("wf_efficiency"),
                        "mc_status": summary.get("mc_status"),
                        "mc_loss_probability": summary.get("mc_loss_probability"),
                        "mc_drawdown_breach_probability": summary.get("mc_drawdown_breach_probability"),
                        "anti_overfit_status": summary.get("anti_overfit_status"),
                        "failed_validation_checks": summary.get("failed_checks"),
                        "validation_failed_check_names": [item.get("check") for item in validation.get("anti_overfit_gate", {}).get("failed_checks", [])],
                        "validation_warnings": validation.get("warnings", [])[:5],
                    }
                )
                if validation.get("passed") and persist_validated_candidates:
                    from backend.database import save_validation_result

                    saved = save_validation_result("optimizer_validated_candidate", validation, validation.get("request", {}))
                    saved_validated_candidates.append(saved)
            except Exception as exc:
                row["validation_status"] = "VALIDATION_ERROR"
                row["validation_error"] = str(exc)
                warnings.append(f"Candidate validation failed for {row.get('regime_filter')}/{row.get('strategy_filter')}: {exc}")
        validated_count = sum(1 for result in validation_results if result.get("passed"))
        if validate_top_n and not validated_count:
            warnings.append("No optimizer candidate survived OOS + walk-forward + Monte Carlo anti-overfit validation. Keep as research-only or broaden data/sample before relaxing thresholds.")

    return {
        "summary": {
            "combinations_requested": len(_build_combinations(request)),
            "combinations_run": len(rows),
            "approved_candidates": len(approved),
            "watchlist_candidates": len(watchlist),
            "validated_candidates": sum(1 for result in validation_results if result.get("passed")),
            "validation_runs": len(validation_results),
            "saved_validated_candidates": len(saved_validated_candidates),
            "best_score": rows[0]["optimizer_score"] if rows else None,
            "best_regime": rows[0]["regime_filter"] if rows else None,
            "best_strategy": rows[0]["strategy_filter"] if rows else None,
            "min_trades": min_trades,
            "min_profit_factor": min_profit_factor,
            "max_drawdown_r": max_drawdown_r,
            "anti_overfit_penalty": trial_penalty,
            "adjusted_min_trades": adjusted_min_trades,
            "adjusted_min_profit_factor": round(adjusted_min_pf, 4),
            "feature_cache_enabled": bool(request.get("use_feature_cache", request.get("feature_cache", True))),
            "feature_cache_hits": cache_hits,
            "feature_cache_misses": cache_misses,
            "feature_cache_hit_rate": round(cache_hits / len(rows), 4) if rows else 0,
        },
        "results": rows,
        "top_candidates": rows[: min(10, len(rows))],
        "validated_candidates": validation_results,
        "saved_validated_candidates": saved_validated_candidates,
        "warnings": warnings,
        "request": {
            "symbol": request.get("symbol"),
            "timeframe": request.get("timeframe"),
            "start_date": request.get("start_date"),
            "end_date": request.get("end_date"),
            "grid": request.get("grid", {}),
        },
    }
