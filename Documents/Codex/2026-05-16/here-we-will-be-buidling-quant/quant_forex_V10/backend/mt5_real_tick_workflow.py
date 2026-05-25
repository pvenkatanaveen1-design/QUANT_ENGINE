from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.mt5_report_importer import MODEL_NAMES, MODEL_ORDER, compare_mt5_model_reports
from backend.mt5_parity_engine import run_mt5_parity_check
from backend.mt5_tester_runner import run_mt5_strategy_tester


def _candidate(payload: dict[str, Any], python_run_id: str | None = None) -> dict[str, Any]:
    return {
        "python_run_id": python_run_id,
        "symbol": payload.get("symbol"),
        "timeframe": payload.get("timeframe"),
        "start_date": payload.get("start_date"),
        "end_date": payload.get("end_date"),
        "regime_filter": payload.get("regime_filter", "ALL"),
        "strategy_filter": payload.get("strategy_filter", "ALL"),
        "risk_percent": payload.get("risk_percent", 1.0),
        "rr": payload.get("rr", 2.0),
        "initial_equity": payload.get("initial_equity", 100000),
    }


def _report_flags(reports: dict[str, str]) -> dict[str, bool]:
    return {model: bool(str(reports.get(model) or "").strip()) for model in MODEL_ORDER}


def _workflow_steps(tester_runs: dict[str, Any], comparison: dict[str, Any] | None, reports_supplied: dict[str, bool], launch_terminal: bool, parity_check: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config_ready = all(bool((tester_runs.get(model) or {}).get("tester_config")) for model in MODEL_ORDER)
    report_count = sum(1 for supplied in reports_supplied.values() if supplied)
    comparison_status = comparison.get("status") if comparison else None
    parity_status = parity_check.get("status") if parity_check else None
    return [
        {
            "step": 1,
            "name": "Python candidate selected",
            "status": "READY",
            "detail": "The current UI payload is the single source of truth for all MT5 model tests.",
        },
        {
            "step": 2,
            "name": "MT5 tester configs generated",
            "status": "PASS" if config_ready else "REVIEW",
            "detail": "Generated one .ini/.set pair per tester model using the same regime, strategy, filters, risk, and RR.",
        },
        {
            "step": 3,
            "name": "MT5 Strategy Tester execution",
            "status": "LAUNCH_REQUESTED" if launch_terminal else "CONFIG_ONLY",
            "detail": "Run the generated configs in MT5 for 1-Min OHLC, Every Tick, and Every Tick Based On Real Ticks.",
        },
        {
            "step": 4,
            "name": "MT5 reports imported",
            "status": "PASS" if report_count == 3 else ("PARTIAL" if report_count else "WAITING"),
            "detail": f"Imported report text supplied for {report_count}/3 MT5 models.",
        },
        {
            "step": 5,
            "name": "Model robustness comparison",
            "status": comparison_status or "WAITING_FOR_REPORTS",
            "detail": "The setup is robust only if real ticks remain profitable and drift versus 1-Min OHLC is acceptable.",
        },
        {
            "step": 6,
            "name": "Python versus MT5 parity",
            "status": parity_status or "WAITING_FOR_REAL_TICK_REPORT",
            "detail": "Compares the saved Python run against MT5 real-tick tester output. Exact parity is best when the EA exports PYIDX/PYHASH.",
        },
    ]


def _model_cards(tester_runs: dict[str, Any], reports_supplied: dict[str, bool], generated_report_sources: dict[str, str]) -> list[dict[str, Any]]:
    cards = []
    for model in MODEL_ORDER:
        run = tester_runs.get(model) or {}
        config = run.get("tester_config") if isinstance(run.get("tester_config"), dict) else {}
        report_supplied = bool(reports_supplied.get(model))
        generated_report = generated_report_sources.get(model)
        run_status = run.get("status") or "NOT_PREPARED"
        if report_supplied:
            next_action = "Report available. Include this model in the comparison."
        elif run_status in {"CONFIG_READY_NOT_LAUNCHED", "CONFIG_READY"}:
            next_action = "Open the generated .ini in MT5 Strategy Tester, run it, then paste/export the report."
        elif run_status in {"TERMINAL_LAUNCHED", "TERMINAL_LAUNCHED_REPORT_NOT_FOUND"}:
            next_action = "Check MT5 Strategy Tester journal and report path, then paste the report if it was generated."
        elif run_status == "REPORT_IMPORTED":
            next_action = "Imported automatically. Review model comparison and parity status."
        else:
            next_action = "Review terminal path, compiled EA location, and tester config."
        cards.append(
            {
                "model": model,
                "model_name": MODEL_NAMES[model],
                "purpose": "fast research filter" if model == "one_min_ohlc" else "intrabar validation" if model == "every_tick" else "final broker/tick validation",
                "status": run_status,
                "report_supplied": report_supplied,
                "generated_report_source": generated_report,
                "ini_path": config.get("ini_path"),
                "set_path": config.get("set_path"),
                "report_path": config.get("report_path"),
                "command": run.get("command") or [],
                "next_action": next_action,
            }
        )
    return cards


def _workflow_readiness(
    tester_runs: dict[str, Any],
    comparison: dict[str, Any] | None,
    reports_supplied: dict[str, bool],
    parity_check: dict[str, Any] | None,
    launch_terminal: bool,
) -> dict[str, Any]:
    configs_ready = all(bool((tester_runs.get(model) or {}).get("tester_config")) for model in MODEL_ORDER)
    reports_count = sum(1 for supplied in reports_supplied.values() if supplied)
    missing_reports = [MODEL_NAMES[model] for model in MODEL_ORDER if not reports_supplied.get(model)]
    comparison_status = comparison.get("status") if comparison else None
    parity_status = parity_check.get("status") if parity_check else None
    if comparison_status in {"MODEL_STABLE_APPROVED_FOR_REVIEW"} and parity_status in {None, "PASS", "APPROVED"}:
        stage = "READY_FOR_REVIEW"
    elif reports_count == 3 and comparison:
        stage = "MODEL_COMPARISON_REVIEW"
    elif reports_count == 3:
        stage = "REPORTS_READY_FOR_COMPARISON"
    elif configs_ready:
        stage = "CONFIGS_READY_RUN_MT5"
    else:
        stage = "SETUP_INCOMPLETE"
    blockers = []
    if not configs_ready:
        blockers.append("MT5 tester configs were not generated for all three models.")
    if missing_reports:
        blockers.append(f"Missing reports: {', '.join(missing_reports)}.")
    if comparison and comparison.get("errors"):
        blockers.append("One or more imported reports failed to parse.")
    return {
        "stage": stage,
        "configs_ready": configs_ready,
        "launch_terminal_requested": launch_terminal,
        "reports_supplied_count": reports_count,
        "reports_required_count": len(MODEL_ORDER),
        "missing_reports": missing_reports,
        "comparison_status": comparison_status or "WAITING",
        "parity_status": parity_status or "WAITING",
        "blockers": blockers,
    }


def _next_actions(readiness: dict[str, Any]) -> list[str]:
    stage = readiness.get("stage")
    if stage == "READY_FOR_REVIEW":
        return [
            "Review the real-tick model row first; it is the final execution-quality gate.",
            "Run Python/MT5 parity if the EA exported PYIDX/PYHASH comments.",
            "Use final approval only after OOS, walk-forward, Monte Carlo, and MT5 real ticks are acceptable.",
        ]
    if stage == "MODEL_COMPARISON_REVIEW":
        return [
            "Review failed comparison checks before approving the setup.",
            "If real ticks degraded versus 1-Min OHLC, tighten cost/spread/slippage assumptions or reject the candidate.",
            "Run parity check if report comments include PYIDX/PYHASH.",
        ]
    if stage == "REPORTS_READY_FOR_COMPARISON":
        return [
            "Run the workflow again or import model comparison to calculate stability checks.",
            "Check PF drift, trade-count drift, net-profit degradation, and real-tick expectancy.",
            "If real ticks fail while 1-Min OHLC passes, treat the setup as execution fragile.",
        ]
    if stage == "CONFIGS_READY_RUN_MT5":
        return [
            "Run the generated 1-Min OHLC, Every Tick, and Real Tick tester configs in MT5.",
            "Paste each generated report into the matching report box below.",
            "Then click Prepare / Compare Real Tick Workflow again.",
        ]
    return [
        "Run a local Python backtest first so the workflow has a candidate and optional run_id.",
        "Confirm the EA is compiled in MT5 Experts and the terminal path is configured.",
        "Generate tester configs before importing reports.",
    ]


def _quick_start() -> list[dict[str, str]]:
    return [
        {"step": "1", "title": "Run Python backtest", "detail": "Use the current symbol/regime/strategy controls and keep the run_id."},
        {"step": "2", "title": "Prepare MT5 configs", "detail": "Click Prepare / Compare Real Tick Workflow to create one config per tester model."},
        {"step": "3", "title": "Run MT5 tester models", "detail": "Run 1-Min OHLC, Every Tick, and Real Ticks with the same .set inputs."},
        {"step": "4", "title": "Import reports", "detail": "Paste all three reports, compare drift, then check Python/MT5 parity."},
    ]


def _read_generated_reports(tester_runs: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    reports: dict[str, str] = {}
    sources: dict[str, str] = {}
    for model, run in tester_runs.items():
        found = run.get("report_found_path")
        candidates = []
        if found:
            candidates.append(found)
        config = run.get("tester_config") if isinstance(run.get("tester_config"), dict) else {}
        candidates.extend(config.get("report_path_candidates") or [])
        if config.get("report_path"):
            candidates.append(config["report_path"])
        for candidate in candidates:
            path = Path(str(candidate))
            try:
                if path.exists() and path.stat().st_size > 0:
                    reports[model] = path.read_text(encoding="utf-8", errors="ignore")
                    sources[model] = str(path)
                    break
            except OSError:
                continue
    return reports, sources


def run_real_tick_workflow(request: dict[str, Any]) -> dict[str, Any]:
    payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
    reports = request.get("reports") if isinstance(request.get("reports"), dict) else {}
    thresholds = request.get("thresholds") if isinstance(request.get("thresholds"), dict) else {}
    workflow_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    launch_terminal = bool(request.get("launch_terminal", False))
    warnings: list[str] = [
        "Real-tick validation is a robustness workflow, not live execution.",
        "Use the same candidate setup across all three MT5 tester models before approving any strategy.",
    ]
    if not launch_terminal:
        warnings.append("launch_terminal=false by default, so this workflow generated configs without starting MT5.")
    else:
        warnings.append("launch_terminal=true will request MT5 tester launches for all three models. Keep the EA tester-only safety enabled.")

    tester_runs: dict[str, Any] = {}
    for model in MODEL_ORDER:
        model_payload = copy.deepcopy(payload)
        mt5_backtest = model_payload.get("mt5_backtest") if isinstance(model_payload.get("mt5_backtest"), dict) else {}
        model_payload["mt5_backtest"] = {
            **mt5_backtest,
            "test_model": model,
            "execution_quality": "strict_final_validation" if model == "every_tick_real_ticks" else "normal_validation" if model == "every_tick" else "fast_research",
            "spread_mode": "mt5_real_spread" if model == "every_tick_real_ticks" else "model_spread",
        }
        run_request = {
            **request,
            "payload": model_payload,
            "launch_terminal": launch_terminal,
            "wait_for_report": bool(request.get("wait_for_report", False)),
            "python_run_id": request.get("python_run_id"),
        }
        tester_runs[model] = run_mt5_strategy_tester(run_request)

    generated_reports, generated_report_sources = _read_generated_reports(tester_runs)
    combined_reports = {**generated_reports, **{model: text for model, text in reports.items() if str(text or "").strip()}}
    reports_supplied = _report_flags(combined_reports)
    comparison = None
    parity_check = None
    if any(reports_supplied.values()):
        comparison = compare_mt5_model_reports(
            {
                "reports": combined_reports,
                "thresholds": thresholds,
                "run_id": request.get("python_run_id") or request.get("run_id"),
                "symbol": payload.get("symbol"),
                "timeframe": payload.get("timeframe"),
                "start_date": payload.get("start_date"),
                "end_date": payload.get("end_date"),
                "initial_equity": payload.get("initial_equity", request.get("initial_equity", 100000)),
                "risk_percent": payload.get("risk_percent", request.get("risk_percent", 1.0)),
                "max_deals_returned": int(request.get("max_deals_returned") or 500),
            }
        )
        warnings.extend(comparison.get("warnings", []))
        if comparison.get("missing_models"):
            warnings.append(f"Reports are still missing for: {', '.join(comparison['missing_models'])}.")
        real_tick_import_id = None
        imports = comparison.get("imports") if isinstance(comparison.get("imports"), dict) else {}
        if isinstance(imports.get("every_tick_real_ticks"), dict):
            real_tick_import_id = imports["every_tick_real_ticks"].get("import_id")
        if request.get("python_run_id") and real_tick_import_id:
            parity_check = run_mt5_parity_check(
                {
                    "python_run_id": request.get("python_run_id"),
                    "mt5_import_id": real_tick_import_id,
                    "tolerances": request.get("parity_tolerances", {}),
                    "max_mismatches_returned": int(request.get("max_mismatches_returned") or 50),
                }
            )
            warnings.extend(parity_check.get("warnings", []))
    else:
        warnings.append("Paste or import all three MT5 tester reports to complete the model comparison.")

    readiness = _workflow_readiness(tester_runs, comparison, reports_supplied, parity_check, launch_terminal)

    if comparison:
        status = "REPORTS_IMPORTED" if not comparison.get("missing_models") and not comparison.get("errors") else "PARTIAL_REPORTS_IMPORTED"
    elif launch_terminal:
        status = "RUNS_REQUESTED"
    else:
        status = "CONFIGS_READY"

    return {
        "workflow_id": workflow_id,
        "created_at": created_at,
        "status": status,
        "order_execution": False,
        "candidate": _candidate(payload, request.get("python_run_id") or request.get("run_id")),
        "models": [{"model": model, "name": MODEL_NAMES[model]} for model in MODEL_ORDER],
        "reports_supplied": reports_supplied,
        "generated_report_sources": generated_report_sources,
        "readiness": readiness,
        "next_actions": _next_actions(readiness),
        "quick_start": _quick_start(),
        "model_cards": _model_cards(tester_runs, reports_supplied, generated_report_sources),
        "steps": _workflow_steps(tester_runs, comparison, reports_supplied, launch_terminal, parity_check),
        "tester_runs": tester_runs,
        "model_comparison": comparison,
        "parity_check": parity_check,
        "warnings": warnings,
    }
