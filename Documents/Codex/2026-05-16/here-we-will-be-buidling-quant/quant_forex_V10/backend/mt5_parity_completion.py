from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.backtest_engine import run_backtest
from backend.mt5_parity_engine import run_mt5_parity_check
from backend.mt5_parity_packet import build_python_parity_packet
from backend.mt5_report_importer import import_mt5_report
from backend.mt5_tester_runner import run_mt5_strategy_tester


def _payload_candidate(payload: dict[str, Any], packet: dict[str, Any] | None = None) -> dict[str, Any]:
    candidate = dict((packet or {}).get("candidate") or {})
    for key in ["symbol", "timeframe", "start_date", "end_date", "regime_filter", "strategy_filter", "risk_percent", "rr", "initial_equity"]:
        candidate.setdefault(key, payload.get(key))
    return candidate


def _parity_has_keys(parity: dict[str, Any]) -> bool:
    warnings = " ".join(parity.get("warnings") or []).lower()
    if "matched by pyhash/pyidx" in warnings:
        return True
    checks = parity.get("checks") or []
    hash_check = next((check for check in checks if check.get("check") == "parity_hash_parity"), None)
    return bool(hash_check and hash_check.get("total", 0) > 0 and hash_check.get("passed"))


def _checklist(packet: dict[str, Any], tester: dict[str, Any] | None, parity: dict[str, Any] | None, report_supplied: bool, required_symbol: str, required_timeframe: str) -> list[dict[str, Any]]:
    candidate = packet.get("candidate", {})
    expected = int(packet.get("expected_trade_count") or 0)
    summary = (parity or {}).get("summary", {})
    has_keys = _parity_has_keys(parity or {})
    exact_count = bool(parity and summary.get("python_trade_count") == summary.get("mt5_trade_count") == summary.get("matched_trade_count"))
    tester_signal = bool((tester or {}).get("python_signal_source"))
    rows = [
        {
            "check": "EURUSD M15 focus window",
            "passed": str(candidate.get("symbol") or "").upper() == required_symbol.upper() and str(candidate.get("timeframe") or "").upper() == required_timeframe.upper(),
            "detail": f"Candidate is {candidate.get('symbol')}/{candidate.get('timeframe')}; recommended proof lane is {required_symbol}/{required_timeframe}.",
        },
        {"check": "Saved Python run exists", "passed": bool(packet.get("python_run_id")), "detail": f"Run ID: {packet.get('python_run_id') or '--'}"},
        {"check": "Python has expected trades", "passed": expected > 0, "detail": f"Expected Python trade rows: {expected}."},
        {"check": "MT5 config uses Python signal CSV", "passed": tester_signal, "detail": "EA must read the generated Python signal CSV so decisions are compared to the same source of truth."},
        {"check": "MT5 report or signal export supplied", "passed": report_supplied, "detail": "Paste/import MT5 tester output with PYIDX/PYHASH columns."},
        {"check": "Parity matched by PYIDX/PYHASH", "passed": has_keys, "detail": "Keyed matching avoids false pass from row-order matching."},
        {"check": "Trade count exact", "passed": exact_count, "detail": f"Python {summary.get('python_trade_count', '--')} / MT5 {summary.get('mt5_trade_count', '--')} / matched {summary.get('matched_trade_count', '--')}."},
        {"check": "All parity fields pass", "passed": bool(parity and parity.get("status") == "PASS"), "detail": f"Parity status: {(parity or {}).get('status', 'WAITING')}."},
    ]
    return rows


def _verdict(checks: list[dict[str, Any]], report_supplied: bool, parity: dict[str, Any] | None) -> str:
    if not report_supplied:
        return "WAITING_FOR_MT5_REPORT"
    if not parity:
        return "WAITING_FOR_PARITY_CHECK"
    required = {row["check"]: row["passed"] for row in checks}
    if required.get("All parity fields pass") and required.get("Parity matched by PYIDX/PYHASH") and required.get("Trade count exact"):
        return "PARITY_PROVEN"
    if parity.get("status") == "PASS":
        return "PASS_NOT_INSTITUTIONAL_KEYED"
    if parity.get("status") == "NO_DATA":
        return "NO_PARITY_DATA"
    return "PARITY_FAILED"


def _next_actions(verdict: str, checks: list[dict[str, Any]]) -> list[str]:
    failed = [row["check"] for row in checks if not row["passed"]]
    if verdict == "PARITY_PROVEN":
        return [
            "Parity proof is complete for this candidate. Next validate 1-Min OHLC vs Every Tick vs Real Ticks.",
            "Keep the packet hash and MT5 report import ID with the research notes.",
        ]
    if verdict == "WAITING_FOR_MT5_REPORT":
        return [
            "Run the generated MT5 Strategy Tester config using QuantForexV10_ResearchEA in Strategy Tester only.",
            "Keep UsePythonSignalCsv=true and RequirePythonSignalCsv=true.",
            "Paste the exported signal/deal rows with PYIDX/PYHASH into the report importer, then run completion again.",
        ]
    if "Parity matched by PYIDX/PYHASH" in failed:
        return [
            "Use the generated Python signal CSV and make the EA export PYIDX/PYHASH in the comment or report columns.",
            "Avoid accepting positional parity as proof.",
        ]
    if "Trade count exact" in failed:
        return ["Compare missing/extra rows. Usually this means MT5 did not read the same Python signal CSV or tester date/model differs."]
    return ["Review failed fields in the mismatch table and rerun with the same symbol, timeframe, date window, strategy, RR, and cost assumptions."]


def run_mt5_parity_completion(request: dict[str, Any]) -> dict[str, Any]:
    payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
    run_id = request.get("python_run_id") or payload.get("python_run_id")
    warnings: list[str] = []
    created_at = datetime.now(timezone.utc).isoformat()

    if not run_id:
        if not payload:
            raise ValueError("MT5 parity completion needs python_run_id or payload.")
        python_result = run_backtest(payload, persist=True)
        run_id = python_result.get("run_id")
        warnings.append("Created a saved Python backtest run from the supplied payload for parity proof.")
    if not run_id:
        raise ValueError("Could not resolve or create a saved Python run for parity.")

    packet = build_python_parity_packet(str(run_id))
    warnings.extend(packet.get("warnings") or [])
    payload = {**payload, **packet.get("candidate", {}), "python_run_id": str(run_id)}
    candidate = _payload_candidate(payload, packet)

    tester_run = None
    if bool(request.get("prepare_tester_config", True)):
        tester_request = {
            "payload": payload,
            "python_run_id": str(run_id),
            "use_python_signals": True,
            "copy_python_signals_to_common": True,
            "launch_terminal": bool(request.get("launch_terminal", False)),
            "wait_for_report": bool(request.get("wait_for_report", False)),
            "terminal_path": request.get("terminal_path"),
            "expert": request.get("expert") or "QuantForexV10_ResearchEA.ex5",
            "test_model": request.get("test_model") or "every_tick_real_ticks",
            "timeout_seconds": int(request.get("timeout_seconds") or 120),
            "shutdown_terminal": bool(request.get("shutdown_terminal", True)),
            "visual": bool(request.get("visual", False)),
            "max_deals_returned": int(request.get("max_deals_returned") or 500),
        }
        tester_run = run_mt5_strategy_tester(tester_request)
        warnings.extend(tester_run.get("warnings") or [])

    report_supplied = bool(request.get("mt5_import_id") or request.get("report_text"))
    imported = None
    import_id = request.get("mt5_import_id")
    if request.get("report_text"):
        imported = import_mt5_report(
            {
                "run_id": str(run_id),
                "report_text": request["report_text"],
                "file_name": request.get("file_name") or "pasted_mt5_parity_report.csv",
                "test_model": request.get("test_model") or "every_tick_real_ticks",
                "symbol": candidate.get("symbol"),
                "timeframe": candidate.get("timeframe"),
                "start_date": candidate.get("start_date"),
                "end_date": candidate.get("end_date"),
                "initial_equity": candidate.get("initial_equity") or 100000,
                "risk_percent": candidate.get("risk_percent") or 1.0,
                "max_deals_returned": int(request.get("max_deals_returned") or 5000),
            }
        )
        import_id = imported.get("import_id")

    parity = None
    if report_supplied:
        parity = run_mt5_parity_check(
            {
                "python_run_id": str(run_id),
                "mt5_import_id": import_id,
                "mt5_import": imported or {},
                "tolerances": request.get("tolerances") or {},
                "max_mismatches_returned": int(request.get("max_mismatches_returned") or 100),
            }
        )
        warnings.extend(parity.get("warnings") or [])

    required_symbol = str(request.get("required_symbol") or "EURUSD")
    required_timeframe = str(request.get("required_timeframe") or "M15")
    checks = _checklist(packet, tester_run, parity, report_supplied, required_symbol, required_timeframe)
    verdict = _verdict(checks, report_supplied, parity)

    return {
        "status": verdict,
        "created_at": created_at,
        "order_execution": False,
        "python_run_id": str(run_id),
        "candidate": candidate,
        "institutional_verdict": {
            "status": verdict,
            "proved": verdict == "PARITY_PROVEN",
            "reason": "Python and MT5 matched by PYIDX/PYHASH with exact trade count and passing fields." if verdict == "PARITY_PROVEN" else "Parity proof is not complete under keyed institutional rules.",
        },
        "checklist": checks,
        "packet": packet,
        "tester_run": tester_run,
        "mt5_import": imported,
        "parity_check": parity,
        "next_actions": _next_actions(verdict, checks),
        "warnings": warnings,
    }
