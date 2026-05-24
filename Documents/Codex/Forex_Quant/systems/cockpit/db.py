from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "cockpit.db"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id                      TEXT PRIMARY KEY,
    regime_id                   TEXT NOT NULL,
    base_regime                 TEXT NOT NULL,
    modifier                    TEXT NOT NULL,
    strategy_id                 TEXT NOT NULL,
    slot                        TEXT NOT NULL,
    signal_fn                   TEXT NOT NULL,
    symbol                      TEXT NOT NULL,
    timeframe                   TEXT NOT NULL,
    data_start                  TEXT NOT NULL,
    data_end                    TEXT NOT NULL,
    bars_used                   INTEGER NOT NULL,
    initial_capital             REAL NOT NULL DEFAULT 10000.0,
    risk_per_trade_pct          REAL NOT NULL DEFAULT 1.0,
    total_trades                INTEGER NOT NULL DEFAULT 0,
    wins                        INTEGER NOT NULL DEFAULT 0,
    losses                      INTEGER NOT NULL DEFAULT 0,
    open_trades                 INTEGER NOT NULL DEFAULT 0,
    win_rate                    REAL,
    profit_factor               REAL,
    sharpe_ratio                REAL,
    sortino_ratio               REAL,
    max_drawdown_pct            REAL,
    max_drawdown_r              REAL,
    total_return_pct            REAL,
    net_profit_usd              REAL,
    final_equity_usd            REAL,
    expectancy_r                REAL,
    avg_rr_target               REAL,
    avg_rr_achieved             REAL,
    avg_bars_held               REAL,
    kill_zone_trades            INTEGER DEFAULT 0,
    kill_zone_wins              INTEGER DEFAULT 0,
    kill_zone_win_rate          REAL,
    no_kill_zone_win_rate       REAL,
    sweep_trades                INTEGER DEFAULT 0,
    sweep_wins                  INTEGER DEFAULT 0,
    sweep_win_rate              REAL,
    institutional_trap_failures INTEGER DEFAULT 0,
    sweep_no_reclaim_failures   INTEGER DEFAULT 0,
    spread_rejection_count      INTEGER DEFAULT 0,
    news_lock_skips             INTEGER DEFAULT 0,
    no_signal_bars              INTEGER DEFAULT 0,
    low_vol_win_rate            REAL,
    high_vol_win_rate           REAL,
    high_conf_win_rate          REAL,
    low_conf_win_rate           REAL,
    prior_win_rate_low          REAL,
    prior_win_rate_high         REAL,
    prior_ev_r                  REAL,
    validated                   INTEGER DEFAULT 0,
    validation_note             TEXT,
    run_duration_seconds        REAL,
    created_at                  TEXT DEFAULT (datetime('now')),
    notes                       TEXT,
    request_json                TEXT,
    response_json               TEXT
);

CREATE INDEX IF NOT EXISTS idx_bt_regime ON backtest_runs(regime_id);
CREATE INDEX IF NOT EXISTS idx_bt_strategy ON backtest_runs(strategy_id);
CREATE INDEX IF NOT EXISTS idx_bt_symbol ON backtest_runs(symbol, timeframe);

CREATE TABLE IF NOT EXISTS trade_log (
    trade_id                TEXT PRIMARY KEY,
    run_id                  TEXT NOT NULL REFERENCES backtest_runs(run_id),
    bar_index               INTEGER NOT NULL,
    trade_number            INTEGER NOT NULL,
    regime_id               TEXT NOT NULL,
    strategy_id             TEXT NOT NULL,
    direction               TEXT NOT NULL,
    entry_price             REAL NOT NULL,
    entry_time              TEXT NOT NULL,
    stop_price              REAL NOT NULL,
    tp_price                REAL NOT NULL,
    rr_target               REAL NOT NULL,
    lot_size                REAL NOT NULL DEFAULT 0.01,
    risk_usd                REAL NOT NULL,
    exit_price              REAL,
    exit_time               TEXT,
    exit_reason             TEXT,
    bars_held               INTEGER,
    pips_gained             REAL,
    pnl_usd                 REAL,
    pnl_r                   REAL,
    rr_achieved             REAL,
    result                  TEXT,
    session_label           TEXT,
    kill_zone_active        INTEGER DEFAULT 0,
    sweep_flag              INTEGER DEFAULT 0,
    kill_zone_at_entry      INTEGER DEFAULT 0,
    adx_at_entry            REAL,
    er_at_entry             REAL,
    vol_pctile_at_entry     REAL,
    spread_pctile_at_entry  REAL,
    atr_at_entry            REAL,
    confidence_at_entry     REAL,
    regime_changed_during   INTEGER DEFAULT 0,
    failed_institutional    INTEGER DEFAULT 0,
    failed_sweep_no_reclaim INTEGER DEFAULT 0,
    failed_high_spread      INTEGER DEFAULT 0,
    failed_news_event       INTEGER DEFAULT 0,
    failed_regime_change    INTEGER DEFAULT 0,
    equity_before           REAL,
    equity_after            REAL,
    drawdown_pct_at_entry   REAL,
    created_at              TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tl_run ON trade_log(run_id);
CREATE INDEX IF NOT EXISTS idx_tl_regime ON trade_log(regime_id);
CREATE INDEX IF NOT EXISTS idx_tl_strategy ON trade_log(strategy_id);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    snap_id             TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES backtest_runs(run_id),
    trade_number        INTEGER NOT NULL,
    trade_time          TEXT,
    equity_usd          REAL NOT NULL,
    drawdown_pct        REAL NOT NULL DEFAULT 0.0,
    pnl_r_cumulative    REAL NOT NULL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_eq_run ON equity_snapshots(run_id);

CREATE TABLE IF NOT EXISTS regime_bar_log (
    log_id          TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES backtest_runs(run_id),
    bar_index       INTEGER NOT NULL,
    bar_time        TEXT NOT NULL,
    regime_id       TEXT NOT NULL,
    base_regime     TEXT NOT NULL,
    modifier        TEXT NOT NULL,
    confidence      REAL NOT NULL,
    tradable        INTEGER NOT NULL,
    adx             REAL,
    er              REAL,
    atr_pct         REAL,
    vol_pctile      REAL,
    spread_pctile   REAL,
    session_label   TEXT,
    kill_zone       INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_rbl_run ON regime_bar_log(run_id);
CREATE INDEX IF NOT EXISTS idx_rbl_regime ON regime_bar_log(regime_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _ratio_percent_to_fraction(value: Any) -> float | None:
    if value is None:
        return None
    val = float(value)
    return val / 100.0 if val > 1.0 else val


def _strategy_meta(result: dict[str, Any]) -> dict[str, Any]:
    strategy = result.get("strategy") or {}
    regime_id = str(result.get("selected_regime") or strategy.get("regime_id") or "Q4_M01").upper()
    base, _, modifier = regime_id.partition("_")
    return {
        "regime_id": regime_id,
        "base_regime": base or regime_id[:2],
        "modifier": modifier or "",
        "strategy_id": str(strategy.get("id") or result.get("selected_strategy") or ""),
        "slot": str(strategy.get("slot") or ""),
        "signal_fn": str(strategy.get("signal_fn") or ""),
        "prior_win_rate_low": float(strategy.get("win_rate_low") or 0.0),
        "prior_win_rate_high": float(strategy.get("win_rate_high") or 0.0),
        "prior_ev_r": float(strategy.get("ev") or 0.0),
    }


def save_backtest_result(result: dict[str, Any], request: dict[str, Any] | None = None) -> str:
    init_db()
    meta = _strategy_meta(result)
    save_status = result.get("save_status") or {}
    run_id = str(save_status.get("run_id") or result.get("run_id") or uuid4())
    period = result.get("period") or {}
    request = request or {}
    api_body = result.get("api_request", {}).get("body", {}) if isinstance(result.get("api_request"), dict) else {}
    initial_capital = float(api_body.get("investment_amount") or request.get("investment_amount") or 10000.0)
    trades = result.get("trades_all") or result.get("trades") or []
    closed_trades = [trade for trade in trades if str(trade.get("result", "")).lower() != "open"]
    kill_zone_trades = [trade for trade in trades if trade.get("kill_zone_active")]
    kill_zone_wins = [trade for trade in kill_zone_trades if float(trade.get("pnl") or 0.0) > 0.0]
    sweep_trades = [trade for trade in trades if trade.get("liquidity_sweep_direction")]
    sweep_wins = [trade for trade in sweep_trades if float(trade.get("pnl") or 0.0) > 0.0]
    failures = result.get("fail_reason_counts") or {}
    notes = result.get("reason") if result.get("blocked") else "; ".join(str(x) for x in result.get("alpha_notes", [])[:3])
    row = {
        **meta,
        "run_id": run_id,
        "symbol": str(result.get("symbol") or request.get("symbol") or "").upper(),
        "timeframe": str(result.get("timeframe") or request.get("timeframe") or "").upper(),
        "data_start": str(period.get("start") or ""),
        "data_end": str(period.get("end") or ""),
        "bars_used": int(period.get("bars") or request.get("bars") or 0),
        "initial_capital": initial_capital,
        "risk_per_trade_pct": 1.0,
        "total_trades": int(result.get("executed_simulated_trades") or result.get("total_trades") or 0),
        "wins": int(result.get("wins") or 0),
        "losses": int(result.get("losses") or 0),
        "open_trades": len(trades) - len(closed_trades),
        "win_rate": _ratio_percent_to_fraction(result.get("win_rate")),
        "profit_factor": float(result.get("profit_factor") or 0.0),
        "sharpe_ratio": None,
        "sortino_ratio": None,
        "max_drawdown_pct": (100.0 * float(result.get("max_drawdown") or 0.0) / initial_capital) if initial_capital else None,
        "max_drawdown_r": None,
        "total_return_pct": float(result.get("return_percent") or 0.0),
        "net_profit_usd": float(result.get("net_pl") or 0.0),
        "final_equity_usd": initial_capital + float(result.get("net_pl") or 0.0),
        "expectancy_r": float(result.get("average_r") or 0.0),
        "avg_rr_target": float(result.get("target_r_multiple") or 0.0),
        "avg_rr_achieved": float(result.get("average_r") or 0.0),
        "avg_bars_held": float(result.get("average_bars_in_trade") or 0.0),
        "kill_zone_trades": len(kill_zone_trades),
        "kill_zone_wins": len(kill_zone_wins),
        "kill_zone_win_rate": (len(kill_zone_wins) / len(kill_zone_trades)) if kill_zone_trades else None,
        "no_kill_zone_win_rate": None,
        "sweep_trades": len(sweep_trades),
        "sweep_wins": len(sweep_wins),
        "sweep_win_rate": (len(sweep_wins) / len(sweep_trades)) if sweep_trades else None,
        "institutional_trap_failures": int(failures.get("institutional trap", 0) or failures.get("trap score", 0) or 0),
        "sweep_no_reclaim_failures": int(failures.get("liquidity sweep", 0) or failures.get("sweep failed", 0) or 0),
        "spread_rejection_count": int(failures.get("spread too high", 0) or 0),
        "news_lock_skips": int(failures.get("news lock", 0) or 0),
        "no_signal_bars": int(failures.get("no setup", 0) or 0),
        "validated": 0,
        "validation_note": "blocked/no trades" if result.get("blocked") else "",
        "run_duration_seconds": None,
        "created_at": _now(),
        "notes": notes,
        "request_json": _json(request or result.get("api_request") or {}),
        "response_json": _json(result),
    }
    columns = list(row.keys())
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(f"{col}=excluded.{col}" for col in columns if col != "run_id")
    with get_conn() as conn:
        conn.execute(
            f"INSERT INTO backtest_runs ({', '.join(columns)}) VALUES ({placeholders}) ON CONFLICT(run_id) DO UPDATE SET {updates}",
            [row[col] for col in columns],
        )
        conn.execute("DELETE FROM trade_log WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM equity_snapshots WHERE run_id = ?", (run_id,))
        risk_usd = float(result.get("risk_amount_per_trade") or 0.0)
        equity_before = initial_capital
        for index, trade in enumerate(trades, start=1):
            pnl_usd = float(trade.get("pnl") or 0.0)
            equity_after = equity_before + pnl_usd
            conn.execute(
                """
                INSERT INTO trade_log (
                    trade_id, run_id, bar_index, trade_number, regime_id, strategy_id, direction,
                    entry_price, entry_time, stop_price, tp_price, rr_target, lot_size, risk_usd,
                    exit_price, exit_time, exit_reason, bars_held, pips_gained, pnl_usd, pnl_r,
                    rr_achieved, result, session_label, kill_zone_active, sweep_flag,
                    kill_zone_at_entry, failed_institutional, failed_sweep_no_reclaim,
                    failed_high_spread, failed_news_event, failed_regime_change,
                    equity_before, equity_after
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    run_id,
                    int(trade.get("bar_index") or index),
                    int(trade.get("trade_number") or index),
                    str(trade.get("regime_id") or meta["regime_id"]),
                    meta["strategy_id"],
                    str(trade.get("side") or trade.get("direction") or ""),
                    float(trade.get("entry") or 0.0),
                    str(trade.get("time") or trade.get("entry_time") or ""),
                    float(trade.get("stop") or 0.0),
                    float(trade.get("target") or 0.0),
                    float(result.get("target_r_multiple") or abs(float(trade.get("r") or 0.0)) or 0.0),
                    0.01,
                    risk_usd,
                    None,
                    None,
                    "SCENARIO_MAX_HOLD",
                    int(trade.get("bars_held") or trade.get("bars_held_max") or 0),
                    None,
                    pnl_usd,
                    float(trade.get("r") or 0.0),
                    float(trade.get("r") or 0.0),
                    "win" if pnl_usd > 0 else "loss",
                    str(trade.get("session_label") or ""),
                    1 if trade.get("kill_zone_active") else 0,
                    1 if trade.get("liquidity_sweep_direction") else 0,
                    1 if trade.get("kill_zone_active") else 0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    equity_before,
                    equity_after,
                ),
            )
            equity_before = equity_after
        for index, snap in enumerate(result.get("equity_curve_all") or result.get("equity_curve") or [], start=1):
            conn.execute(
                "INSERT INTO equity_snapshots (snap_id, run_id, trade_number, trade_time, equity_usd, drawdown_pct, pnl_r_cumulative) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid4()),
                    run_id,
                    index,
                    str(snap.get("time") or ""),
                    float(snap.get("equity") or initial_capital),
                    float(snap.get("drawdown") or 0.0),
                    0.0,
                ),
            )
        conn.commit()
    return run_id


def list_runs(limit: int = 100, regime_id: str | None = None, strategy_id: str | None = None) -> list[dict[str, Any]]:
    init_db()
    clauses: list[str] = []
    args: list[Any] = []
    if regime_id:
        clauses.append("regime_id = ?")
        args.append(regime_id.upper())
    if strategy_id:
        clauses.append("strategy_id = ?")
        args.append(strategy_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(f"SELECT * FROM backtest_runs {where} ORDER BY created_at DESC LIMIT ?", [*args, int(limit)]).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_run(run_id: str) -> dict[str, Any] | None:
    init_db()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM backtest_runs WHERE run_id = ?", (run_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_run_detail(run_id: str) -> dict[str, Any] | None:
    run = get_run(run_id)
    if not run:
        return None
    with get_conn() as conn:
        trades = [_row_to_dict(row) for row in conn.execute("SELECT * FROM trade_log WHERE run_id = ? ORDER BY trade_number", (run_id,)).fetchall()]
        equity = [_row_to_dict(row) for row in conn.execute("SELECT * FROM equity_snapshots WHERE run_id = ? ORDER BY trade_number", (run_id,)).fetchall()]
    run["request"] = json.loads(run.get("request_json") or "{}")
    run["response"] = json.loads(run.get("response_json") or "{}")
    run["trades"] = trades
    run["equity"] = equity
    return run


def rankings(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT regime_id, strategy_id, slot, signal_fn, symbol, timeframe,
                   COUNT(*) AS runs,
                   SUM(total_trades) AS total_trades,
                   SUM(wins) AS wins,
                   SUM(losses) AS losses,
                   AVG(win_rate) AS avg_win_rate,
                   AVG(profit_factor) AS avg_profit_factor,
                   AVG(expectancy_r) AS avg_expectancy_r,
                   SUM(net_profit_usd) AS total_net_profit_usd,
                   AVG(total_return_pct) AS avg_return_pct,
                   MAX(created_at) AS latest_run_at
            FROM backtest_runs
            WHERE total_trades > 0
            GROUP BY regime_id, strategy_id, symbol, timeframe
            ORDER BY avg_expectancy_r DESC, avg_profit_factor DESC, total_trades DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]
