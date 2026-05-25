from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.backtest_engine import run_backtest
from backend.database import save_ab_experiment


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("summary", {})
    total_r = round(sum(float(trade.get("result_R") or 0) for trade in result.get("trades", [])), 4)
    return {
        "run_id": result.get("run_id"),
        "total_trades": int(summary.get("total_trades") or 0),
        "win_rate": float(summary.get("win_rate") or 0),
        "profit_factor": float(summary.get("profit_factor") or 0),
        "expectancy_R": float(summary.get("expectancy_R") or 0),
        "average_R": float(summary.get("average_R") or 0),
        "average_win_R": float(summary.get("average_win_R") or 0),
        "average_loss_R": float(summary.get("average_loss_R") or 0),
        "break_even_win_rate": summary.get("break_even_win_rate"),
        "max_drawdown_R": float(summary.get("max_drawdown_R") or 0),
        "max_losing_streak": int(summary.get("max_losing_streak") or 0),
        "net_profit": float(summary.get("net_profit") or 0),
        "roi_percent": float(summary.get("roi_percent") or 0),
        "total_R": total_r,
        "skipped_setups": int(summary.get("skipped_setups") or 0),
        "best_session": summary.get("best_session"),
        "worst_session": summary.get("worst_session"),
    }


def _delta(variant: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "delta_trades": variant["total_trades"] - baseline["total_trades"],
        "delta_win_rate": round(variant["win_rate"] - baseline["win_rate"], 4),
        "delta_profit_factor": round(variant["profit_factor"] - baseline["profit_factor"], 4),
        "delta_expectancy_R": round(variant["expectancy_R"] - baseline["expectancy_R"], 4),
        "delta_average_R": round(variant["average_R"] - baseline["average_R"], 4),
        "delta_max_drawdown_R": round(variant["max_drawdown_R"] - baseline["max_drawdown_R"], 4),
        "delta_net_profit": round(variant["net_profit"] - baseline["net_profit"], 2),
        "delta_total_R": round(variant["total_R"] - baseline["total_R"], 4),
    }


def _decision(metrics: dict[str, Any], deltas: dict[str, Any], rules: dict[str, Any]) -> tuple[str, list[str]]:
    min_trades = int(rules.get("min_trades") or 30)
    min_pf = float(rules.get("min_profit_factor") or 1.2)
    min_exp = float(rules.get("min_expectancy_R") or 0.0)
    min_exp_improvement = float(rules.get("min_expectancy_improvement_R") or 0.02)
    max_dd = float(rules.get("max_drawdown_R") or 12.0)
    max_dd_worsening = float(rules.get("max_drawdown_worsening_R") or 2.0)

    reasons: list[str] = []
    if metrics["total_trades"] < min_trades:
        reasons.append(f"Trade count {metrics['total_trades']} is below A/B minimum {min_trades}.")
    if metrics["profit_factor"] < min_pf:
        reasons.append(f"Profit factor {metrics['profit_factor']:.2f} is below {min_pf:.2f}.")
    if metrics["expectancy_R"] < min_exp:
        reasons.append(f"Expectancy {metrics['expectancy_R']:.3f}R is below {min_exp:.3f}R.")
    if abs(metrics["max_drawdown_R"]) > max_dd:
        reasons.append(f"Drawdown {metrics['max_drawdown_R']:.2f}R exceeds {max_dd:.2f}R.")
    if deltas["delta_expectancy_R"] < min_exp_improvement:
        reasons.append(f"Expectancy improvement {deltas['delta_expectancy_R']:.3f}R is below {min_exp_improvement:.3f}R.")
    if deltas["delta_max_drawdown_R"] < -max_dd_worsening:
        reasons.append(f"Drawdown worsened by {abs(deltas['delta_max_drawdown_R']):.2f}R, above {max_dd_worsening:.2f}R tolerance.")

    if not reasons:
        return "ACCEPT_VARIANT", ["Variant improves baseline and passes the A/B decision gates."]
    if metrics["total_trades"] >= max(10, min_trades // 2) and metrics["expectancy_R"] > 0 and deltas["delta_expectancy_R"] > 0:
        return "WATCHLIST_VARIANT", reasons
    if metrics["total_trades"] == 0:
        return "NO_TRADES", reasons
    return "REJECT_VARIANT", reasons


def _run_arm(label: str, payload: dict[str, Any]) -> dict[str, Any]:
    final_payload = deepcopy(payload)
    final_payload["use_feature_cache"] = bool(final_payload.get("use_feature_cache", True))
    result = run_backtest(final_payload, persist=False)
    return {
        "label": label,
        "payload": final_payload,
        "metrics": _summary(result),
        "data_health": result.get("data_health", {}),
        "feature_summary": result.get("feature_summary", {}),
        "regime_confidence": result.get("regime_confidence", []),
        "warnings": result.get("warnings", []),
    }


def run_ab_experiment(request: dict[str, Any]) -> dict[str, Any]:
    base_payload = deepcopy(request.get("base_payload") or {})
    if not base_payload:
        raise ValueError("A/B experiment needs base_payload.")
    variants = request.get("variants") or []
    if not variants:
        raise ValueError("A/B experiment needs at least one variant.")

    experiment_id = f"ab_{uuid4().hex[:12]}"
    created_at = datetime.now(timezone.utc).isoformat()
    baseline_label = str(request.get("baseline_label") or "Baseline")
    rules = request.get("decision_rules") or {}
    warnings: list[str] = []

    baseline = _run_arm(baseline_label, base_payload)
    baseline_metrics = baseline["metrics"]
    comparison: list[dict[str, Any]] = []
    variant_results: list[dict[str, Any]] = []

    if baseline_metrics["total_trades"] == 0:
        warnings.append("Baseline produced no trades. Variant deltas are still calculated, but the experiment is mainly a no-trade diagnosis.")

    for index, variant in enumerate(variants, start=1):
        label = str(variant.get("label") or f"Variant {index}")
        changes = variant.get("changes") or variant.get("overrides") or {}
        payload = _deep_merge(base_payload, changes)
        try:
            arm = _run_arm(label, payload)
            metrics = arm["metrics"]
            deltas = _delta(metrics, baseline_metrics)
            status, reasons = _decision(metrics, deltas, rules)
            arm.update(
                {
                    "changes": changes,
                    "status": status,
                    "reasons": reasons,
                    "delta_vs_baseline": deltas,
                }
            )
            comparison.append(
                {
                    "rank": None,
                    "label": label,
                    "status": status,
                    **metrics,
                    **deltas,
                    "reasons": reasons,
                    "changes": changes,
                }
            )
            variant_results.append(arm)
        except ValueError as exc:
            row = {
                "rank": None,
                "label": label,
                "status": "NO_DATA",
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
                "delta_trades": -baseline_metrics["total_trades"],
                "delta_win_rate": -baseline_metrics["win_rate"],
                "delta_profit_factor": -baseline_metrics["profit_factor"],
                "delta_expectancy_R": -baseline_metrics["expectancy_R"],
                "delta_average_R": -baseline_metrics["average_R"],
                "delta_max_drawdown_R": -baseline_metrics["max_drawdown_R"],
                "delta_net_profit": -baseline_metrics["net_profit"],
                "delta_total_R": -baseline_metrics["total_R"],
                "reasons": [str(exc)],
                "changes": changes,
            }
            comparison.append(row)
            variant_results.append({"label": label, "payload": payload, "changes": changes, "status": "NO_DATA", "reasons": [str(exc)], "metrics": row})

    comparison.sort(
        key=lambda row: (
            row["status"] == "ACCEPT_VARIANT",
            row["status"] == "WATCHLIST_VARIANT",
            row.get("delta_expectancy_R", 0),
            row.get("profit_factor", 0),
        ),
        reverse=True,
    )
    for rank, row in enumerate(comparison, start=1):
        row["rank"] = rank

    accepted = [row for row in comparison if row["status"] == "ACCEPT_VARIANT"]
    watchlist = [row for row in comparison if row["status"] == "WATCHLIST_VARIANT"]
    best = comparison[0] if comparison else {}
    status = "NO_VARIANT_ACCEPTED"
    if accepted:
        status = "VARIANT_ACCEPTED"
    elif watchlist:
        status = "WATCHLIST_ONLY"
    elif baseline_metrics["total_trades"] == 0:
        status = "NO_BASELINE_TRADES"

    if accepted:
        warnings.append("A/B acceptance is a research gate only. Confirm with OOS, walk-forward, Monte Carlo, and MT5 real-tick comparison.")
    elif watchlist:
        warnings.append("Only watchlist variants found. Increase sample size or run OOS before promoting a variant.")
    else:
        warnings.append("No variant beat the baseline under the current A/B decision gates.")

    result = {
        "experiment_id": experiment_id,
        "created_at": created_at,
        "summary": {
            "status": status,
            "baseline_label": baseline_label,
            "baseline_trades": baseline_metrics["total_trades"],
            "variants_tested": len(variants),
            "accepted_variants": len(accepted),
            "watchlist_variants": len(watchlist),
            "best_variant_label": best.get("label"),
            "best_delta_expectancy_R": best.get("delta_expectancy_R"),
            "best_delta_profit_factor": best.get("delta_profit_factor"),
            "decision_rules": rules,
        },
        "baseline": baseline,
        "variants": variant_results,
        "comparison": comparison,
        "warnings": warnings,
        "request": request,
    }
    if request.get("persist", True):
        save_ab_experiment(result)
    return result

