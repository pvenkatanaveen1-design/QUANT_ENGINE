from __future__ import annotations

from typing import Any


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


def _summary(source: dict[str, Any], key: str = "summary") -> dict[str, Any]:
    value = source.get(key) if isinstance(source, dict) else {}
    return value if isinstance(value, dict) else {}


def multiple_test_penalty(trials: int) -> dict[str, Any]:
    trials = max(0, int(trials or 0))
    if trials <= 25:
        level = "LOW"
        extra_trades = 0
        extra_pf = 0.0
        extra_oos_retention = 0.0
    elif trials <= 100:
        level = "MODERATE"
        extra_trades = 10
        extra_pf = 0.05
        extra_oos_retention = 0.05
    elif trials <= 500:
        level = "HIGH"
        extra_trades = 25
        extra_pf = 0.10
        extra_oos_retention = 0.10
    else:
        level = "EXTREME"
        extra_trades = 50
        extra_pf = 0.20
        extra_oos_retention = 0.15
    return {
        "trials": trials,
        "level": level,
        "extra_min_trades": extra_trades,
        "extra_profit_factor": extra_pf,
        "extra_oos_retention": extra_oos_retention,
        "reason": "More tested combinations require stricter evidence because one setup can look good by luck.",
    }


def adjusted_thresholds(base: dict[str, Any] | None = None, trials: int = 0) -> dict[str, Any]:
    base = base if isinstance(base, dict) else {}
    penalty = multiple_test_penalty(trials)
    min_trades = _int(base.get("min_backtest_trades", base.get("min_trades")), 50) + penalty["extra_min_trades"]
    min_pf = _num(base.get("min_backtest_pf", base.get("min_profit_factor")), 1.15) + penalty["extra_profit_factor"]
    min_oos_retention = _num(base.get("min_oos_retention"), 0.50) + penalty["extra_oos_retention"]
    return {
        "min_backtest_trades": min_trades,
        "min_backtest_pf": round(min_pf, 4),
        "min_backtest_expectancy_R": _num(base.get("min_backtest_expectancy_R"), 0.0),
        "min_oos_trades": _int(base.get("min_oos_trades"), 20),
        "min_oos_pf": _num(base.get("min_oos_pf"), 1.10),
        "min_oos_retention": round(min_oos_retention, 4),
        "min_walk_forward_pass_rate": _num(base.get("min_walk_forward_pass_rate"), 0.60),
        "min_walk_forward_efficiency": _num(base.get("min_walk_forward_efficiency"), 0.50),
        "max_mc_drawdown_breach_probability": _num(base.get("max_mc_drawdown_breach_probability"), 0.10),
        "max_mc_loss_probability": _num(base.get("max_mc_loss_probability"), 0.25),
        "max_mc_losing_streak_breach_probability": _num(base.get("max_mc_losing_streak_breach_probability"), 0.20),
        "multiple_test_penalty": penalty,
    }


def _check(name: str, passed: bool, detail: str, value: Any = None, required: bool = True) -> dict[str, Any]:
    return {
        "check": name,
        "passed": bool(passed),
        "required": bool(required),
        "status": "PASS" if passed else "FAIL" if required else "WARN",
        "value": value,
        "detail": detail,
    }


def anti_overfit_gate(
    *,
    backtest: dict[str, Any] | None = None,
    out_of_sample: dict[str, Any] | None = None,
    walk_forward: dict[str, Any] | None = None,
    monte_carlo: dict[str, Any] | None = None,
    optimizer: dict[str, Any] | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    backtest = backtest if isinstance(backtest, dict) else {}
    out_of_sample = out_of_sample if isinstance(out_of_sample, dict) else {}
    walk_forward = walk_forward if isinstance(walk_forward, dict) else {}
    monte_carlo = monte_carlo if isinstance(monte_carlo, dict) else {}
    optimizer = optimizer if isinstance(optimizer, dict) else {}

    optimizer_summary = _summary(optimizer)
    trials = _int(
        optimizer_summary.get("combinations_requested", optimizer_summary.get("combinations_run")),
        len(optimizer.get("results") or []),
    )
    gate_thresholds = adjusted_thresholds(thresholds, trials)
    checks: list[dict[str, Any]] = []

    bt_summary = _summary(backtest)
    checks.extend(
        [
            _check("anti_overfit_min_trades", _int(bt_summary.get("total_trades")) >= gate_thresholds["min_backtest_trades"], f"Backtest trades must be >= adjusted minimum {gate_thresholds['min_backtest_trades']}.", bt_summary.get("total_trades")),
            _check("anti_overfit_profit_factor", _num(bt_summary.get("profit_factor")) >= gate_thresholds["min_backtest_pf"], f"Backtest PF must be >= adjusted minimum {gate_thresholds['min_backtest_pf']}.", bt_summary.get("profit_factor")),
            _check("anti_overfit_expectancy", _num(bt_summary.get("expectancy_R")) > gate_thresholds["min_backtest_expectancy_R"], "Backtest expectancy must remain positive.", bt_summary.get("expectancy_R")),
        ]
    )

    oos_summary = _summary(out_of_sample)
    oos_out = _summary(out_of_sample, "out_of_sample")
    checks.extend(
        [
            _check("anti_overfit_oos_status", oos_summary.get("status") == "PASS" and bool(oos_summary.get("stable")), "OOS must pass and be stable.", oos_summary.get("status")),
            _check("anti_overfit_oos_trades", _int(oos_out.get("total_trades")) >= gate_thresholds["min_oos_trades"], f"OOS trades must be >= {gate_thresholds['min_oos_trades']}.", oos_out.get("total_trades")),
            _check("anti_overfit_oos_pf", _num(oos_out.get("profit_factor")) >= gate_thresholds["min_oos_pf"], f"OOS PF must be >= {gate_thresholds['min_oos_pf']}.", oos_out.get("profit_factor")),
            _check("anti_overfit_oos_retention", oos_summary.get("performance_retention") is not None and _num(oos_summary.get("performance_retention")) >= gate_thresholds["min_oos_retention"], f"OOS performance retention must be >= adjusted minimum {gate_thresholds['min_oos_retention']}.", oos_summary.get("performance_retention")),
        ]
    )

    wf_summary = _summary(walk_forward)
    checks.extend(
        [
            _check("anti_overfit_walk_forward_pass_rate", _num(wf_summary.get("pass_rate")) >= gate_thresholds["min_walk_forward_pass_rate"], f"Walk-forward pass rate must be >= {gate_thresholds['min_walk_forward_pass_rate']}.", wf_summary.get("pass_rate")),
            _check("anti_overfit_walk_forward_efficiency", wf_summary.get("average_walk_forward_efficiency") is None or _num(wf_summary.get("average_walk_forward_efficiency")) >= gate_thresholds["min_walk_forward_efficiency"], f"Average WFE must be >= {gate_thresholds['min_walk_forward_efficiency']} when available.", wf_summary.get("average_walk_forward_efficiency")),
            _check("anti_overfit_walk_forward_stable", bool(wf_summary.get("stable")), "Walk-forward summary must be stable.", wf_summary.get("stable")),
        ]
    )

    mc_summary = _summary(monte_carlo)
    mc_risk = _summary(monte_carlo, "risk_of_ruin")
    checks.extend(
        [
            _check("anti_overfit_monte_carlo_status", mc_summary.get("status") == "PASS", "Monte Carlo status must be PASS.", mc_summary.get("status")),
            _check("anti_overfit_mc_drawdown_tail", _num(mc_risk.get("drawdown_breach_probability")) <= gate_thresholds["max_mc_drawdown_breach_probability"], f"MC drawdown breach probability must be <= {gate_thresholds['max_mc_drawdown_breach_probability']}.", mc_risk.get("drawdown_breach_probability")),
            _check("anti_overfit_mc_loss_tail", _num(mc_risk.get("loss_probability")) <= gate_thresholds["max_mc_loss_probability"], f"MC loss probability must be <= {gate_thresholds['max_mc_loss_probability']}.", mc_risk.get("loss_probability")),
            _check("anti_overfit_mc_losing_streak_tail", _num(mc_risk.get("losing_streak_breach_probability")) <= gate_thresholds["max_mc_losing_streak_breach_probability"], f"MC losing-streak breach probability must be <= {gate_thresholds['max_mc_losing_streak_breach_probability']}.", mc_risk.get("losing_streak_breach_probability")),
        ]
    )

    failed = [row for row in checks if row["required"] and not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    warnings = []
    if gate_thresholds["multiple_test_penalty"]["level"] in {"HIGH", "EXTREME"}:
        warnings.append(f"Multiple-test penalty is {gate_thresholds['multiple_test_penalty']['level']}; approval thresholds were tightened.")
    if failed:
        warnings.append("Anti-overfit gate failed. Treat this setup as rejected even if the in-sample backtest looks attractive.")

    return {
        "status": status,
        "passed": status == "PASS",
        "checks": checks,
        "failed_checks": failed,
        "thresholds": gate_thresholds,
        "warnings": warnings,
        "verdict": "Reject likely curve-fit candidate." if failed else "Candidate passed minimum anti-overfit evidence gates.",
    }
