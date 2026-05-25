from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from backend.backtest_engine import run_backtest
from backend.database import load_backtest, load_backtest_trades, load_mt5_report_import


PRICE_TOLERANCE_BY_SYMBOL = {
    "USDJPY": 0.001,
    "XAUUSD": 0.01,
}


def _num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number


def _time(value: Any) -> pd.Timestamp | None:
    if value is None or str(value).strip() == "":
        return None
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed


def _time_text(value: Any) -> str | None:
    parsed = _time(value)
    return parsed.isoformat() if parsed is not None else (str(value) if value else None)


def _parse_comment(comment: Any) -> dict[str, str]:
    text = str(comment or "").strip()
    if not text:
        return {}
    parts = [part.strip() for part in text.split("|") if part.strip()]
    result: dict[str, str] = {"comment": text}
    if parts and re.fullmatch(r"R\d{2}", parts[0], re.IGNORECASE):
        result["regime_id"] = parts[0].upper()
    if len(parts) > 1:
        result["strategy_id"] = parts[1].upper()
    for part in parts:
        upper = part.upper()
        if upper.startswith("PYIDX:"):
            result["parity_index"] = upper.split(":", 1)[1]
        if upper.startswith("PYHASH:"):
            result["parity_hash"] = upper.split(":", 1)[1].lower()
    return result


def _price_tolerance(symbol: str, tolerances: dict[str, Any]) -> float:
    if tolerances.get("price_tolerance") is not None:
        return float(tolerances["price_tolerance"])
    upper = str(symbol or "").upper()
    if upper in PRICE_TOLERANCE_BY_SYMBOL:
        return PRICE_TOLERANCE_BY_SYMBOL[upper]
    if upper.endswith("JPY"):
        return 0.001
    return 0.00001


def _normalize_python_trade(trade: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "python",
        "entry_time": _time_text(trade.get("entry_time")),
        "exit_time": _time_text(trade.get("exit_time")),
        "regime_id": str(trade.get("regime_id") or "").upper(),
        "regime_name": trade.get("regime_name"),
        "strategy_id": str(trade.get("strategy_id") or "").upper(),
        "strategy_name": trade.get("strategy_name"),
        "direction": str(trade.get("direction") or "").lower(),
        "entry": _num(trade.get("entry")),
        "sl": _num(trade.get("sl")),
        "tp": _num(trade.get("tp")),
        "exit_price": _num(trade.get("exit_price")),
        "result_R": _num(trade.get("result_R", trade.get("result_r"))),
        "profit": _num(trade.get("profit")),
        "parity_index": trade.get("parity_index"),
        "parity_hash": str(trade.get("parity_hash") or "").lower(),
        "raw": trade,
    }


def _python_trade_hash(row: dict[str, Any], index: int) -> str:
    text = "|".join(
        [
            str(index),
            str(row.get("entry_time") or ""),
            str(row.get("regime_id") or "").upper(),
            str(row.get("strategy_id") or "").upper(),
            str(row.get("direction") or "").lower(),
            f"{_num(row.get('entry')):.8f}",
            f"{_num(row.get('sl')):.8f}",
            f"{_num(row.get('tp')):.8f}",
        ]
    )
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _normalize_python_trades(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for idx, trade in enumerate(trades):
        row = dict(trade)
        row.setdefault("parity_index", idx)
        row.setdefault("parity_hash", _python_trade_hash(row, idx))
        normalized.append(_normalize_python_trade(row))
    return normalized


def _normalize_mt5_trade(trade: dict[str, Any]) -> dict[str, Any]:
    comment_bits = _parse_comment(trade.get("comment"))
    raw = trade.get("raw") if isinstance(trade.get("raw"), dict) else {}
    parity_index = trade.get("parity_index", raw.get("parity_index", comment_bits.get("parity_index")))
    try:
        parity_index = int(parity_index) if parity_index not in (None, "") else None
    except (TypeError, ValueError):
        parity_index = None
    return {
        "source": "mt5",
        "entry_time": _time_text(trade.get("entry_time") or raw.get("entry_time") or trade.get("time")),
        "exit_time": _time_text(trade.get("exit_time") or raw.get("exit_time") or trade.get("time")),
        "regime_id": str(trade.get("regime_id") or raw.get("regime_id") or comment_bits.get("regime_id") or "").upper(),
        "regime_name": trade.get("regime_name") or raw.get("regime_name"),
        "strategy_id": str(trade.get("strategy_id") or raw.get("strategy_id") or comment_bits.get("strategy_id") or "").upper(),
        "strategy_name": trade.get("strategy_name") or raw.get("strategy_name"),
        "direction": str(trade.get("direction") or raw.get("direction") or "").lower(),
        "entry": _num(trade.get("entry", raw.get("entry", trade.get("price")))),
        "sl": _num(trade.get("sl", raw.get("sl"))),
        "tp": _num(trade.get("tp", raw.get("tp"))),
        "exit_price": _num(trade.get("exit_price", raw.get("exit_price", trade.get("price")))),
        "result_R": _num(trade.get("result_R", trade.get("result_r", raw.get("result_R", raw.get("result_r"))))),
        "profit": _num(trade.get("profit", raw.get("profit"))),
        "parity_index": parity_index,
        "parity_hash": str(trade.get("parity_hash") or raw.get("parity_hash") or comment_bits.get("parity_hash") or "").lower(),
        "comment": trade.get("comment") or raw.get("comment") or comment_bits.get("comment"),
        "raw": trade,
    }


def _trade_match_key(trade: dict[str, Any]) -> tuple[str, Any] | None:
    if trade.get("parity_hash"):
        return ("hash", trade["parity_hash"])
    if trade.get("parity_index") is not None:
        return ("index", trade["parity_index"])
    return None


def _matched_trade_pairs(python_trades: list[dict[str, Any]], mt5_trades: list[dict[str, Any]]) -> tuple[list[tuple[int, dict[str, Any], dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    mt5_by_key: dict[tuple[str, Any], dict[str, Any]] = {}
    duplicate_keys: set[tuple[str, Any]] = set()
    for mt5_trade in mt5_trades:
        key = _trade_match_key(mt5_trade)
        if key is None:
            continue
        if key in mt5_by_key:
            duplicate_keys.add(key)
        mt5_by_key[key] = mt5_trade
    pairs: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    missing_python: list[dict[str, Any]] = []
    used_mt5_ids: set[int] = set()
    keyed_python = 0
    if mt5_by_key:
        for idx, py_trade in enumerate(python_trades):
            key = _trade_match_key(py_trade)
            if key is None:
                missing_python.append(py_trade)
                continue
            keyed_python += 1
            mt5_trade = mt5_by_key.get(key)
            if mt5_trade is None:
                missing_python.append(py_trade)
            else:
                pairs.append((idx, py_trade, mt5_trade))
                used_mt5_ids.add(id(mt5_trade))
        extra_mt5 = [trade for trade in mt5_trades if id(trade) not in used_mt5_ids]
        if duplicate_keys:
            warnings.append(f"Duplicate MT5 parity keys found: {len(duplicate_keys)}. Check EA export uniqueness.")
        if keyed_python:
            warnings.append("Parity matched by PYHASH/PYIDX keys from the Python parity packet.")
        else:
            warnings.append("MT5 report has parity keys but Python trades do not. Falling back would be unsafe; use /api/backtest/{run_id}/mt5-parity-packet.")
        return pairs, missing_python, extra_mt5, warnings

    matched = min(len(python_trades), len(mt5_trades))
    warnings.append("No MT5 parity keys found; falling back to positional comparison. Export PYIDX/PYHASH from the EA for institutional-grade parity.")
    return [(idx, python_trades[idx], mt5_trades[idx]) for idx in range(matched)], python_trades[matched:], mt5_trades[matched:], warnings


def _get_python_trades(request: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    warnings: list[str] = []
    if isinstance(request.get("python_trades"), list):
        return _normalize_python_trades(request["python_trades"]), request.get("python_result") or {}, warnings
    run_id = request.get("python_run_id") or request.get("run_id")
    if run_id:
        stored = load_backtest(str(run_id))
        if stored is None:
            warnings.append(f"Python backtest run_id not found: {run_id}")
        else:
            return _normalize_python_trades(load_backtest_trades(str(run_id))), stored, warnings
    if isinstance(request.get("python_result"), dict):
        result = request["python_result"]
        return _normalize_python_trades(result.get("trades", [])), result, warnings
    payload = request.get("payload")
    if isinstance(payload, dict):
        result = run_backtest(payload, persist=False)
        warnings.append("Python backtest was run on demand for parity comparison.")
        return _normalize_python_trades(result.get("trades", [])), result, warnings
    return [], {}, warnings


def _get_mt5_trades(request: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    warnings: list[str] = []
    if isinstance(request.get("mt5_trades"), list):
        return [_normalize_mt5_trade(t) for t in request["mt5_trades"]], request.get("mt5_import") or {}, warnings
    if isinstance(request.get("mt5_import"), dict):
        imported = request["mt5_import"]
        return [_normalize_mt5_trade(t) for t in imported.get("deals", [])], imported, warnings
    import_id = request.get("mt5_import_id")
    if import_id:
        imported = load_mt5_report_import(str(import_id))
        if imported is None:
            warnings.append(f"MT5 import_id not found: {import_id}")
        else:
            warnings.append("MT5 report imports usually contain deals, not full Python-style SL/TP fields; price/SL/TP parity is best when the EA signal CSV is supplied.")
            return [_normalize_mt5_trade(t) for t in imported.get("deals", [])], imported, warnings
    return [], {}, warnings


def _compare_value(field: str, py: dict[str, Any], mt5: dict[str, Any], tolerance: float = 0.0) -> dict[str, Any]:
    py_value = py.get(field)
    mt5_value = mt5.get(field)
    if isinstance(py_value, (int, float)) or isinstance(mt5_value, (int, float)):
        delta = _num(mt5_value) - _num(py_value)
        passed = abs(delta) <= tolerance
        return {"field": field, "python": py_value, "mt5": mt5_value, "delta": round(delta, 8), "passed": passed, "tolerance": tolerance}
    passed = str(py_value or "") == str(mt5_value or "")
    return {"field": field, "python": py_value, "mt5": mt5_value, "passed": passed}


def _compare_time(field: str, py: dict[str, Any], mt5: dict[str, Any], tolerance_seconds: int) -> dict[str, Any]:
    py_time = _time(py.get(field))
    mt5_time = _time(mt5.get(field))
    if py_time is None or mt5_time is None:
        return {"field": field, "python": py.get(field), "mt5": mt5.get(field), "passed": py_time == mt5_time}
    delta = abs((mt5_time - py_time).total_seconds())
    return {"field": field, "python": py_time.isoformat(), "mt5": mt5_time.isoformat(), "delta_seconds": delta, "passed": delta <= tolerance_seconds, "tolerance_seconds": tolerance_seconds}


def run_mt5_parity_check(request: dict[str, Any]) -> dict[str, Any]:
    tolerances = request.get("tolerances") if isinstance(request.get("tolerances"), dict) else {}
    payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
    symbol = str(request.get("symbol") or payload.get("symbol") or "").upper()
    price_tol = _price_tolerance(symbol, tolerances)
    result_tol = float(tolerances.get("result_R_tolerance", 0.05))
    profit_tol = float(tolerances.get("profit_tolerance", 1.0))
    time_tol = int(tolerances.get("time_tolerance_seconds", 60))
    max_mismatches = int(request.get("max_mismatches_returned") or 50)

    python_trades, python_result, py_warnings = _get_python_trades(request)
    mt5_trades, mt5_import, mt5_warnings = _get_mt5_trades(request)
    warnings = py_warnings + mt5_warnings
    if not python_trades:
        warnings.append("No Python trades available for parity comparison.")
    if not mt5_trades:
        warnings.append("No MT5 trades/deals available for parity comparison.")

    pairs, missing_mt5, extra_mt5, match_warnings = _matched_trade_pairs(python_trades, mt5_trades)
    warnings.extend(match_warnings)
    matched = len(pairs)
    mismatches: list[dict[str, Any]] = []
    field_totals: dict[str, dict[str, int]] = {}

    def record(field_result: dict[str, Any]) -> None:
        field = field_result["field"]
        field_totals.setdefault(field, {"passed": 0, "total": 0})
        field_totals[field]["total"] += 1
        if field_result["passed"]:
            field_totals[field]["passed"] += 1

    for idx, py, mt5 in pairs:
        checks = [
            _compare_value("parity_hash", py, mt5) if py.get("parity_hash") and mt5.get("parity_hash") else {"field": "parity_hash", "passed": True},
            _compare_value("regime_id", py, mt5),
            _compare_value("strategy_id", py, mt5),
            _compare_time("entry_time", py, mt5, time_tol),
            _compare_value("direction", py, mt5),
            _compare_value("entry", py, mt5, price_tol),
            _compare_value("sl", py, mt5, price_tol),
            _compare_value("tp", py, mt5, price_tol),
            _compare_value("result_R", py, mt5, result_tol),
            _compare_value("profit", py, mt5, profit_tol),
        ]
        for check in checks:
            record(check)
        failed = [check for check in checks if not check["passed"]]
        if failed and len(mismatches) < max_mismatches:
            mismatches.append(
                {
                    "index": idx,
                    "python_trade": py,
                    "mt5_trade": mt5,
                    "failed_fields": failed,
                }
            )

    for idx, trade in enumerate(missing_mt5[:max_mismatches], start=matched):
        mismatches.append({"index": idx, "type": "MISSING_MT5_TRADE", "python_trade": trade})
    for idx, trade in enumerate(extra_mt5[:max_mismatches], start=matched):
        mismatches.append({"index": idx, "type": "EXTRA_MT5_TRADE", "mt5_trade": trade})

    checks = [
        {
            "check": "trade_count",
            "passed": len(python_trades) == len(mt5_trades),
            "python": len(python_trades),
            "mt5": len(mt5_trades),
            "delta": len(mt5_trades) - len(python_trades),
        }
    ]
    for field, totals in field_totals.items():
        total = totals["total"]
        passed = totals["passed"]
        checks.append({"check": f"{field}_parity", "passed": passed == total, "matched": passed, "total": total, "match_rate": round(passed / total, 4) if total else 0.0})

    failed_checks = [check for check in checks if not check["passed"]]
    missing_count = len(missing_mt5)
    extra_count = len(extra_mt5)
    failed_field_count = sum(1 for item in mismatches if item.get("failed_fields"))
    total_failures = len(failed_checks) + failed_field_count + missing_count + extra_count
    if not python_trades or not mt5_trades:
        status = "NO_DATA"
    elif total_failures == 0:
        status = "PASS"
    elif len(python_trades) == len(mt5_trades) and failed_field_count <= max(1, int(0.05 * matched)):
        status = "WARN"
    else:
        status = "FAIL"

    return {
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol or None,
        "payload": payload,
        "summary": {
            "python_trade_count": len(python_trades),
            "mt5_trade_count": len(mt5_trades),
            "matched_trade_count": matched,
            "missing_mt5_trade_count": missing_count,
            "extra_mt5_trade_count": extra_count,
            "mismatch_count": len(mismatches),
            "pass_rate": round((matched - failed_field_count) / matched, 4) if matched else 0.0,
            "price_tolerance": price_tol,
            "time_tolerance_seconds": time_tol,
            "result_R_tolerance": result_tol,
            "profit_tolerance": profit_tol,
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "mismatches": mismatches[:max_mismatches],
        "warnings": warnings,
        "python_context": {
            "run_id": request.get("python_run_id") or request.get("run_id") or python_result.get("run_id"),
            "summary": python_result.get("summary", {}),
        },
        "mt5_context": {
            "import_id": request.get("mt5_import_id") or mt5_import.get("import_id"),
            "test_model": mt5_import.get("test_model"),
            "summary": mt5_import.get("summary", {}),
        },
    }
