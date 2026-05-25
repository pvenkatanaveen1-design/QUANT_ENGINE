from __future__ import annotations

from typing import Any

from backend.anti_overfit_engine import anti_overfit_gate
from backend.backtest_engine import run_backtest
from backend.monte_carlo_engine import run_monte_carlo
from backend.out_of_sample_engine import run_out_of_sample
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


def _present(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def _check(name: str, passed: bool, required: bool, detail: str, value: Any = None) -> dict[str, Any]:
    return {
        "check": name,
        "passed": bool(passed),
        "required": bool(required),
        "detail": detail,
        "value": value,
        "status": "PASS" if passed else "FAIL" if required else "WARN",
    }


def _optimizer_candidate(optimizer: dict[str, Any]) -> dict[str, Any] | None:
    rows = optimizer.get("results") or optimizer.get("top_candidates") or []
    if not rows:
        return None
    approved = [row for row in rows if row.get("status") == "APPROVED_CANDIDATE"]
    return approved[0] if approved else rows[0]


def _real_tick_row(mt5: dict[str, Any]) -> dict[str, Any]:
    rows = mt5.get("rows") or mt5.get("mt5_model_comparison") or []
    return next((row for row in rows if row.get("model") == "every_tick_real_ticks"), {})


def _thresholds(request: dict[str, Any]) -> dict[str, Any]:
    user = request.get("thresholds") if isinstance(request.get("thresholds"), dict) else {}
    return {
        "min_backtest_trades": _int(user.get("min_backtest_trades"), 50),
        "min_backtest_pf": _num(user.get("min_backtest_pf"), 1.15),
        "min_backtest_expectancy_R": _num(user.get("min_backtest_expectancy_R"), 0.0),
        "max_backtest_drawdown_R": _num(user.get("max_backtest_drawdown_R"), 12.0),
        "min_oos_trades": _int(user.get("min_oos_trades"), 20),
        "min_oos_pf": _num(user.get("min_oos_pf"), 1.10),
        "min_walk_forward_pass_rate": _num(user.get("min_walk_forward_pass_rate"), 0.60),
        "min_walk_forward_efficiency": _num(user.get("min_walk_forward_efficiency"), 0.50),
        "max_mc_drawdown_breach_probability": _num(user.get("max_mc_drawdown_breach_probability"), 0.10),
        "max_mc_loss_probability": _num(user.get("max_mc_loss_probability"), 0.25),
        "max_mc_losing_streak_breach_probability": _num(user.get("max_mc_losing_streak_breach_probability"), 0.20),
        "min_real_tick_trades": _int(user.get("min_real_tick_trades"), 30),
        "min_real_tick_pf": _num(user.get("min_real_tick_pf"), 1.10),
        "min_real_tick_expectancy_R": _num(user.get("min_real_tick_expectancy_R"), 0.0),
        "max_pf_drift": _num(user.get("max_pf_drift"), 0.35),
        "max_trade_count_drift_pct": _num(user.get("max_trade_count_drift_pct"), 0.35),
        "max_net_profit_degradation_pct": _num(user.get("max_net_profit_degradation_pct"), 0.50),
    }


def _maybe_run_missing(request: dict[str, Any], result_key: str, runner) -> dict[str, Any]:
    existing = request.get(result_key)
    if _present(existing):
        return existing
    if not request.get("auto_run_missing", False):
        return {}
    payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
    if not payload:
        return {}
    try:
        return runner(payload)
    except Exception as exc:
        return {"summary": {"status": "ERROR"}, "warnings": [str(exc)], "error": str(exc)}


def final_approval_review(request: dict[str, Any]) -> dict[str, Any]:
    payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
    thresholds = _thresholds(request)
    backtest = _maybe_run_missing(request, "backtest", lambda p: run_backtest(p, persist=False))
    oos = _maybe_run_missing(request, "out_of_sample", run_out_of_sample)
    walk_forward = _maybe_run_missing(request, "walk_forward", run_walk_forward)
    monte_carlo = _maybe_run_missing(request, "monte_carlo", run_monte_carlo)
    optimizer = request.get("optimizer") if isinstance(request.get("optimizer"), dict) else {}
    mt5 = request.get("mt5_comparison") if isinstance(request.get("mt5_comparison"), dict) else {}
    anti_overfit = anti_overfit_gate(
        backtest=backtest,
        out_of_sample=oos,
        walk_forward=walk_forward,
        monte_carlo=monte_carlo,
        optimizer=optimizer,
        thresholds=request.get("thresholds") if isinstance(request.get("thresholds"), dict) else {},
    )

    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    candidate = _optimizer_candidate(optimizer)
    checks.append(
        _check(
            "optimizer_candidate",
            candidate is not None and candidate.get("status") == "APPROVED_CANDIDATE",
            False,
            "Optimizer found an approved candidate." if candidate and candidate.get("status") == "APPROVED_CANDIDATE" else "Optimizer is absent or did not produce an approved candidate. This does not block validation, but ranking quality is unknown.",
            candidate.get("status") if candidate else None,
        )
    )

    summary = backtest.get("summary", {}) if isinstance(backtest, dict) else {}
    checks.extend(
        [
            _check("backtest_present", bool(summary), True, "Local backtest result is available." if summary else "Run local backtest first."),
            _check("backtest_trade_count", _int(summary.get("total_trades")) >= thresholds["min_backtest_trades"], True, f"Backtest trades must be >= {thresholds['min_backtest_trades']}.", summary.get("total_trades")),
            _check("backtest_profit_factor", _num(summary.get("profit_factor")) >= thresholds["min_backtest_pf"], True, f"Backtest PF must be >= {thresholds['min_backtest_pf']}.", summary.get("profit_factor")),
            _check("backtest_expectancy", _num(summary.get("expectancy_R")) > thresholds["min_backtest_expectancy_R"], True, "Backtest expectancy must be positive.", summary.get("expectancy_R")),
            _check("backtest_drawdown", abs(_num(summary.get("max_drawdown_R"))) <= thresholds["max_backtest_drawdown_R"], True, f"Backtest drawdown must be within {thresholds['max_backtest_drawdown_R']}R.", summary.get("max_drawdown_R")),
        ]
    )

    oos_summary = oos.get("summary", {}) if isinstance(oos, dict) else {}
    oos_out = oos.get("out_of_sample", {}) if isinstance(oos, dict) else {}
    checks.extend(
        [
            _check("oos_present", bool(oos_summary), True, "Out-of-sample result is available." if oos_summary else "Run out-of-sample validation."),
            _check("oos_status", oos_summary.get("status") == "PASS" and bool(oos_summary.get("stable")), True, "OOS must pass and be stable.", oos_summary.get("status")),
            _check("oos_trade_count", _int(oos_out.get("total_trades")) >= thresholds["min_oos_trades"], True, f"OOS trades must be >= {thresholds['min_oos_trades']}.", oos_out.get("total_trades")),
            _check("oos_profit_factor", _num(oos_out.get("profit_factor")) >= thresholds["min_oos_pf"], True, f"OOS PF must be >= {thresholds['min_oos_pf']}.", oos_out.get("profit_factor")),
        ]
    )

    wf_summary = walk_forward.get("summary", {}) if isinstance(walk_forward, dict) else {}
    checks.extend(
        [
            _check("walk_forward_present", bool(wf_summary), True, "Walk-forward result is available." if wf_summary else "Run walk-forward validation."),
            _check("walk_forward_stable", bool(wf_summary.get("stable")), True, "Walk-forward must be stable.", wf_summary.get("stable")),
            _check("walk_forward_pass_rate", _num(wf_summary.get("pass_rate")) >= thresholds["min_walk_forward_pass_rate"], True, f"Walk-forward pass rate must be >= {thresholds['min_walk_forward_pass_rate']}.", wf_summary.get("pass_rate")),
            _check("walk_forward_efficiency", wf_summary.get("average_walk_forward_efficiency") is None or _num(wf_summary.get("average_walk_forward_efficiency")) >= thresholds["min_walk_forward_efficiency"], True, f"Average WFE must be >= {thresholds['min_walk_forward_efficiency']} when available.", wf_summary.get("average_walk_forward_efficiency")),
        ]
    )

    mc_summary = monte_carlo.get("summary", {}) if isinstance(monte_carlo, dict) else {}
    mc_risk = monte_carlo.get("risk_of_ruin", {}) if isinstance(monte_carlo, dict) else {}
    checks.extend(
        [
            _check("monte_carlo_present", bool(mc_summary), True, "Monte Carlo result is available." if mc_summary else "Run Monte Carlo validation."),
            _check("monte_carlo_status", mc_summary.get("status") == "PASS", True, "Monte Carlo status must be PASS.", mc_summary.get("status")),
            _check("monte_carlo_drawdown_breach", _num(mc_risk.get("drawdown_breach_probability")) <= thresholds["max_mc_drawdown_breach_probability"], True, f"MC drawdown breach probability must be <= {thresholds['max_mc_drawdown_breach_probability']}.", mc_risk.get("drawdown_breach_probability")),
            _check("monte_carlo_loss_probability", _num(mc_risk.get("loss_probability")) <= thresholds["max_mc_loss_probability"], True, f"MC loss probability must be <= {thresholds['max_mc_loss_probability']}.", mc_risk.get("loss_probability")),
            _check("monte_carlo_losing_streak", _num(mc_risk.get("losing_streak_breach_probability")) <= thresholds["max_mc_losing_streak_breach_probability"], True, f"MC losing-streak breach probability must be <= {thresholds['max_mc_losing_streak_breach_probability']}.", mc_risk.get("losing_streak_breach_probability")),
        ]
    )
    checks.append(
        _check(
            "anti_overfit_gate",
            anti_overfit.get("status") == "PASS",
            True,
            anti_overfit.get("verdict", "Anti-overfit gate must pass."),
            anti_overfit.get("status"),
        )
    )
    for gate_check in anti_overfit.get("checks", []):
        checks.append({**gate_check, "check": gate_check.get("check", "anti_overfit_detail")})

    real_tick = _real_tick_row(mt5)
    stability = mt5.get("stability", {}) if isinstance(mt5, dict) else {}
    mt5_status = mt5.get("status")
    checks.extend(
        [
            _check("mt5_comparison_present", bool(mt5), True, "MT5 model comparison is available." if mt5 else "Import 1-Min OHLC, Every Tick, and Real Ticks reports."),
            _check("mt5_real_tick_present", bool(real_tick), True, "Real-tick model row is present." if real_tick else "Real-tick MT5 report is missing."),
            _check("mt5_real_tick_trades", _int(real_tick.get("trade_count")) >= thresholds["min_real_tick_trades"], True, f"Real-tick trades must be >= {thresholds['min_real_tick_trades']}.", real_tick.get("trade_count")),
            _check("mt5_real_tick_pf", _num(real_tick.get("profit_factor")) >= thresholds["min_real_tick_pf"], True, f"Real-tick PF must be >= {thresholds['min_real_tick_pf']}.", real_tick.get("profit_factor")),
            _check("mt5_real_tick_expectancy", _num(real_tick.get("expectancy_R")) > thresholds["min_real_tick_expectancy_R"], True, "Real-tick expectancy must be positive.", real_tick.get("expectancy_R")),
            _check("mt5_model_stability_status", mt5_status == "MODEL_STABLE_APPROVED_FOR_REVIEW", True, "MT5 model comparison status must be stable.", mt5_status),
            _check("mt5_pf_drift", stability.get("profit_factor_drift_1m_to_real_ticks") is not None and abs(_num(stability.get("profit_factor_drift_1m_to_real_ticks"))) <= thresholds["max_pf_drift"], True, f"PF drift from 1-Min OHLC to Real Ticks must be <= {thresholds['max_pf_drift']}.", stability.get("profit_factor_drift_1m_to_real_ticks")),
            _check("mt5_trade_count_drift", stability.get("trade_count_drift_pct_1m_to_real_ticks") is not None and abs(_num(stability.get("trade_count_drift_pct_1m_to_real_ticks"))) <= thresholds["max_trade_count_drift_pct"], True, f"Trade-count drift must be <= {thresholds['max_trade_count_drift_pct']}.", stability.get("trade_count_drift_pct_1m_to_real_ticks")),
            _check("mt5_net_profit_degradation", stability.get("net_profit_drift_pct_1m_to_real_ticks") is not None and _num(stability.get("net_profit_drift_pct_1m_to_real_ticks")) >= -thresholds["max_net_profit_degradation_pct"], True, f"Net profit degradation must not exceed {thresholds['max_net_profit_degradation_pct']}.", stability.get("net_profit_drift_pct_1m_to_real_ticks")),
        ]
    )

    required = [row for row in checks if row["required"]]
    failed_required = [row for row in required if not row["passed"]]
    optional_failed = [row for row in checks if not row["required"] and not row["passed"]]
    if failed_required:
        status = "FINAL_REJECTED"
        decision = "Do not approve. Required validation layers are missing or failing."
    else:
        status = "FINAL_APPROVED_FOR_DEMO_REVIEW"
        decision = "Candidate passed local, OOS, walk-forward, Monte Carlo, and MT5 real-tick validation gates. Use demo or paper review before any funded-account decision."

    if optional_failed:
        warnings.append("Optimizer ranking is optional for the final gate, but absent/weak optimizer output reduces candidate selection confidence.")
    if status != "FINAL_APPROVED_FOR_DEMO_REVIEW":
        warnings.append("Final approval requires all required gates to pass. Optimizer ranking alone is never enough.")
    warnings.extend(anti_overfit.get("warnings", []))
    warnings.append("This approval gate is research validation only. It does not authorize live or funded-account execution.")

    return {
        "status": status,
        "decision": decision,
        "passed_required": len(required) - len(failed_required),
        "failed_required": len(failed_required),
        "total_required": len(required),
        "checks": checks,
        "failed_checks": failed_required,
        "candidate": {
            "symbol": payload.get("symbol"),
            "timeframe": payload.get("timeframe"),
            "regime_filter": payload.get("regime_filter"),
            "strategy_filter": payload.get("strategy_filter"),
            "optimizer_candidate": candidate,
        },
        "thresholds": thresholds,
        "anti_overfit_gate": anti_overfit,
        "warnings": warnings,
        "inputs_used": {
            "backtest": bool(summary),
            "optimizer": bool(optimizer),
            "out_of_sample": bool(oos_summary),
            "walk_forward": bool(wf_summary),
            "monte_carlo": bool(mc_summary),
            "mt5_comparison": bool(mt5),
            "auto_run_missing": bool(request.get("auto_run_missing", False)),
        },
    }
