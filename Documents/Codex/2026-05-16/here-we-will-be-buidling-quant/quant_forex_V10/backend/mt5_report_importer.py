from __future__ import annotations

import io
import json
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from backend.database import load_backtest, load_backtest_trades, save_mt5_report_import


MODEL_NAMES = {
    "one_min_ohlc": "1-Min OHLC",
    "every_tick": "Every Tick",
    "every_tick_real_ticks": "Real Ticks",
}
MODEL_ORDER = ["one_min_ohlc", "every_tick", "every_tick_real_ticks"]

COLUMN_ALIASES = {
    "time": {"time", "date", "datetime", "open time", "close time"},
    "entry_time": {"entry time", "entry_time", "open time"},
    "exit_time": {"exit time", "exit_time", "close time"},
    "symbol": {"symbol"},
    "timeframe": {"timeframe", "period"},
    "regime_id": {"regime", "regime id", "regime_id"},
    "strategy_id": {"strategy", "strategy id", "strategy_id"},
    "parity_index": {"parity index", "parity_index", "pyidx", "python index"},
    "parity_hash": {"parity hash", "parity_hash", "pyhash", "python hash"},
    "deal_type": {"type", "deal type", "entry type", "operation"},
    "direction": {"direction", "side", "cmd"},
    "volume": {"volume", "lots", "volume in lots"},
    "price": {"price", "open price", "close price"},
    "entry": {"entry price", "entry_price", "entry"},
    "sl": {"sl", "stop loss", "stop_loss"},
    "tp": {"tp", "take profit", "take_profit"},
    "exit_price": {"exit price", "exit_price"},
    "result_r": {"result r", "result_r", "r", "result in r"},
    "initial_risk": {"initial risk", "initial_risk", "risk amount", "risk_amount", "risk money", "risk_money"},
    "alpha_score": {"alpha", "alpha score", "alpha_score"},
    "pattern_score": {"pattern score", "pattern_score"},
    "final_score": {"final score", "final_score"},
    "patterns_detected": {"patterns", "patterns detected", "patterns_detected", "pattern summary", "pattern_summary", "pattern details", "pattern_details"},
    "setup_reason": {"reason", "setup reason", "setup_reason", "decision reason", "decision_reason"},
    "entry_reason": {"entry reason", "entry_reason", "signal reason", "signal_reason"},
    "commission": {"commission", "comm"},
    "swap": {"swap"},
    "profit": {"profit", "p/l", "pl", "net profit", "result"},
    "balance": {"balance", "equity"},
    "comment": {"comment", "comments"},
}


def _clean_column(name: Any) -> str:
    return " ".join(str(name or "").strip().lower().replace("\n", " ").split())


def _canonical_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for col in df.columns:
        clean = _clean_column(col)
        for target, aliases in COLUMN_ALIASES.items():
            if clean in aliases:
                rename[col] = target
                break
    return df.rename(columns=rename)


def _numeric(value: Any) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    text = text.replace(",", "")
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    try:
        return float(text)
    except ValueError:
        return 0.0


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    return str(value).strip() != ""


def _text(value: Any) -> str:
    return "" if not _has_value(value) else str(value).strip()


def _parse_patterns(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        parsed = []
        for item in value:
            if isinstance(item, dict):
                parsed.append(item)
            elif _has_value(item):
                parsed.append({"pattern_id": str(item).strip(), "score": 0})
        return parsed
    text = _text(value)
    if not text:
        return []
    try:
        loaded = json.loads(text)
        return _parse_patterns(loaded)
    except Exception:
        pass
    labels = [
        item.strip()
        for item in re.split(r"[+|;,]", text)
        if item.strip() and item.strip().upper() not in {"NONE", "NA", "N/A", "--"}
    ]
    return [{"pattern_id": label, "score": 0} for label in labels]


def _patterns_text(patterns: list[dict[str, Any]]) -> str:
    return "+".join(str(item.get("pattern_id") or item.get("pattern_name") or "").strip() for item in patterns if item)


def _comment_metadata(comment: str) -> dict[str, Any]:
    text = _text(comment)
    meta: dict[str, Any] = {}
    if not text:
        return meta
    tokens = [token.strip() for token in re.split(r"[|;,\s]+", text) if token.strip()]
    for token in tokens:
        upper = token.upper()
        if re.fullmatch(r"R\d{2}", upper):
            meta.setdefault("regime_id", upper)
        elif re.fullmatch(r"[A-Z]{1,4}\d{1,2}", upper) and not upper.startswith("PY"):
            meta.setdefault("strategy_id", upper)
        elif re.fullmatch(r"A-?\d+(\.\d+)?", upper):
            meta.setdefault("alpha_score", _numeric(upper[1:]))
        elif re.fullmatch(r"P-?\d+(\.\d+)?", upper):
            meta.setdefault("pattern_score", _numeric(upper[1:]))
        elif upper.startswith("PYIDX:"):
            meta.setdefault("parity_index", int(_numeric(upper.split(":", 1)[1])))
        elif upper.startswith("PYHASH:"):
            meta.setdefault("parity_hash", token.split(":", 1)[1])
        elif upper.startswith("FS:") or upper.startswith("FINAL:"):
            meta.setdefault("final_score", _numeric(token.split(":", 1)[1]))
    return meta


def _parse_time(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = pd.to_datetime(value, utc=True)
        if pd.isna(parsed):
            return None
        return parsed.isoformat()
    except Exception:
        return str(value)


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _read_tables(report_text: str) -> list[pd.DataFrame]:
    text = report_text.strip()
    if not text:
        return []
    tables: list[pd.DataFrame] = []
    if "<table" in text.lower() or "<html" in text.lower():
        try:
            tables.extend(pd.read_html(io.StringIO(text)))
        except ValueError:
            pass
    for sep in [None, "\t", ";", ","]:
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep, engine="python")
            if len(df.columns) >= 2:
                tables.append(df)
                break
        except Exception:
            continue
    return tables


def _select_deal_table(tables: list[pd.DataFrame]) -> pd.DataFrame:
    best = pd.DataFrame()
    best_score = -1
    for table in tables:
        df = _canonical_columns(table.copy())
        columns = set(df.columns)
        score = 0
        if "profit" in columns:
            score += 4
        if "parity_hash" in columns or "parity_index" in columns:
            score += 4
        if {"entry", "sl", "tp"} & columns:
            score += 2
        if "time" in columns:
            score += 2
        if "entry_time" in columns:
            score += 2
        if "deal_type" in columns or "direction" in columns:
            score += 2
        if "price" in columns:
            score += 1
        if "volume" in columns:
            score += 1
        if score > best_score:
            best = df
            best_score = score
    if best.empty or best_score < 4:
        raise ValueError("Could not find a Strategy Tester deals/table or parity signal section with at least profit or parity columns.")
    return best


def _direction(row: pd.Series) -> str:
    combined = f"{row.get('direction', '')} {row.get('deal_type', '')}".lower()
    if "buy" in combined or "long" in combined:
        return "long"
    if "sell" in combined or "short" in combined:
        return "short"
    return ""


def _deal_type(row: pd.Series) -> str:
    return str(row.get("deal_type") or row.get("direction") or "").strip()


def _deal_rows(df: pd.DataFrame, fallback_symbol: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for _, row in df.iterrows():
        profit = _numeric(row.get("profit"))
        commission = _numeric(row.get("commission"))
        swap = _numeric(row.get("swap"))
        result_r_raw = row.get("result_r")
        initial_risk = _numeric(row.get("initial_risk"))
        comment = str(row.get("comment") or "").strip()
        comment_meta = _comment_metadata(comment)
        patterns = _parse_patterns(row.get("patterns_detected"))
        alpha_score = _numeric(row.get("alpha_score")) or float(comment_meta.get("alpha_score") or 0)
        pattern_score = _numeric(row.get("pattern_score")) or float(comment_meta.get("pattern_score") or 0)
        final_score_raw = row.get("final_score")
        final_score = _numeric(final_score_raw) or float(comment_meta.get("final_score") or 0)
        if not final_score and (alpha_score or pattern_score):
            final_score = alpha_score + pattern_score
        deal = {
            "time": _parse_time(row.get("time")),
            "entry_time": _parse_time(row.get("entry_time") or row.get("time")),
            "exit_time": _parse_time(row.get("exit_time") or row.get("time")),
            "symbol": str(row.get("symbol") or fallback_symbol or "").strip(),
            "timeframe": str(row.get("timeframe") or "").strip(),
            "regime_id": str(row.get("regime_id") or comment_meta.get("regime_id") or "").strip().upper(),
            "strategy_id": str(row.get("strategy_id") or comment_meta.get("strategy_id") or "").strip().upper(),
            "parity_index": int(_numeric(row.get("parity_index"))) if str(row.get("parity_index") or "").strip() else comment_meta.get("parity_index"),
            "parity_hash": str(row.get("parity_hash") or comment_meta.get("parity_hash") or "").strip(),
            "deal_type": _deal_type(row),
            "direction": _direction(row),
            "volume": _numeric(row.get("volume")),
            "price": _numeric(row.get("price")),
            "entry": _numeric(row.get("entry", row.get("price"))),
            "sl": _numeric(row.get("sl")),
            "tp": _numeric(row.get("tp")),
            "exit_price": _numeric(row.get("exit_price", row.get("price"))),
            "initial_risk": initial_risk,
            "result_R": _numeric(result_r_raw),
            "result_R_source": "ea_exported_result_R" if _has_value(result_r_raw) else "",
            "alpha_score": alpha_score,
            "pattern_score": pattern_score,
            "final_score": final_score,
            "final_score_source": "imported_final_score" if _has_value(final_score_raw) else "alpha_plus_pattern_estimate" if final_score else "",
            "patterns_detected": patterns,
            "patterns_text": _patterns_text(patterns),
            "setup_reason": _text(row.get("setup_reason") or row.get("entry_reason")),
            "commission": commission,
            "swap": swap,
            "profit": profit,
            "balance": _numeric(row.get("balance")),
            "comment": comment,
            "raw": {str(k): _jsonable(v) for k, v in row.to_dict().items()},
        }
        if profit or commission or swap or deal["deal_type"] or deal["direction"] or deal["parity_hash"] or deal["entry"] or deal["sl"] or deal["tp"]:
            rows.append(deal)
    return rows


def _max_drawdown(values: list[float]) -> float:
    peak = 0.0
    cumulative = 0.0
    max_dd = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    return max_dd


def _max_losing_streak(values: list[float]) -> int:
    current = 0
    worst = 0
    for value in values:
        if value < 0:
            current += 1
            worst = max(worst, current)
        else:
            current = 0
    return worst


def _profit_factor(values: list[float]) -> float:
    gross_profit = sum(v for v in values if v > 0)
    gross_loss = abs(sum(v for v in values if v < 0))
    if gross_loss == 0:
        return 999.0 if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def _enrich_deals_from_python_run(deals: list[dict[str, Any]], run_id: str | None) -> dict[str, Any]:
    if not run_id:
        return {"matched": 0, "source": "none"}
    try:
        python_trades = load_backtest_trades(run_id)
    except Exception:
        return {"matched": 0, "source": "load_failed"}
    by_hash = {str(t.get("parity_hash") or ""): t for t in python_trades if t.get("parity_hash")}
    by_index = {int(t.get("parity_index")): t for t in python_trades if t.get("parity_index") is not None}
    matched = 0
    for deal in deals:
        source = None
        parity_hash = str(deal.get("parity_hash") or "")
        if parity_hash and parity_hash in by_hash:
            source = by_hash[parity_hash]
        elif deal.get("parity_index") is not None:
            source = by_index.get(int(deal["parity_index"]))
        if not source:
            continue
        matched += 1
        deal["python_signal_matched"] = True
        deal["python_expected_result_R"] = source.get("result_R")
        deal["python_expected_profit"] = source.get("profit")
        text_keys = {"regime_id", "strategy_id", "direction"}
        for key in ["regime_id", "strategy_id", "direction", "entry", "sl", "tp", "initial_risk", "alpha_score", "pattern_score", "final_score"]:
            missing = not _has_value(deal.get(key))
            zero_numeric = key not in text_keys and _numeric(deal.get(key)) == 0
            if (missing or zero_numeric) and _has_value(source.get(key)):
                deal[key] = source.get(key)
        source_patterns = source.get("patterns_detected")
        if not deal.get("patterns_detected") and source_patterns:
            deal["patterns_detected"] = _parse_patterns(source_patterns)
            deal["patterns_text"] = _patterns_text(deal["patterns_detected"])
        if not deal.get("setup_reason"):
            deal["setup_reason"] = source.get("entry_reason") or source.get("reason") or ""
        if not deal.get("final_score_source") and _has_value(source.get("final_score")):
            deal["final_score_source"] = "python_signal_final_score"
    return {"matched": matched, "source": "saved_python_backtest_trades", "available": len(python_trades)}


def _summary(deals: list[dict[str, Any]], initial_equity: float, risk_percent: float) -> dict[str, Any]:
    realized = [d for d in deals if float(d.get("profit") or 0) != 0]
    profits = [float(d.get("profit") or 0) for d in realized]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    trade_count = len(profits)
    win_rate = len(wins) / trade_count if trade_count else 0.0
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    risk_amount = initial_equity * risk_percent / 100 if initial_equity and risk_percent else 0.0
    approx_r = [p / risk_amount for p in profits] if risk_amount else []
    result_r: list[float] = []
    exact_r_count = 0
    result_r_sources: list[str] = []
    for deal in realized:
        profit = float(deal.get("profit") or 0)
        if deal.get("result_R_source") == "ea_exported_result_R":
            result_r.append(float(deal.get("result_R") or 0))
            exact_r_count += 1
            result_r_sources.append("ea_exported_result_R")
            continue
        initial_risk = float(deal.get("initial_risk") or 0)
        if initial_risk > 0:
            value = profit / initial_risk
            deal["result_R"] = value
            deal["result_R_source"] = "ea_exported_initial_risk"
            result_r.append(value)
            exact_r_count += 1
            result_r_sources.append("ea_exported_initial_risk")
            continue
        if risk_amount:
            value = profit / risk_amount
            deal["result_R"] = value
            deal["result_R_source"] = "account_risk_approximation"
            result_r.append(value)
            result_r_sources.append("account_risk_approximation")
    if "ea_exported_result_R" in result_r_sources:
        result_r_source = "ea_exported_result_R"
    elif "ea_exported_initial_risk" in result_r_sources:
        result_r_source = "ea_exported_initial_risk"
    elif "account_risk_approximation" in result_r_sources:
        result_r_source = "account_risk_approximation"
    else:
        result_r_source = "unavailable"
    alpha_values = [float(d.get("alpha_score") or 0) for d in realized if float(d.get("alpha_score") or 0) != 0]
    pattern_values = [float(d.get("pattern_score") or 0) for d in realized if float(d.get("pattern_score") or 0) != 0]
    final_values = [float(d.get("final_score") or 0) for d in realized if float(d.get("final_score") or 0) != 0]
    pattern_counter: dict[str, int] = {}
    for deal in realized:
        for pattern in deal.get("patterns_detected") or []:
            pid = str(pattern.get("pattern_id") or pattern.get("pattern_name") or "").strip()
            if pid:
                pattern_counter[pid] = pattern_counter.get(pid, 0) + 1
    return {
        "raw_deal_rows": len(deals),
        "trade_count": trade_count,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(win_rate, 4),
        "net_profit": round(sum(profits), 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(_profit_factor(profits), 4),
        "average_profit": round(float(np.mean(profits)), 2) if profits else 0.0,
        "average_win": round(float(np.mean(wins)), 2) if wins else 0.0,
        "average_loss": round(float(np.mean(losses)), 2) if losses else 0.0,
        "max_drawdown_currency": round(_max_drawdown(profits), 2),
        "max_losing_streak": _max_losing_streak(profits),
        "roi_percent": round((sum(profits) / initial_equity) * 100, 4) if initial_equity else 0.0,
        "total_R": round(sum(result_r), 4) if result_r else 0.0,
        "expectancy_R": round(float(np.mean(result_r)), 4) if result_r else 0.0,
        "max_drawdown_R": round(_max_drawdown(result_r), 4) if result_r else 0.0,
        "profit_factor_R": round(_profit_factor(result_r), 4) if result_r else 0.0,
        "exact_r_count": exact_r_count,
        "result_r_source": result_r_source,
        "approx_total_R": round(sum(approx_r), 4) if approx_r else 0.0,
        "approx_expectancy_R": round(float(np.mean(approx_r)), 4) if approx_r else 0.0,
        "approx_max_drawdown_R": round(_max_drawdown(approx_r), 4) if approx_r else 0.0,
        "average_alpha_score": round(float(np.mean(alpha_values)), 2) if alpha_values else 0.0,
        "average_pattern_score": round(float(np.mean(pattern_values)), 2) if pattern_values else 0.0,
        "average_final_score": round(float(np.mean(final_values)), 2) if final_values else 0.0,
        "pattern_detail_rows": sum(1 for d in realized if d.get("patterns_detected")),
        "top_patterns": sorted(
            [{"pattern_id": key, "count": value} for key, value in pattern_counter.items()],
            key=lambda item: item["count"],
            reverse=True,
        )[:10],
        "result_r_note": "R values use EA-exported result_R first, EA-exported initial_risk second, and account-risk approximation only when exact risk columns are missing.",
    }


def _comparison(
    run_id: str | None,
    mt5_summary: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    model_name = MODEL_NAMES.get(model, model)
    row = {
        "model": model,
        "model_name": model_name,
        "trade_count": mt5_summary.get("trade_count", 0),
        "win_rate": mt5_summary.get("win_rate", 0),
        "profit_factor": mt5_summary.get("profit_factor", 0),
        "expectancy_R": mt5_summary.get("expectancy_R", mt5_summary.get("approx_expectancy_R", 0)),
        "net_profit": mt5_summary.get("net_profit", 0),
        "status": "IMPORTED",
        "source": "MT5 Strategy Tester imported report",
    }
    if run_id:
        python_run = load_backtest(run_id)
        if python_run:
            py_summary = python_run.get("summary", {})
            row["python_trade_count"] = py_summary.get("total_trades", 0)
            row["python_profit_factor"] = py_summary.get("profit_factor", 0)
            row["python_expectancy_R"] = py_summary.get("expectancy_R", 0)
            row["trade_count_delta"] = int(mt5_summary.get("trade_count", 0) or 0) - int(py_summary.get("total_trades", 0) or 0)
            row["profit_factor_delta"] = round(float(mt5_summary.get("profit_factor", 0) or 0) - float(py_summary.get("profit_factor", 0) or 0), 4)
            row["expectancy_R_delta"] = round(float(mt5_summary.get("expectancy_R", mt5_summary.get("approx_expectancy_R", 0)) or 0) - float(py_summary.get("expectancy_R", 0) or 0), 4)
            row["status"] = "IMPORTED_MATCHED_RUN"
    return row


def import_mt5_report(request: dict[str, Any]) -> dict[str, Any]:
    report_text = str(request.get("report_text") or "")
    tables = _read_tables(report_text)
    if not tables:
        raise ValueError("Report text is empty or not readable as CSV/TSV/HTML table.")
    df = _select_deal_table(tables)
    symbol = request.get("symbol") or None
    deals = _deal_rows(df, symbol)
    if not deals:
        raise ValueError("No deal rows were found in the imported MT5 report.")

    run_id = request.get("run_id") or None
    if run_id and not symbol:
        python_run = load_backtest(run_id)
        if python_run:
            symbol = python_run.get("request", {}).get("symbol")
    python_enrichment = _enrich_deals_from_python_run(deals, run_id)
    initial_equity = float(request.get("initial_equity") or 100000)
    risk_percent = float(request.get("risk_percent") or 1.0)
    test_model = str(request.get("test_model") or "every_tick_real_ticks")
    summary = _summary(deals, initial_equity, risk_percent)
    comparison_row = _comparison(run_id, summary, test_model)
    warnings = [
        "MT5 report import reconciles tester results; it does not run MT5 Strategy Tester automatically.",
    ]
    if summary.get("result_r_source") == "account_risk_approximation":
        warnings.append("R values are approximated because the MT5 report did not include result_R or initial_risk columns.")
    elif summary.get("result_r_source") == "unavailable":
        warnings.append("R values are unavailable because realized trades or usable risk columns were not found.")
    else:
        warnings.append(f"R values use {summary.get('result_r_source')} from the imported MT5 report.")
    if python_enrichment.get("matched"):
        warnings.append(f"Matched {python_enrichment.get('matched')} imported rows to saved Python trades for missing pattern/risk/score details.")
    if summary["trade_count"] == 0:
        warnings.append("Report had rows but no realized profit rows; check whether you exported deals/history rather than summary-only data.")

    result = {
        "import_id": str(uuid.uuid4()),
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "file_name": request.get("file_name") or "pasted_mt5_report",
        "test_model": test_model,
        "symbol": symbol or request.get("symbol"),
        "timeframe": request.get("timeframe"),
        "start_date": request.get("start_date"),
        "end_date": request.get("end_date"),
        "initial_equity": initial_equity,
        "risk_percent": risk_percent,
        "raw_row_count": len(df),
        "summary": summary,
        "python_enrichment": python_enrichment,
        "model_comparison_row": comparison_row,
        "deals": deals[: int(request.get("max_deals_returned") or 500)],
        "warnings": warnings,
    }
    save_mt5_report_import(result)
    return result


def _pct_delta(current: float, baseline: float) -> float | None:
    if baseline == 0:
        return None
    return round((current - baseline) / abs(baseline), 4)


def _comparison_status(row: dict[str, Any], thresholds: dict[str, Any], final_model: bool = False) -> str:
    trades = int(row.get("trade_count") or 0)
    pf = float(row.get("profit_factor") or 0)
    exp = float(row.get("expectancy_R") or 0)
    min_trades = int(thresholds.get("min_trades", 30))
    min_pf = float(thresholds.get("min_profit_factor", 1.10 if final_model else 1.05))
    min_exp = float(thresholds.get("min_expectancy_R", 0.0))
    if trades < min_trades:
        return "INSUFFICIENT_TRADES"
    if pf < min_pf:
        return "FAIL_PF"
    if exp <= min_exp:
        return "FAIL_EXPECTANCY"
    return "PASS"


def _model_role(model: str) -> str:
    if model == "one_min_ohlc":
        return "fast_research_filter"
    if model == "every_tick":
        return "intrabar_validation"
    if model == "every_tick_real_ticks":
        return "final_execution_validation"
    return "unknown"


def _comparison_diagnostics(rows: list[dict[str, Any]], checks: list[dict[str, Any]], stability: dict[str, Any], thresholds: dict[str, Any], missing: list[str], errors: list[dict[str, str]]) -> dict[str, Any]:
    by_model = {row.get("model"): row for row in rows}
    final = by_model.get("every_tick_real_ticks", {})
    baseline = by_model.get("one_min_ohlc", {})
    imported_count = sum(1 for row in rows if row.get("status") not in {"MISSING_REPORT", "IMPORT_FAILED"})
    failed_checks = [item for item in checks if not item.get("passed")]
    real_tick_status = final.get("status", "MISSING_REPORT")
    real_tick_pf = float(final.get("profit_factor") or 0)
    real_tick_exp = float(final.get("expectancy_R") or 0)
    real_tick_trades = int(final.get("trade_count") or 0)
    min_trades = int(thresholds.get("min_trades", 30))
    min_pf = float(thresholds.get("min_profit_factor", 1.10))
    min_exp = float(thresholds.get("min_expectancy_R", 0.0))
    max_pf_drift = float(thresholds.get("max_pf_drift", 0.35))
    max_trade_drift = float(thresholds.get("max_trade_count_drift_pct", 0.35))
    max_net_drop = float(thresholds.get("max_net_profit_degradation_pct", 0.50))

    drift_checks = [
        {
            "metric": "PF drift: 1-Min OHLC to Real Ticks",
            "observed": stability.get("profit_factor_drift_1m_to_real_ticks"),
            "limit": max_pf_drift,
            "passed": stability.get("profit_factor_drift_1m_to_real_ticks") is not None and abs(float(stability.get("profit_factor_drift_1m_to_real_ticks") or 0)) <= max_pf_drift,
            "institutional_reason": "Large PF drift means candle assumptions may be too optimistic versus broker tick path.",
        },
        {
            "metric": "Trade-count drift: 1-Min OHLC to Real Ticks",
            "observed": stability.get("trade_count_drift_pct_1m_to_real_ticks"),
            "limit": max_trade_drift,
            "passed": stability.get("trade_count_drift_pct_1m_to_real_ticks") is not None and abs(float(stability.get("trade_count_drift_pct_1m_to_real_ticks") or 0)) <= max_trade_drift,
            "institutional_reason": "Large trade-count drift means signals/fills are sensitive to intrabar assumptions.",
        },
        {
            "metric": "Net-profit degradation: 1-Min OHLC to Real Ticks",
            "observed": stability.get("net_profit_drift_pct_1m_to_real_ticks"),
            "limit": -max_net_drop,
            "passed": stability.get("net_profit_drift_pct_1m_to_real_ticks") is not None and float(stability.get("net_profit_drift_pct_1m_to_real_ticks") or 0) >= -max_net_drop,
            "institutional_reason": "Real ticks should not erase too much of the 1-Min OHLC edge.",
        },
    ]

    recommendations: list[str] = []
    if missing:
        recommendations.append(f"Import missing MT5 reports before judging execution stability: {', '.join(missing)}.")
    if errors:
        recommendations.append("Fix failed report parses; export a deals/history table with time, type, profit, and preferably result_R/PYHASH.")
    if real_tick_status in {"MISSING_REPORT", "IMPORT_FAILED"}:
        verdict = "WAITING_FOR_REAL_TICK_REPORT"
        can_promote = False
        recommendations.append("Real-tick report is mandatory before final semi-manual approval.")
    elif real_tick_trades < min_trades:
        verdict = "REAL_TICK_INSUFFICIENT_TRADES"
        can_promote = False
        recommendations.append(f"Real ticks produced {real_tick_trades} trades; need at least {min_trades} for this gate.")
    elif real_tick_pf < min_pf or real_tick_exp <= min_exp:
        verdict = "REAL_TICK_EDGE_FAILED"
        can_promote = False
        recommendations.append("Real-tick PF/expectancy failed; reject or recalibrate costs, filters, and SL/TP assumptions.")
    elif failed_checks:
        verdict = "EXECUTION_DRIFT_REVIEW_REQUIRED"
        can_promote = False
        recommendations.append("Real ticks have positive evidence but drift checks failed; inspect spread/slippage and intrabar path sensitivity.")
    else:
        verdict = "EXECUTION_STABLE_REVIEW_READY"
        can_promote = True
        recommendations.append("Real-tick comparison passed. Continue only to final approval after OOS, walk-forward, Monte Carlo, and portfolio checks.")

    if baseline.get("trade_count") and final.get("trade_count"):
        recommendations.append("Use the model comparison together with Python/MT5 parity; model stability does not prove signal parity by itself.")

    return {
        "verdict": verdict,
        "can_promote_to_final_review": can_promote,
        "imported_models": imported_count,
        "required_models": len(MODEL_ORDER),
        "real_tick_status": real_tick_status,
        "real_tick_trade_count": real_tick_trades,
        "real_tick_profit_factor": real_tick_pf,
        "real_tick_expectancy_R": real_tick_exp,
        "failed_checks": failed_checks,
        "drift_checks": drift_checks,
        "recommendations": recommendations,
        "model_roles": {model: _model_role(model) for model in MODEL_ORDER},
    }


def compare_mt5_model_reports(request: dict[str, Any]) -> dict[str, Any]:
    reports = request.get("reports") if isinstance(request.get("reports"), dict) else {}
    thresholds = request.get("thresholds") if isinstance(request.get("thresholds"), dict) else {}
    base = {
        "run_id": request.get("run_id"),
        "symbol": request.get("symbol"),
        "timeframe": request.get("timeframe"),
        "start_date": request.get("start_date"),
        "end_date": request.get("end_date"),
        "initial_equity": float(request.get("initial_equity") or 100000),
        "risk_percent": float(request.get("risk_percent") or 1.0),
        "max_deals_returned": int(request.get("max_deals_returned") or 500),
    }
    imports: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for model in MODEL_ORDER:
        text = str(reports.get(model) or "").strip()
        if not text:
            rows.append(
                {
                    "model": model,
                    "model_name": MODEL_NAMES[model],
                    "trade_count": 0,
                    "win_rate": 0,
                    "profit_factor": 0,
                    "expectancy_R": 0,
                    "net_profit": 0,
                    "status": "MISSING_REPORT",
                    "source": "not imported",
                    "model_role": _model_role(model),
                    "is_final_validation_model": model == "every_tick_real_ticks",
                }
            )
            continue
        try:
            imported = import_mt5_report(
                {
                    **base,
                    "file_name": f"{base.get('symbol') or 'symbol'}_{base.get('timeframe') or 'tf'}_{model}_report",
                    "test_model": model,
                    "report_text": text,
                }
            )
            imports[model] = imported
            row = dict(imported["model_comparison_row"])
            row["status"] = _comparison_status(row, thresholds, final_model=model == "every_tick_real_ticks")
            row["import_id"] = imported["import_id"]
            row["model_role"] = _model_role(model)
            row["is_final_validation_model"] = model == "every_tick_real_ticks"
            rows.append(row)
        except Exception as exc:
            errors.append({"model": model, "error": str(exc)})
            rows.append(
                {
                    "model": model,
                    "model_name": MODEL_NAMES[model],
                    "trade_count": 0,
                    "win_rate": 0,
                    "profit_factor": 0,
                    "expectancy_R": 0,
                    "net_profit": 0,
                    "status": "IMPORT_FAILED",
                    "source": "MT5 Strategy Tester imported report",
                    "error": str(exc),
                    "model_role": _model_role(model),
                    "is_final_validation_model": model == "every_tick_real_ticks",
                }
            )

    by_model = {row["model"]: row for row in rows}
    baseline = by_model.get("one_min_ohlc", {})
    final = by_model.get("every_tick_real_ticks", {})
    tick = by_model.get("every_tick", {})
    for row in rows:
        row["trade_count_delta_vs_1m"] = int(row.get("trade_count") or 0) - int(baseline.get("trade_count") or 0)
        row["profit_factor_delta_vs_1m"] = round(float(row.get("profit_factor") or 0) - float(baseline.get("profit_factor") or 0), 4)
        row["expectancy_delta_vs_1m"] = round(float(row.get("expectancy_R") or 0) - float(baseline.get("expectancy_R") or 0), 4)
        row["net_profit_drift_vs_1m"] = _pct_delta(float(row.get("net_profit") or 0), float(baseline.get("net_profit") or 0))

    missing = [row["model"] for row in rows if row.get("status") == "MISSING_REPORT"]
    imported_count = len(imports)
    pf_drift = round(float(final.get("profit_factor") or 0) - float(baseline.get("profit_factor") or 0), 4)
    exp_drift = round(float(final.get("expectancy_R") or 0) - float(baseline.get("expectancy_R") or 0), 4)
    trade_drift_pct = _pct_delta(float(final.get("trade_count") or 0), float(baseline.get("trade_count") or 0))
    net_drift_pct = _pct_delta(float(final.get("net_profit") or 0), float(baseline.get("net_profit") or 0))
    max_pf_drift = float(thresholds.get("max_pf_drift", 0.35))
    max_trade_drift = float(thresholds.get("max_trade_count_drift_pct", 0.35))
    max_net_degradation = float(thresholds.get("max_net_profit_degradation_pct", 0.50))

    checks = [
        {"check": "all_models_imported", "passed": imported_count == 3, "detail": f"Imported {imported_count}/3 reports."},
        {"check": "real_ticks_trade_count", "passed": final.get("status") not in {"MISSING_REPORT", "IMPORT_FAILED", "INSUFFICIENT_TRADES"}, "detail": f"Real tick trades: {final.get('trade_count', 0)}."},
        {"check": "real_ticks_pf", "passed": float(final.get("profit_factor") or 0) >= float(thresholds.get("min_profit_factor", 1.10)), "detail": f"Real tick PF: {final.get('profit_factor', 0)}."},
        {"check": "real_ticks_expectancy", "passed": float(final.get("expectancy_R") or 0) > float(thresholds.get("min_expectancy_R", 0.0)), "detail": f"Real tick expectancy R: {final.get('expectancy_R', 0)}."},
        {"check": "pf_drift_vs_1m", "passed": abs(pf_drift) <= max_pf_drift, "detail": f"PF drift 1m to real ticks: {pf_drift}."},
        {"check": "trade_count_drift_vs_1m", "passed": trade_drift_pct is not None and abs(trade_drift_pct) <= max_trade_drift, "detail": f"Trade count drift: {trade_drift_pct}."},
        {"check": "net_profit_degradation_vs_1m", "passed": net_drift_pct is not None and net_drift_pct >= -max_net_degradation, "detail": f"Net profit drift: {net_drift_pct}."},
    ]
    if tick.get("status") in {"PASS", "IMPORTED"} and final.get("status") in {"PASS", "IMPORTED"}:
        tick_to_real_pf = round(float(final.get("profit_factor") or 0) - float(tick.get("profit_factor") or 0), 4)
        checks.append({"check": "every_tick_to_real_tick_pf_drift", "passed": abs(tick_to_real_pf) <= max_pf_drift, "detail": f"Every tick to real tick PF drift: {tick_to_real_pf}."})

    passed = all(item["passed"] for item in checks)
    stability = {
        "profit_factor_drift_1m_to_real_ticks": pf_drift,
        "expectancy_drift_1m_to_real_ticks": exp_drift,
        "trade_count_drift_pct_1m_to_real_ticks": trade_drift_pct,
        "net_profit_drift_pct_1m_to_real_ticks": net_drift_pct,
        "baseline_model": "one_min_ohlc",
        "final_model": "every_tick_real_ticks",
    }
    diagnostics = _comparison_diagnostics(rows, checks, stability, thresholds, missing, errors)
    if missing:
        status = "MISSING_MODELS"
    elif errors:
        status = "IMPORT_ERRORS"
    elif passed:
        status = "MODEL_STABLE_APPROVED_FOR_REVIEW"
    else:
        status = "MODEL_UNSTABLE_REVIEW_REQUIRED"

    return {
        "comparison_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "symbol": base.get("symbol"),
        "timeframe": base.get("timeframe"),
        "run_id": base.get("run_id"),
        "rows": rows,
        "checks": checks,
        "missing_models": missing,
        "errors": errors,
        "imports": {model: {"import_id": item["import_id"], "summary": item["summary"]} for model, item in imports.items()},
        "stability": stability,
        "diagnostics": diagnostics,
        "decision": {
            "status": diagnostics["verdict"],
            "can_promote_to_final_review": diagnostics["can_promote_to_final_review"],
            "message": diagnostics["recommendations"][0] if diagnostics["recommendations"] else status,
        },
        "next_actions": diagnostics["recommendations"],
        "thresholds": {
            "min_trades": int(thresholds.get("min_trades", 30)),
            "min_profit_factor": float(thresholds.get("min_profit_factor", 1.10)),
            "min_expectancy_R": float(thresholds.get("min_expectancy_R", 0.0)),
            "max_pf_drift": max_pf_drift,
            "max_trade_count_drift_pct": max_trade_drift,
            "max_net_profit_degradation_pct": max_net_degradation,
        },
        "warnings": [
            "Use the same symbol, timeframe, date range, regime, strategy, risk, and filters for all three MT5 model reports.",
            "Approve a setup only when the real-tick model remains profitable and model drift is acceptable.",
        ],
    }
