from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from backend.backtest_engine import run_backtest
from backend.mt5.mt5_client import build_mt5_backtest_bridge_response
from backend.mt5_parity_packet import write_python_signal_csv
from backend.mt5_report_importer import import_mt5_report


BASE_DIR = Path(__file__).resolve().parent
RUN_DIR = BASE_DIR / "data" / "mt5_tester_runs"
EA_SOURCE_PATH = BASE_DIR.parent / "mt5" / "Experts" / "QuantForexV10_ResearchEA.mq5"

MODEL_CODES = {
    "every_tick": 0,
    "one_min_ohlc": 1,
    "candle_close": 2,
    "open_prices_only": 2,
    "every_tick_real_ticks": 4,
}

TIMEFRAME_PERIODS = {
    "M1": "M1",
    "M5": "M5",
    "M15": "M15",
    "M30": "M30",
    "H1": "H1",
    "H4": "H4",
    "D1": "D1",
}


def _safe_name(value: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    return "".join(ch if ch in allowed else "_" for ch in value)[:80] or "mt5"


def _date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("-", ".")


def _set_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(_set_value(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _write_set_file(path: Path, ea_inputs: dict[str, Any]) -> None:
    lines = [f"{key}={_set_value(value)}" for key, value in sorted(ea_inputs.items()) if value is not None]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_ini_file(path: Path, payload: dict[str, Any], request: dict[str, Any], set_path: Path, report_path: Path) -> dict[str, Any]:
    mt5 = payload.get("mt5_backtest") if isinstance(payload.get("mt5_backtest"), dict) else {}
    test_model = str(mt5.get("test_model") or payload.get("mt5_test_model") or request.get("test_model") or "every_tick_real_ticks")
    requested_model_code = request.get("model_code")
    model_code = int(requested_model_code if requested_model_code is not None else MODEL_CODES.get(test_model, 4))
    expert = str(request.get("expert") or request.get("expert_name") or mt5.get("expert") or os.getenv("MT5_EXPERT") or "QuantForexV10_ResearchEA.ex5")
    deposit = float(payload.get("initial_equity") or request.get("initial_equity") or 100000)
    leverage = int(request.get("leverage") or mt5.get("leverage") or 100)
    currency = str(request.get("currency") or mt5.get("currency") or "USD")
    optimization = "true" if bool(request.get("optimization", False)) else "false"
    visual = "true" if bool(request.get("visual", False)) else "false"
    shutdown_terminal = "true" if bool(request.get("shutdown_terminal", True)) else "false"
    replace_report = "true"
    period = TIMEFRAME_PERIODS.get(str(payload.get("timeframe", "M15")).upper(), str(payload.get("timeframe", "M15")).upper())

    lines = [
        "[Tester]",
        f"Expert={expert}",
        f"ExpertParameters={set_path}",
        f"Symbol={payload.get('symbol')}",
        f"Period={period}",
        f"Model={model_code}",
        f"ExecutionMode={request.get('execution_mode', 0)}",
        f"Optimization={optimization}",
        f"Visual={visual}",
        f"FromDate={_date(payload.get('start_date'))}",
        f"ToDate={_date(payload.get('end_date'))}",
        f"ForwardMode={request.get('forward_mode', 0)}",
        f"Deposit={deposit}",
        f"Currency={currency}",
        f"Leverage={leverage}",
        f"Report={report_path}",
        f"ReplaceReport={replace_report}",
        f"ShutdownTerminal={shutdown_terminal}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "expert": expert,
        "test_model": test_model,
        "model_code": model_code,
        "model_code_note": "MT5 tester model codes vary by terminal/build. Override model_code in request if your terminal requires a different code.",
        "ea_source_path": str(EA_SOURCE_PATH),
        "compiled_ea_expected": expert,
        "compiled_ea_note": "Compile the mq5 source in MetaEditor and place the resulting .ex5 under the terminal MQL5/Experts path before launching the tester.",
        "report_path": str(report_path),
        "report_path_candidates": [str(candidate) for candidate in _report_candidates(report_path)],
        "set_path": str(set_path),
        "ini_path": str(path),
    }


def _report_candidates(report_path: Path) -> list[Path]:
    candidates = [report_path]
    if report_path.suffix.lower() == ".html":
        candidates.append(report_path.with_suffix(".htm"))
    elif report_path.suffix.lower() == ".htm":
        candidates.append(report_path.with_suffix(".html"))
    else:
        candidates.extend([report_path.with_suffix(".html"), report_path.with_suffix(".htm")])
    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def _find_report(report_path: Path) -> Path | None:
    for candidate in _report_candidates(report_path):
        try:
            if candidate.exists() and candidate.stat().st_size > 0:
                return candidate
        except OSError:
            continue
    return None


def _terminal_path(request: dict[str, Any]) -> Path | None:
    load_dotenv()
    raw = request.get("terminal_path") or os.getenv("MT5_TERMINAL_PATH") or os.getenv("MT5_PATH")
    if not raw:
        try:
            import MetaTrader5 as mt5  # type: ignore

            if mt5.initialize():
                info = mt5.terminal_info()
                terminal_dir = getattr(info, "path", None) if info else None
                if terminal_dir:
                    folder = Path(str(terminal_dir)).expanduser()
                    for name in ("terminal64.exe", "terminal.exe"):
                        candidate = folder / name
                        if candidate.exists():
                            return candidate
        except Exception:
            return None
        return None
    path = Path(str(raw)).expanduser()
    if path.is_dir():
        for name in ("terminal64.exe", "terminal.exe"):
            candidate = path / name
            if candidate.exists():
                return candidate
    return path


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _mt5_common_files_dir() -> Path | None:
    try:
        import MetaTrader5 as mt5  # type: ignore

        initialized = mt5.initialize()
        if not initialized:
            return None
        info = mt5.terminal_info()
        common = getattr(info, "commondata_path", None) if info else None
        if not common:
            return None
        folder = Path(str(common)).expanduser() / "Files"
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    except Exception:
        return None


def _python_signal_mode(request: dict[str, Any], payload: dict[str, Any]) -> bool:
    mt5 = payload.get("mt5_backtest") if isinstance(payload.get("mt5_backtest"), dict) else {}
    return _truthy(request.get("use_python_signals")) or _truthy(mt5.get("use_python_signals")) or _truthy(payload.get("use_python_signals"))


def _python_signal_build_enabled(request: dict[str, Any]) -> bool:
    if "build_python_signals" not in request:
        return True
    return _truthy(request.get("build_python_signals"))


def _prepare_python_signal_csv(request: dict[str, Any], payload: dict[str, Any], folder: Path) -> dict[str, Any] | None:
    if not _python_signal_mode(request, payload):
        return None
    run_id = request.get("python_run_id") or payload.get("python_run_id")
    if not run_id:
        if not _python_signal_build_enabled(request):
            return {
                "enabled": True,
                "status": "SKIPPED_NO_PYTHON_RUN_ID",
                "python_run_id": None,
                "note": (
                    "Python signal CSV mode is enabled, but build_python_signals=false and no python_run_id was supplied. "
                    "Tester config is still generated; run a Python backtest first or enable Build Python signal CSV for parity-source testing."
                ),
            }
        python_result = run_backtest(payload, persist=True)
        run_id = python_result.get("run_id")
        payload["python_run_id"] = run_id
    if not run_id:
        raise ValueError("Python signal mode needs a saved Python backtest run_id, but none could be created.")

    safe_run = _safe_name(str(run_id))
    signal_name = request.get("python_signal_file") or f"QuantForexV10_python_signals_{safe_run}.csv"
    written = write_python_signal_csv(str(run_id), folder, str(signal_name))
    common_copy_path = None
    common_dir = _mt5_common_files_dir() if _truthy(request.get("copy_python_signals_to_common", True)) else None
    if common_dir:
        common_copy_path = common_dir / written["file_name"]
        shutil.copyfile(written["file_path"], common_copy_path)

    written["python_run_id"] = str(run_id)
    written["common_file_path"] = str(common_copy_path) if common_copy_path else None
    written["mt5_file_open_mode"] = "FILE_COMMON"
    written["mt5_file_name"] = written["file_name"]
    written["note"] = (
        "Python signal source-of-truth mode is enabled. The EA will read this CSV and execute only Python-generated signals. "
        "If common_file_path is empty, copy file_path into the MT5 Common/Files folder before launching the tester."
    )
    return written


def run_mt5_strategy_tester(request: dict[str, Any]) -> dict[str, Any]:
    load_dotenv()
    payload = request.get("payload") if isinstance(request.get("payload"), dict) else request
    run_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    folder = RUN_DIR / run_id
    folder.mkdir(parents=True, exist_ok=True)

    python_signal_source = _prepare_python_signal_csv(request, payload, folder)
    bridge = build_mt5_backtest_bridge_response({"payload": payload})
    ea_inputs = bridge.get("ea_inputs_prepared", {})
    if python_signal_source and python_signal_source.get("mt5_file_name"):
        ea_inputs["UsePythonSignalCsv"] = True
        ea_inputs["PythonSignalCsvFile"] = python_signal_source["mt5_file_name"]
        ea_inputs["RequirePythonSignalCsv"] = True
        ea_inputs["WriteSignalCsv"] = True
    stem = "_".join(
        _safe_name(str(part))
        for part in [payload.get("symbol", "SYMBOL"), payload.get("timeframe", "TF"), payload.get("regime_filter", "ALL"), payload.get("strategy_filter", "ALL")]
    )
    set_path = folder / f"{stem}.set"
    ini_path = folder / f"{stem}_tester.ini"
    report_path = folder / f"{stem}_mt5_report.html"
    _write_set_file(set_path, ea_inputs)
    config = _write_ini_file(ini_path, payload, request, set_path, report_path)

    terminal = _terminal_path(request)
    command = [str(terminal), f"/config:{ini_path}"] if terminal else []
    launch_requested = bool(request.get("launch_terminal", True))
    result: dict[str, Any] = {
        "run_id": run_id,
        "created_at": created_at,
        "status": "CONFIG_READY",
        "order_execution": False,
        "payload_received": payload,
        "bridge": bridge,
        "tester_config": config,
        "terminal_path": str(terminal) if terminal else None,
        "command": command,
        "warnings": [],
        "report_import": None,
        "python_signal_source": python_signal_source,
    }
    safety = bridge.get("safety") if isinstance(bridge.get("safety"), dict) else {}
    result["warnings"].extend(safety.get("warnings", []))
    if python_signal_source and python_signal_source.get("status") == "SKIPPED_NO_PYTHON_RUN_ID":
        result["warnings"].append(python_signal_source["note"])
    elif python_signal_source and not python_signal_source.get("common_file_path"):
        result["warnings"].append(
            f"Python signal CSV was generated at {python_signal_source['file_path']}. Copy it to MT5 Common/Files as {python_signal_source['file_name']} before launch."
        )

    if not launch_requested:
        result["status"] = "CONFIG_READY_NOT_LAUNCHED"
        result["bridge"].setdefault("mt5_strategy_tester", {})["runner_layer_status"] = result["status"]
        result["warnings"].append("launch_terminal=false, so config files were generated but MT5 was not started.")
        return result
    if not terminal:
        result["status"] = "TERMINAL_PATH_MISSING"
        result["bridge"].setdefault("mt5_strategy_tester", {})["runner_layer_status"] = result["status"]
        result["warnings"].append("Set MT5_PATH or MT5_TERMINAL_PATH, or pass terminal_path, to launch MT5 Strategy Tester.")
        return result
    if not terminal.exists():
        result["status"] = "TERMINAL_NOT_FOUND"
        result["bridge"].setdefault("mt5_strategy_tester", {})["runner_layer_status"] = result["status"]
        result["warnings"].append(f"MT5 terminal was not found at: {terminal}")
        return result

    try:
        proc = subprocess.Popen(command, cwd=str(terminal.parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        result["process_id"] = proc.pid
        result["status"] = "TERMINAL_LAUNCHED"
        result["bridge"].setdefault("mt5_strategy_tester", {})["actual_tester_run_started"] = True
        result["bridge"].setdefault("mt5_strategy_tester", {})["runner_layer_status"] = result["status"]
    except Exception as exc:
        result["status"] = "LAUNCH_FAILED"
        result["bridge"].setdefault("mt5_strategy_tester", {})["runner_layer_status"] = result["status"]
        result["warnings"].append(str(exc))
        return result

    if bool(request.get("wait_for_report", False)):
        timeout = max(1, int(request.get("timeout_seconds", 120)))
        deadline = time.time() + timeout
        started_wait = time.time()
        found_report: Path | None = None
        while time.time() < deadline:
            found_report = _find_report(report_path)
            if found_report:
                break
            if proc.poll() is not None and time.time() > started_wait + 3:
                # MT5 may close quickly after generating a report; keep polling until timeout
                # because file writes can lag process exit on Windows.
                pass
            time.sleep(1)
        result["report_wait"] = {
            "timeout_seconds": timeout,
            "elapsed_seconds": round(time.time() - started_wait, 2),
            "process_exit_code": proc.poll(),
            "report_path_candidates": [str(candidate) for candidate in _report_candidates(report_path)],
            "report_found_path": str(found_report) if found_report else None,
        }
        if found_report:
            report_text = found_report.read_text(encoding="utf-8", errors="ignore")
            import_request = {
                "report_text": report_text,
                "file_name": found_report.name,
                "test_model": config["test_model"],
                "run_id": request.get("python_run_id") or request.get("run_id"),
                "symbol": payload.get("symbol"),
                "timeframe": payload.get("timeframe"),
                "start_date": payload.get("start_date"),
                "end_date": payload.get("end_date"),
                "initial_equity": payload.get("initial_equity", 100000),
                "risk_percent": payload.get("risk_percent", 1),
                "max_deals_returned": int(request.get("max_deals_returned", 500)),
            }
            try:
                result["report_import"] = import_mt5_report(import_request)
                result["report_found_path"] = str(found_report)
                result["status"] = "REPORT_IMPORTED"
                result["bridge"].setdefault("mt5_strategy_tester", {})["runner_layer_status"] = result["status"]
            except Exception as exc:
                result["status"] = "REPORT_FOUND_IMPORT_FAILED"
                result["bridge"].setdefault("mt5_strategy_tester", {})["runner_layer_status"] = result["status"]
                result["warnings"].append(f"MT5 report was created but import failed: {exc}")
        else:
            result["status"] = "TERMINAL_LAUNCHED_REPORT_NOT_FOUND"
            result["bridge"].setdefault("mt5_strategy_tester", {})["runner_layer_status"] = result["status"]
            result["warnings"].append(f"No report appeared within {timeout} seconds. Check MT5 tester journal and report path candidates.")

    return result
