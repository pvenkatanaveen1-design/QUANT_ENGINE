from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable
import uuid

from backend.backtest_engine import run_backtest
from backend.final_approval_engine import final_approval_review
from backend.monte_carlo_engine import run_monte_carlo
from backend.out_of_sample_engine import run_out_of_sample
from backend.portfolio_engine import run_portfolio_backtest
from backend.walk_forward_engine import run_walk_forward


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _summary(result: dict[str, Any] | None, key: str = "summary") -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    value = result.get(key)
    return value if isinstance(value, dict) else {}


def _safe_run(name: str, enabled: bool, fn: Callable[[dict[str, Any]], dict[str, Any]], payload: dict[str, Any]) -> dict[str, Any]:
    if not enabled:
        return {"status": "SKIPPED", "summary": {"status": "SKIPPED"}, "warnings": [f"{name} validation was not selected."]}
    try:
        return fn(payload)
    except Exception as exc:
        return {
            "status": "ERROR",
            "summary": {"status": "ERROR"},
            "error": str(exc),
            "warnings": [f"{name} validation failed: {exc}"],
        }


def _check(layer: str, passed: bool, weight: float, value: Any, rule: str, required: bool = True) -> dict[str, Any]:
    status = "PASS" if passed else "FAIL" if required else "WARN"
    return {
        "layer": layer,
        "status": status,
        "passed": bool(passed),
        "required": bool(required),
        "weight": weight,
        "score": weight if passed else 0.0,
        "value": value,
        "rule": rule,
    }


def _validation_checks(
    request: dict[str, Any],
    backtest: dict[str, Any],
    oos: dict[str, Any],
    walk_forward: dict[str, Any],
    monte_carlo: dict[str, Any],
    portfolio: dict[str, Any],
    mt5_comparison: dict[str, Any],
) -> list[dict[str, Any]]:
    thresholds = request.get("thresholds") if isinstance(request.get("thresholds"), dict) else {}
    min_backtest_trades = _int(thresholds.get("min_backtest_trades"), 50)
    min_backtest_pf = _num(thresholds.get("min_backtest_pf"), 1.15)
    max_backtest_dd = _num(thresholds.get("max_backtest_drawdown_R"), 12.0)
    min_oos_trades = _int(thresholds.get("min_oos_trades"), 20)
    min_oos_pf = _num(thresholds.get("min_oos_pf"), 1.10)
    min_wf_pass_rate = _num(thresholds.get("min_walk_forward_pass_rate"), 0.60)
    min_wf_efficiency = _num(thresholds.get("min_walk_forward_efficiency"), 0.50)
    max_mc_dd_prob = _num(thresholds.get("max_mc_drawdown_breach_probability"), 0.10)
    max_mc_loss_prob = _num(thresholds.get("max_mc_loss_probability"), 0.25)
    min_portfolio_legs = _int(thresholds.get("min_portfolio_legs"), 3)
    require_mt5 = bool(request.get("require_mt5_comparison", False))

    bt = _summary(backtest)
    oos_summary = _summary(oos)
    oos_out = _summary(oos, "out_of_sample")
    wf = _summary(walk_forward)
    mc = _summary(monte_carlo)
    mc_risk = _summary(monte_carlo, "risk_of_ruin")
    pf = _summary(portfolio)
    mt5_status = mt5_comparison.get("status") if isinstance(mt5_comparison, dict) else None
    mt5_rows = mt5_comparison.get("rows") if isinstance(mt5_comparison, dict) else []
    real_tick = next((row for row in (mt5_rows or []) if row.get("model") == "every_tick_real_ticks"), {})

    checks = [
        _check("Local Backtest Trades", _int(bt.get("total_trades")) >= min_backtest_trades, 10, bt.get("total_trades"), f"Trades >= {min_backtest_trades}"),
        _check("Local Backtest PF", _num(bt.get("profit_factor")) >= min_backtest_pf, 10, bt.get("profit_factor"), f"PF >= {min_backtest_pf}"),
        _check("Local Backtest Expectancy", _num(bt.get("expectancy_R")) > 0, 10, bt.get("expectancy_R"), "Expectancy R > 0"),
        _check("Local Backtest Drawdown", abs(_num(bt.get("max_drawdown_R"))) <= max_backtest_dd, 8, bt.get("max_drawdown_R"), f"Max DD <= {max_backtest_dd}R"),
        _check("Out-of-Sample Status", oos_summary.get("status") == "PASS" and bool(oos_summary.get("stable")), 12, oos_summary.get("status"), "OOS PASS and stable"),
        _check("Out-of-Sample Trades", _int(oos_out.get("total_trades")) >= min_oos_trades, 6, oos_out.get("total_trades"), f"OOS trades >= {min_oos_trades}"),
        _check("Out-of-Sample PF", _num(oos_out.get("profit_factor")) >= min_oos_pf, 7, oos_out.get("profit_factor"), f"OOS PF >= {min_oos_pf}"),
        _check("Walk-Forward Pass Rate", _num(wf.get("pass_rate")) >= min_wf_pass_rate, 10, wf.get("pass_rate"), f"WF pass rate >= {min_wf_pass_rate}"),
        _check("Walk-Forward Efficiency", wf.get("average_walk_forward_efficiency") is None or _num(wf.get("average_walk_forward_efficiency")) >= min_wf_efficiency, 7, wf.get("average_walk_forward_efficiency"), f"Avg WFE >= {min_wf_efficiency}"),
        _check("Monte Carlo Status", mc.get("status") == "PASS", 8, mc.get("status"), "MC status PASS"),
        _check("Monte Carlo Drawdown Risk", _num(mc_risk.get("drawdown_breach_probability"), 1.0) <= max_mc_dd_prob, 5, mc_risk.get("drawdown_breach_probability"), f"DD breach probability <= {max_mc_dd_prob}"),
        _check("Monte Carlo Loss Risk", _num(mc_risk.get("loss_probability"), 1.0) <= max_mc_loss_prob, 5, mc_risk.get("loss_probability"), f"Loss probability <= {max_mc_loss_prob}"),
        _check("Portfolio Breadth", _int(pf.get("legs_completed")) >= min_portfolio_legs and _num(pf.get("expectancy_R")) > 0, 5, pf.get("legs_completed"), f"Portfolio legs >= {min_portfolio_legs} with positive expectancy", required=False),
        _check("MT5 Real-Tick Stability", bool(real_tick) and mt5_status == "MODEL_STABLE_APPROVED_FOR_REVIEW", 12, mt5_status, "Real-tick model comparison stable", required=require_mt5),
    ]
    return checks


def _score(checks: list[dict[str, Any]], require_mt5: bool) -> dict[str, Any]:
    applicable = [row for row in checks if row["required"] or row["layer"] != "MT5 Real-Tick Stability" or require_mt5]
    total_weight = sum(float(row.get("weight") or 0) for row in applicable)
    earned = sum(float(row.get("score") or 0) for row in applicable)
    validation_score = round((earned / total_weight) * 100, 2) if total_weight else 0.0
    failed_required = [row for row in applicable if row.get("required") and not row.get("passed")]
    passed_required = [row for row in applicable if row.get("required") and row.get("passed")]
    if failed_required:
        status = "VALIDATION_REJECTED" if validation_score < 70 else "VALIDATION_WATCHLIST"
    elif validation_score >= 90:
        status = "DEMO_REVIEW_READY"
    elif validation_score >= 80:
        status = "VALIDATION_WATCHLIST"
    else:
        status = "RESEARCH_ONLY"
    return {
        "validation_score": validation_score,
        "status": status,
        "passed_required": len(passed_required),
        "failed_required": len(failed_required),
        "total_required": len([row for row in applicable if row.get("required")]),
        "earned_weight": round(earned, 4),
        "total_weight": round(total_weight, 4),
    }


def _next_actions(score: dict[str, Any], checks: list[dict[str, Any]]) -> list[str]:
    failed = [row for row in checks if row.get("required") and not row.get("passed")]
    actions = [f"Fix or re-test: {row['layer']} ({row['rule']})." for row in failed[:6]]
    if not actions:
        actions.append("If MT5 comparison was not required, import 1-Min OHLC, Every Tick, and Real Ticks reports before funded-account review.")
        actions.append("Run the same candidate on at least EURUSD, GBPUSD, USDJPY, and XAUUSD before trusting symbol robustness.")
    if score.get("validation_score", 0) < 80:
        actions.append("Do not approve yet. Revisit filters, sample size, and regime purity before optimizing deeper.")
    return actions


def run_validation_cockpit(request: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(request.get("payload") if isinstance(request.get("payload"), dict) else request)
    if not payload:
        raise ValueError("Validation cockpit requires a payload or direct backtest request fields.")

    run_portfolio = bool(request.get("run_portfolio", False))
    require_mt5 = bool(request.get("require_mt5_comparison", False))
    oos_settings = request.get("out_of_sample") if isinstance(request.get("out_of_sample"), dict) else {}
    wf_settings = request.get("walk_forward") if isinstance(request.get("walk_forward"), dict) else {}
    mc_settings = request.get("monte_carlo") if isinstance(request.get("monte_carlo"), dict) else {}
    portfolio_settings = request.get("portfolio") if isinstance(request.get("portfolio"), dict) else {}
    mt5_comparison = request.get("mt5_comparison") if isinstance(request.get("mt5_comparison"), dict) else {}

    backtest = _safe_run("Backtest", bool(request.get("run_backtest", True)), lambda p: run_backtest(p, persist=False), payload)
    oos = _safe_run("Out-of-sample", bool(request.get("run_oos", True)), run_out_of_sample, {**deepcopy(payload), **oos_settings})
    walk_forward = _safe_run("Walk-forward", bool(request.get("run_walk_forward", True)), run_walk_forward, {**deepcopy(payload), **wf_settings})
    monte_carlo = _safe_run("Monte Carlo", bool(request.get("run_monte_carlo", True)), run_monte_carlo, {**deepcopy(payload), **mc_settings})
    portfolio = _safe_run("Portfolio", run_portfolio, run_portfolio_backtest, {**deepcopy(payload), **portfolio_settings})

    checks = _validation_checks(request, backtest, oos, walk_forward, monte_carlo, portfolio, mt5_comparison)
    score = _score(checks, require_mt5)
    final_approval = final_approval_review(
        {
            "payload": payload,
            "backtest": backtest,
            "out_of_sample": oos,
            "walk_forward": walk_forward,
            "monte_carlo": monte_carlo,
            "mt5_comparison": mt5_comparison,
            "thresholds": request.get("thresholds") if isinstance(request.get("thresholds"), dict) else {},
            "auto_run_missing": False,
        }
    )

    warnings: list[str] = []
    for result in [backtest, oos, walk_forward, monte_carlo, portfolio]:
        warnings.extend(str(item) for item in (result.get("warnings") or []) if item)
    if not mt5_comparison:
        warnings.append("MT5 model comparison is not imported. A 10/10 validation workflow needs 1-Min OHLC, Every Tick, and Real Ticks reports.")

    return {
        "validation_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            **score,
            "symbol": payload.get("symbol"),
            "timeframe": payload.get("timeframe"),
            "regime_filter": payload.get("regime_filter", "ALL"),
            "strategy_filter": payload.get("strategy_filter", "ALL"),
            "mt5_required": require_mt5,
            "portfolio_run": run_portfolio,
            "decision": "Ready for demo review only." if score["status"] == "DEMO_REVIEW_READY" else "Research validation incomplete; do not approve yet.",
        },
        "scorecard": checks,
        "failed_required": [row for row in checks if row.get("required") and not row.get("passed")],
        "next_actions": _next_actions(score, checks),
        "backtest": backtest,
        "out_of_sample": oos,
        "walk_forward": walk_forward,
        "monte_carlo": monte_carlo,
        "portfolio": portfolio,
        "mt5_comparison": mt5_comparison,
        "final_approval": final_approval,
        "warnings": warnings,
        "request": {
            "payload": payload,
            "run_portfolio": run_portfolio,
            "require_mt5_comparison": require_mt5,
            "thresholds": request.get("thresholds", {}),
        },
    }
