from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.database import load_backtest, load_backtest_trades


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _price(value: Any) -> str:
    try:
        return f"{float(value):.8f}"
    except (TypeError, ValueError):
        return "0.00000000"


def _mt5_time(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%Y.%m.%d %H:%M")
    except ValueError:
        return text.replace("-", ".").replace("T", " ")[:16]


def _trade_hash(row: dict[str, Any], index: int) -> str:
    text = "|".join(
        [
            str(index),
            str(row.get("entry_time") or ""),
            str(row.get("regime_id") or "").upper(),
            str(row.get("strategy_id") or "").upper(),
            str(row.get("direction") or "").lower(),
            _price(row.get("entry")),
            _price(row.get("sl")),
            _price(row.get("tp")),
        ]
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _packet_hash(run: dict[str, Any], trades: list[dict[str, Any]]) -> str:
    payload = {
        "run_id": run.get("run_id"),
        "request": run.get("request", {}),
        "summary": run.get("summary", {}),
        "trades": [
            {
                "entry_time": t.get("entry_time"),
                "regime_id": t.get("regime_id"),
                "strategy_id": t.get("strategy_id"),
                "direction": t.get("direction"),
                "entry": _price(t.get("entry")),
                "sl": _price(t.get("sl")),
                "tp": _price(t.get("tp")),
            }
            for t in trades
        ],
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _expected_signal_rows(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, trade in enumerate(trades):
        parity_hash = _trade_hash(trade, idx)
        rows.append(
            {
                "parity_index": idx,
                "parity_hash": parity_hash,
                "entry_time": _mt5_time(trade.get("entry_time")),
                "exit_time": _mt5_time(trade.get("exit_time")),
                "symbol": trade.get("symbol"),
                "timeframe": trade.get("timeframe"),
                "regime_id": trade.get("regime_id"),
                "strategy_id": trade.get("strategy_id"),
                "direction": trade.get("direction"),
                "entry": trade.get("entry"),
                "sl": trade.get("sl"),
                "tp": trade.get("tp"),
                "exit_price": trade.get("exit_price"),
                "result_R": trade.get("result_R"),
                "profit": trade.get("profit"),
                "alpha_score": trade.get("alpha_score"),
                "pattern_score": trade.get("pattern_score"),
                "final_score": trade.get("final_score"),
                "initial_risk": trade.get("initial_risk"),
                "patterns_detected": json.dumps(trade.get("patterns_detected") or [], separators=(",", ":")),
                "comment": f"{trade.get('regime_id')}|{trade.get('strategy_id')}|PYIDX:{idx}|PYHASH:{parity_hash}",
            }
        )
    return rows


def _csv_text(rows: list[dict[str, Any]]) -> str:
    fieldnames = [
        "parity_index",
        "parity_hash",
        "entry_time",
        "exit_time",
        "symbol",
        "timeframe",
        "regime_id",
        "strategy_id",
        "direction",
        "entry",
        "sl",
        "tp",
        "exit_price",
        "result_R",
        "profit",
        "alpha_score",
        "pattern_score",
        "final_score",
        "initial_risk",
        "patterns_detected",
        "comment",
    ]
    if not rows:
        output = io.StringIO()
        csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n").writeheader()
        return output.getvalue()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def build_python_parity_packet(run_id: str) -> dict[str, Any]:
    run = load_backtest(run_id)
    if run is None:
        raise ValueError(f"Backtest run not found: {run_id}")
    trades = load_backtest_trades(run_id)
    signal_rows = _expected_signal_rows(trades)
    request = run.get("request", {})
    packet_hash = _packet_hash(run, trades)
    return {
        "packet_id": packet_hash[:16],
        "packet_hash": packet_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "python_run_id": run_id,
        "candidate": {
            "symbol": request.get("symbol"),
            "timeframe": request.get("timeframe"),
            "start_date": request.get("start_date"),
            "end_date": request.get("end_date"),
            "regime_filter": request.get("regime_filter"),
            "strategy_filter": request.get("strategy_filter"),
            "risk_percent": request.get("risk_percent"),
            "rr": request.get("rr"),
            "initial_equity": request.get("initial_equity"),
        },
        "summary": run.get("summary", {}),
        "expected_trade_count": len(signal_rows),
        "expected_signals": signal_rows,
        "expected_signals_csv": _csv_text(signal_rows),
        "mt5_ea_requirements": {
            "tester_only": True,
            "required_comment_format": "Rxx|StrategyId|PYIDX:<index>|PYHASH:<16-char-hash>",
            "required_export_columns": [
                "parity_index",
                "parity_hash",
                "entry_time",
                "exit_time",
                "symbol",
                "timeframe",
                "regime_id",
                "strategy_id",
                "direction",
                "entry",
                "sl",
                "tp",
                "exit_price",
                "result_R",
                "profit",
                "comment",
            ],
        },
        "warnings": [
            "Use this packet to make the MQL5 tester export deterministic signal rows. Generic MT5 deal reports can still be compared, but exact SL/TP/result_R parity requires these columns.",
            "No order execution is enabled by this packet; it is for Strategy Tester/report parity only.",
        ],
    }


def write_python_signal_csv(run_id: str, output_dir: str | Path, file_name: str | None = None) -> dict[str, Any]:
    packet = build_python_parity_packet(run_id)
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    name = file_name or f"QuantForexV10_python_signals_{packet['packet_id']}.csv"
    path = folder / name
    path.write_text(packet.get("expected_signals_csv", ""), encoding="utf-8")
    return {
        "packet": packet,
        "file_name": name,
        "file_path": str(path),
        "expected_trade_count": packet.get("expected_trade_count", 0),
        "packet_id": packet.get("packet_id"),
        "packet_hash": packet.get("packet_hash"),
    }
