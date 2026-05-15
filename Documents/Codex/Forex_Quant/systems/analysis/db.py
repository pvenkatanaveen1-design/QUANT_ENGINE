from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_DIR = PROJECT_ROOT / "data" / "analysis"
DUCKDB_PATH = ANALYSIS_DIR / "quanta_analysis.duckdb"
SQLITE_PATH = ANALYSIS_DIR / "quanta_journal.sqlite"

CACHE_TYPES = [
    "WF_RUN_SUMMARY",
    "STRATEGY_STATS",
    "REGIME_STATS",
    "BASE_REGIME_STATS",
    "SESSION_STATS",
    "CONDITION_STATS",
    "STRATEGY_REGIME_MATRIX",
    "SESSION_REGIME_STATS",
    "DAY_OF_WEEK_STATS",
    "REGIME_FREQUENCY",
    "CONFIDENCE_BUCKETS",
    "ROLLING_EDGE",
    "RR_DISTRIBUTION",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def get_duckdb():
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DUCKDB_PATH))


def get_sqlite() -> sqlite3.Connection:
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> dict[str, str]:
    with get_duckdb() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT,
                symbol TEXT,
                timeframe TEXT,
                selected_regime TEXT,
                selected_strategy TEXT,
                strategy_family TEXT,
                source TEXT,
                period_start TEXT,
                period_end TEXT,
                bars INTEGER,
                conditions_json TEXT,
                metrics_json TEXT,
                request_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                run_id TEXT,
                trade_number INTEGER,
                strategy_id TEXT,
                regime_at_entry TEXT,
                symbol TEXT,
                timeframe TEXT,
                bar_time TEXT,
                side TEXT,
                entry DOUBLE,
                stop DOUBLE,
                target DOUBLE,
                pnl DOUBLE,
                pnl_r DOUBLE,
                cumulative_pnl DOUBLE,
                trap_score DOUBLE,
                kill_zone_active INTEGER,
                reason TEXT,
                metadata_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS equity_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                run_id TEXT,
                trade_number INTEGER,
                bar_time TEXT,
                equity DOUBLE,
                drawdown DOUBLE,
                pnl_r_cumulative DOUBLE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS regime_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                run_id TEXT,
                bar_time TEXT,
                symbol TEXT,
                timeframe TEXT,
                regime_id TEXT,
                confidence DOUBLE,
                tradable INTEGER,
                features_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_engine_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT,
                symbol TEXT,
                timeframe TEXT,
                regime_id_filter TEXT,
                metrics_json TEXT,
                trades_json TEXT,
                equity_json TEXT,
                validation_note TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_cache (
                cache_id TEXT PRIMARY KEY,
                run_id TEXT,
                cache_type TEXT,
                group_key TEXT,
                strategy_id TEXT,
                regime_id TEXT,
                timeframe TEXT,
                condition TEXT,
                trades_count INTEGER,
                wins INTEGER,
                losses INTEGER,
                win_rate DOUBLE,
                profit_factor DOUBLE,
                expectancy_r DOUBLE,
                total_pnl_usd DOUBLE,
                max_drawdown DOUBLE,
                payload_json TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_run ON trades(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_regime ON trades(regime_at_entry)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_run_type ON analysis_cache(run_id, cache_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signal_engine_runs_created ON signal_engine_runs(created_at)")

    with get_sqlite() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_journal (
                decision_id TEXT PRIMARY KEY,
                created_at TEXT,
                symbol TEXT,
                timeframe TEXT,
                regime_id TEXT,
                strategy_id TEXT,
                action TEXT,
                reason TEXT,
                payload_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_approvals (
                approval_id TEXT PRIMARY KEY,
                created_at TEXT,
                strategy_id TEXT,
                regime_id TEXT,
                from_status TEXT,
                to_status TEXT,
                approved INTEGER,
                reason TEXT,
                evidence_json TEXT
            )
            """
        )
        conn.commit()
    return {"duckdb": str(DUCKDB_PATH), "sqlite": str(SQLITE_PATH)}


def _cache_row(
    *,
    run_id: str,
    cache_type: str,
    group_key: str,
    strategy_id: str | None = None,
    regime_id: str | None = None,
    timeframe: str | None = None,
    condition: str | None = None,
    trades_count: int = 0,
    wins: int = 0,
    losses: int = 0,
    win_rate: float = 0.0,
    profit_factor: float = 0.0,
    expectancy_r: float = 0.0,
    total_pnl_usd: float = 0.0,
    max_drawdown: float = 0.0,
    payload: Any | None = None,
) -> tuple[Any, ...]:
    return (
        f"{run_id}_{cache_type}_{group_key}",
        run_id,
        cache_type,
        group_key,
        strategy_id,
        regime_id,
        timeframe,
        condition,
        trades_count,
        wins,
        losses,
        win_rate,
        profit_factor,
        expectancy_r,
        total_pnl_usd,
        max_drawdown,
        _json(payload or {}),
        _now(),
    )


def save_backtest_result(result: dict[str, Any]) -> dict[str, Any]:
    init_db()
    run_id = result.get("run_id") or str(uuid4())
    result["run_id"] = run_id
    period = result.get("period") or {}
    request = result.get("api_request") or {}
    body = request.get("body") or {}
    metrics = {
        key: result.get(key)
        for key in (
            "executed_simulated_trades",
            "wins",
            "losses",
            "win_rate",
            "gross_profit",
            "gross_loss",
            "net_pl",
            "return_percent",
            "profit_factor",
            "expectancy",
            "average_r",
            "max_drawdown",
            "max_consecutive_losses",
            "trade_frequency_per_100_bars",
        )
    }
    with get_duckdb() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO backtest_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run_id,
                _now(),
                result.get("symbol"),
                result.get("timeframe"),
                result.get("selected_regime"),
                (result.get("strategy") or {}).get("id"),
                result.get("strategy_family"),
                body.get("source"),
                period.get("start"),
                period.get("end"),
                int(period.get("bars") or 0),
                _json(
                    {
                        "killzone_enabled": body.get("killzone_enabled"),
                        "breakout_enabled": body.get("breakout_enabled"),
                        "sweep_enabled": body.get("sweep_enabled"),
                        "alpha_enabled": body.get("alpha_enabled"),
                        "spread_filter_enabled": body.get("spread_filter_enabled"),
                        "regime_scope": body.get("regime_scope"),
                    }
                ),
                _json(metrics),
                _json(request),
            ],
        )
        for trade in result.get("trades_all") or result.get("trades") or []:
            conn.execute(
                """
                INSERT OR REPLACE INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    f"{run_id}_T{int(trade.get('trade_number') or 0):06d}",
                    run_id,
                    int(trade.get("trade_number") or 0),
                    (result.get("strategy") or {}).get("id"),
                    trade.get("regime_id"),
                    result.get("symbol"),
                    result.get("timeframe"),
                    trade.get("time"),
                    trade.get("side"),
                    float(trade.get("entry") or 0.0),
                    float(trade.get("stop") or 0.0),
                    float(trade.get("target") or 0.0),
                    float(trade.get("pnl") or 0.0),
                    float(trade.get("r") or 0.0),
                    float(trade.get("cumulative_pnl") or 0.0),
                    float(trade.get("trap_score") or 0.0),
                    1 if trade.get("kill_zone_active") else 0,
                    trade.get("reason"),
                    _json(trade),
                ],
            )
        for index, point in enumerate(result.get("equity_curve_all") or result.get("equity_curve") or [], start=1):
            conn.execute(
                """
                INSERT OR REPLACE INTO equity_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    f"{run_id}_E{index:06d}",
                    run_id,
                    index,
                    point.get("time"),
                    float(point.get("equity") or 0.0),
                    float(point.get("drawdown") or 0.0),
                    float(point.get("net_pl") or 0.0),
                ],
            )

        cache_rows = [
            _cache_row(
                run_id=run_id,
                cache_type="RUN_SUMMARY",
                group_key="run",
                strategy_id=(result.get("strategy") or {}).get("id"),
                regime_id=result.get("selected_regime"),
                timeframe=result.get("timeframe"),
                trades_count=int(result.get("executed_simulated_trades") or 0),
                wins=int(result.get("wins") or 0),
                losses=int(result.get("losses") or 0),
                win_rate=float(result.get("win_rate") or 0.0),
                profit_factor=float(result.get("profit_factor") or 0.0),
                expectancy_r=float(result.get("average_r") or 0.0),
                total_pnl_usd=float(result.get("net_pl") or 0.0),
                max_drawdown=float(result.get("max_drawdown") or 0.0),
                payload=metrics,
            ),
            _cache_row(
                run_id=run_id,
                cache_type="FAIL_REASON_COUNTS",
                group_key="failures",
                payload=result.get("fail_reason_counts") or {},
            ),
            _cache_row(
                run_id=run_id,
                cache_type="INSTITUTIONAL_FLAGS",
                group_key="institutional",
                payload=result.get("institutional_impact_flags") or {},
            ),
        ]
        conn.executemany(
            """
            INSERT OR REPLACE INTO analysis_cache VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            cache_rows,
        )
    return {"run_id": run_id, "duckdb": str(DUCKDB_PATH), "sqlite": str(SQLITE_PATH), "saved": True}


def list_backtest_runs(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with get_duckdb() as conn:
        rows = conn.execute(
            """
            SELECT run_id, created_at, symbol, timeframe, selected_regime, selected_strategy,
                   strategy_family, period_start, period_end, metrics_json
            FROM backtest_runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [int(limit)],
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "run_id": row[0],
                "created_at": row[1],
                "symbol": row[2],
                "timeframe": row[3],
                "selected_regime": row[4],
                "selected_strategy": row[5],
                "strategy_family": row[6],
                "period_start": row[7],
                "period_end": row[8],
                "metrics": json.loads(row[9] or "{}"),
            }
        )
    return out


def find_backtest_run(
    *,
    symbol: str,
    timeframe: str,
    selected_regime: str,
    selected_strategy: str,
    conditions: dict[str, Any],
) -> dict[str, Any] | None:
    """Return the latest saved scenario run matching the exact UI backtest conditions."""
    init_db()
    with get_duckdb() as conn:
        rows = conn.execute(
            """
            SELECT run_id, created_at, symbol, timeframe, selected_regime, selected_strategy,
                   strategy_family, period_start, period_end, bars, conditions_json, metrics_json, request_json
            FROM backtest_runs
            WHERE upper(symbol) = upper(?)
              AND upper(timeframe) = upper(?)
              AND upper(selected_regime) = upper(?)
              AND selected_strategy = ?
            ORDER BY created_at DESC
            LIMIT 50
            """,
            [symbol, timeframe, selected_regime, selected_strategy],
        ).fetchall()
    normalized_conditions = {key: conditions.get(key) for key in sorted(conditions)}
    for row in rows:
        stored_conditions = json.loads(row[10] or "{}")
        request = json.loads(row[12] or "{}")
        body = request.get("body") or {}
        comparable = {
            "bars": body.get("bars"),
            "investment_amount": body.get("investment_amount"),
            "killzone_enabled": stored_conditions.get("killzone_enabled"),
            "breakout_enabled": stored_conditions.get("breakout_enabled"),
            "sweep_enabled": stored_conditions.get("sweep_enabled"),
            "alpha_enabled": stored_conditions.get("alpha_enabled"),
            "spread_filter_enabled": stored_conditions.get("spread_filter_enabled"),
            "regime_scope": stored_conditions.get("regime_scope"),
        }
        comparable = {key: comparable.get(key) for key in sorted(normalized_conditions)}
        if comparable == normalized_conditions:
            return {
                "run_id": row[0],
                "created_at": row[1],
                "symbol": row[2],
                "timeframe": row[3],
                "selected_regime": row[4],
                "selected_strategy": row[5],
                "strategy_family": row[6],
                "period_start": row[7],
                "period_end": row[8],
                "bars": row[9],
                "conditions": stored_conditions,
                "metrics": json.loads(row[11] or "{}"),
                "request": request,
            }
    return None


def get_backtest_run_detail(run_id: str) -> dict[str, Any] | None:
    init_db()
    with get_duckdb() as conn:
        run = conn.execute(
            """
            SELECT run_id, created_at, symbol, timeframe, selected_regime, selected_strategy,
                   strategy_family, period_start, period_end, bars, conditions_json, metrics_json, request_json
            FROM backtest_runs
            WHERE run_id = ?
            """,
            [run_id],
        ).fetchone()
        if not run:
            return None
        trades = conn.execute(
            """
            SELECT trade_number, bar_time, side, entry, stop, target, pnl, pnl_r,
                   cumulative_pnl, trap_score, kill_zone_active, reason, metadata_json
            FROM trades
            WHERE run_id = ?
            ORDER BY trade_number
            """,
            [run_id],
        ).fetchall()
        equity = conn.execute(
            """
            SELECT trade_number, bar_time, equity, drawdown, pnl_r_cumulative
            FROM equity_snapshots
            WHERE run_id = ?
            ORDER BY trade_number
            """,
            [run_id],
        ).fetchall()
    return {
        "run_id": run[0],
        "created_at": run[1],
        "symbol": run[2],
        "timeframe": run[3],
        "selected_regime": run[4],
        "selected_strategy": run[5],
        "strategy_family": run[6],
        "period": {"start": run[7], "end": run[8], "bars": run[9]},
        "conditions": json.loads(run[10] or "{}"),
        "metrics": json.loads(run[11] or "{}"),
        "request": json.loads(run[12] or "{}"),
        "trades": [
            {
                "trade_number": row[0],
                "time": row[1],
                "side": row[2],
                "entry": row[3],
                "stop": row[4],
                "target": row[5],
                "pnl": row[6],
                "r": row[7],
                "cumulative_pnl": row[8],
                "trap_score": row[9],
                "kill_zone_active": bool(row[10]),
                "reason": row[11],
                "metadata": json.loads(row[12] or "{}"),
            }
            for row in trades
        ],
        "equity": [
            {"trade_number": row[0], "time": row[1], "equity": row[2], "drawdown": row[3], "net_pl": row[4]}
            for row in equity
        ],
    }


def get_analysis_cache(run_id: str | None = None, cache_type: str | None = None) -> list[dict[str, Any]]:
    init_db()
    query = "SELECT * FROM analysis_cache"
    params: list[Any] = []
    clauses: list[str] = []
    if run_id:
        clauses.append("run_id = ?")
        params.append(run_id)
    if cache_type:
        clauses.append("cache_type = ?")
        params.append(cache_type)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC LIMIT 500"
    with get_duckdb() as conn:
        rows = conn.execute(query, params).fetchall()
        cols = [item[0] for item in conn.description]
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(zip(cols, row))
        if item.get("payload_json"):
            item["payload"] = json.loads(item["payload_json"])
        result.append(item)
    return result


def append_decision(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    decision_id = payload.get("decision_id") or str(uuid4())
    with get_sqlite() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO decision_journal VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                decision_id,
                payload.get("created_at") or _now(),
                payload.get("symbol"),
                payload.get("timeframe"),
                payload.get("regime_id"),
                payload.get("strategy_id"),
                payload.get("action"),
                payload.get("reason"),
                _json(payload),
            ],
        )
        conn.commit()
    journal_jsonl = ANALYSIS_DIR / "decisions.jsonl"
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    line = {
        "decision_id": decision_id,
        "created_at": payload.get("created_at") or _now(),
        "symbol": payload.get("symbol"),
        "timeframe": payload.get("timeframe"),
        "regime_id": payload.get("regime_id"),
        "strategy_id": payload.get("strategy_id"),
        "action": payload.get("action"),
        "reason": payload.get("reason"),
        "payload": payload,
    }
    with journal_jsonl.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, default=str, sort_keys=True) + "\n")
    return {"decision_id": decision_id, "saved": True}


def list_decisions(limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    with get_sqlite() as conn:
        rows = conn.execute(
            """
            SELECT decision_id, created_at, symbol, timeframe, regime_id, strategy_id, action, reason, payload_json
            FROM decision_journal
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [int(limit)],
        ).fetchall()
    return [
        {
            "decision_id": row["decision_id"],
            "created_at": row["created_at"],
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "regime_id": row["regime_id"],
            "strategy_id": row["strategy_id"],
            "action": row["action"],
            "reason": row["reason"],
            "payload": json.loads(row["payload_json"] or "{}"),
        }
        for row in rows
    ]


def record_strategy_approval(strategy_id: str, regime_id: str, from_status: str, to_status: str, approved: bool, reason: str, evidence: dict[str, Any]) -> dict[str, Any]:
    init_db()
    approval_id = str(uuid4())
    with get_sqlite() as conn:
        conn.execute(
            """
            INSERT INTO strategy_approvals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [approval_id, _now(), strategy_id, regime_id, from_status, to_status, 1 if approved else 0, reason, _json(evidence)],
        )
        conn.commit()
    return {"approval_id": approval_id, "approved": approved, "reason": reason}


def _serialize_wf_trade(t: Any) -> dict[str, Any]:
    return {
        "trade_id": t.trade_id,
        "bar_index": t.bar_index,
        "regime_id": t.regime_id,
        "session_label": t.session_label,
        "kill_zone_active": t.kill_zone_active,
        "direction": t.direction,
        "entry": t.entry,
        "stop": t.stop,
        "tp": t.tp,
        "rr_target": t.rr_target,
        "strategy_id": t.strategy_id,
        "signal_confidence": t.signal_confidence,
        "signal_bar_time": getattr(t, "signal_bar_time", ""),
        "result": t.result,
        "pnl_r": t.pnl_r,
        "bars_held": t.bars_held,
        "exit_reason": t.exit_reason,
    }


def _agg_closed(sub: list[Any]) -> tuple[int, int, int, float, float, float]:
    n = len(sub)
    if n == 0:
        return 0, 0, 0, 0.0, 0.0, 0.0
    wins = sum(1 for t in sub if t.result == "win")
    losses = sum(1 for t in sub if t.result == "loss")
    wr_frac = wins / n
    gw = sum(t.pnl_r for t in sub if t.result == "win")
    gl = abs(sum(t.pnl_r for t in sub if t.result == "loss"))
    pf = gw / max(gl, 1e-10)
    ex = sum(t.pnl_r for t in sub) / n
    return n, wins, losses, wr_frac, pf, ex


def _strategy_slot(sid: str) -> str | None:
    for p in ("S01", "S02", "S03", "S04"):
        if sid.startswith(p):
            return p
    return None


def _parse_dow(ts: str) -> int | None:
    if not ts:
        return None
    try:
        t = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
        return datetime.fromisoformat(t).weekday()
    except ValueError:
        return None


def populate_all(conn: Any, run_id: str, result: Any, initial_balance: float = 10_000.0) -> None:
    """Populate analysis_cache with Phase F cache types from a signal-engine BacktestResult."""
    from systems.strategy_router import backend as strategy_backend

    closed: list[Any] = [t for t in result.trades if t.result in ("win", "loss")]
    r_dollar = float(initial_balance) * 0.01
    net_r = sum(t.pnl_r for t in closed)
    net_usd = net_r * r_dollar
    cache_batch: list[tuple[Any, ...]] = []

    def push(**kwargs: Any) -> None:
        cache_batch.append(_cache_row(run_id=run_id, **kwargs))

    win_rate_pct = float(result.win_rate) * 100.0
    push(
        cache_type="WF_RUN_SUMMARY",
        group_key="summary",
        trades_count=int(result.total_trades),
        wins=int(result.wins),
        losses=int(result.losses),
        win_rate=win_rate_pct,
        profit_factor=float(result.profit_factor),
        expectancy_r=float(result.expectancy_r),
        total_pnl_usd=float(net_usd),
        max_drawdown=float(result.max_drawdown_r) * 100.0,
        payload={
            "sharpe_r": result.sharpe_r,
            "sortino_r": result.sortino_r,
            "expectancy_r": result.expectancy_r,
            "avg_rr_target": result.avg_rr_target,
            "avg_rr_achieved": result.avg_rr_achieved,
            "kill_zone_win_rate_pct": result.kill_zone_win_rate * 100.0,
            "no_kill_zone_win_rate_pct": result.no_kill_zone_win_rate * 100.0,
            "validated": result.validated,
            "validation_note": result.validation_note,
            "total_return_pct": 100.0 * net_usd / initial_balance if initial_balance else 0.0,
            "symbol": result.symbol,
            "timeframe": result.timeframe,
        },
    )

    by_strategy: dict[str, list[Any]] = {}
    by_regime: dict[str, list[Any]] = {}
    by_base: dict[str, list[Any]] = {}
    by_session: dict[str, list[Any]] = {}
    for t in closed:
        by_strategy.setdefault(t.strategy_id, []).append(t)
        by_regime.setdefault(t.regime_id, []).append(t)
        base = t.regime_id[:2] if t.regime_id and len(t.regime_id) >= 2 else "Q?"
        by_base.setdefault(base, []).append(t)
        by_session.setdefault(t.session_label or "Unknown", []).append(t)

    for sid, grp in sorted(by_strategy.items()):
        n, w, l, wrf, pf, ex = _agg_closed(grp)
        push(
            cache_type="STRATEGY_STATS",
            group_key=sid,
            strategy_id=sid,
            trades_count=n,
            wins=w,
            losses=l,
            win_rate=wrf * 100.0,
            profit_factor=pf,
            expectancy_r=ex,
            total_pnl_usd=sum(x.pnl_r for x in grp) * r_dollar,
            max_drawdown=0.0,
            payload={"insufficient_sample": n < 30},
        )

    for rid, grp in sorted(by_regime.items()):
        n, w, l, wrf, pf, ex = _agg_closed(grp)
        push(
            cache_type="REGIME_STATS",
            group_key=rid,
            regime_id=rid,
            trades_count=n,
            wins=w,
            losses=l,
            win_rate=wrf * 100.0,
            profit_factor=pf,
            expectancy_r=ex,
            payload={"insufficient_sample": n < 10},
        )

    for base, grp in sorted(by_base.items()):
        n, w, l, wrf, pf, ex = _agg_closed(grp)
        push(
            cache_type="BASE_REGIME_STATS",
            group_key=base,
            regime_id=base,
            trades_count=n,
            wins=w,
            losses=l,
            win_rate=wrf * 100.0,
            profit_factor=pf,
            expectancy_r=ex,
            payload={},
        )

    for sess, grp in sorted(by_session.items()):
        n, w, l, wrf, pf, ex = _agg_closed(grp)
        push(
            cache_type="SESSION_STATS",
            group_key=sess,
            condition=sess,
            trades_count=n,
            wins=w,
            losses=l,
            win_rate=wrf * 100.0,
            profit_factor=pf,
            expectancy_r=ex,
            payload={},
        )

    kz = [t for t in closed if t.kill_zone_active]
    nkz = [t for t in closed if not t.kill_zone_active]
    for label, grp in (("kill_zone", kz), ("no_kill_zone", nkz)):
        n, w, l, wrf, pf, ex = _agg_closed(grp)
        push(
            cache_type="CONDITION_STATS",
            group_key=label,
            condition=label,
            trades_count=n,
            wins=w,
            losses=l,
            win_rate=wrf * 100.0,
            profit_factor=pf,
            expectancy_r=ex,
            payload={},
        )

    hiconf = [t for t in closed if float(t.signal_confidence) >= 0.55]
    loconf = [t for t in closed if float(t.signal_confidence) < 0.55]
    for label, grp in (("high_confidence", hiconf), ("low_confidence", loconf)):
        n, w, l, wrf, pf, ex = _agg_closed(grp)
        push(
            cache_type="CONDITION_STATS",
            group_key=f"conf_{label}",
            condition=label,
            trades_count=n,
            wins=w,
            losses=l,
            win_rate=wrf * 100.0,
            profit_factor=pf,
            expectancy_r=ex,
            payload={},
        )

    all_regimes = sorted({row["regime_id"] for row in strategy_backend.get_registry()})
    slots = ["S01", "S02", "S03", "S04"]
    for rid in all_regimes:
        for slot in slots:
            grp = [t for t in closed if t.regime_id == rid and _strategy_slot(t.strategy_id) == slot]
            n, w, _, wrf, pf, ex = _agg_closed(grp)
            push(
                cache_type="STRATEGY_REGIME_MATRIX",
                group_key=f"{rid}__{slot}",
                regime_id=rid,
                condition=slot,
                trades_count=n,
                wins=w,
                losses=n - w,
                win_rate=(wrf * 100.0) if n >= 10 else 0.0,
                profit_factor=pf,
                expectancy_r=ex,
                payload={"display_wr": "--" if n < 10 else f"{wrf * 100.0:.1f}%", "n": n},
            )

    for sess, grp_sess in sorted(by_session.items()):
        for base, grp in sorted(by_base.items()):
            sub = [t for t in grp_sess if (t.regime_id or "")[:2] == base]
            n, w, l, wrf, pf, ex = _agg_closed(sub)
            if n == 0:
                continue
            push(
                cache_type="SESSION_REGIME_STATS",
                group_key=f"{sess}|{base}",
                regime_id=base,
                condition=sess,
                trades_count=n,
                wins=w,
                losses=l,
                win_rate=wrf * 100.0,
                profit_factor=pf,
                expectancy_r=ex,
                payload={},
            )

    dow_groups: dict[int, list[Any]] = {}
    for t in closed:
        d = _parse_dow(getattr(t, "signal_bar_time", "") or "")
        if d is None:
            continue
        dow_groups.setdefault(d, []).append(t)
    for d in range(5):
        grp = dow_groups.get(d, [])
        n, w, l, wrf, pf, ex = _agg_closed(grp)
        names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
        push(
            cache_type="DAY_OF_WEEK_STATS",
            group_key=names[d],
            condition=names[d],
            trades_count=n,
            wins=w,
            losses=l,
            win_rate=wrf * 100.0,
            profit_factor=pf,
            expectancy_r=ex,
            payload={},
        )

    freq: dict[str, int] = {}
    for t in closed:
        freq[t.regime_id] = freq.get(t.regime_id, 0) + 1
    total_c = len(closed) or 1
    for rid, cnt in sorted(freq.items(), key=lambda x: -x[1]):
        push(
            cache_type="REGIME_FREQUENCY",
            group_key=rid,
            regime_id=rid,
            trades_count=cnt,
            wins=0,
            losses=0,
            win_rate=100.0 * cnt / total_c,
            profit_factor=0.0,
            expectancy_r=0.0,
            payload={"note": "frequency among closed trades in this run", "count": cnt},
        )

    bucket_defs = [(0.10, 0.30), (0.30, 0.50), (0.50, 0.70), (0.70, 0.85)]
    for lo, hi in bucket_defs:
        grp = [t for t in closed if lo <= float(t.signal_confidence) < hi]
        n, w, l, wrf, pf, ex = _agg_closed(grp)
        label = f"{lo:.2f}-{hi:.2f}"
        push(
            cache_type="CONFIDENCE_BUCKETS",
            group_key=label,
            condition=label,
            trades_count=n,
            wins=w,
            losses=l,
            win_rate=wrf * 100.0,
            profit_factor=pf,
            expectancy_r=ex,
            payload={},
        )
    grp_top = [t for t in closed if float(t.signal_confidence) >= 0.85]
    n, w, l, wrf, pf, ex = _agg_closed(grp_top)
    push(
        cache_type="CONFIDENCE_BUCKETS",
        group_key="0.85-1.00",
        condition="0.85-1.00",
        trades_count=n,
        wins=w,
        losses=l,
        win_rate=wrf * 100.0,
        profit_factor=pf,
        expectancy_r=ex,
        payload={},
    )

    for sid in sorted(by_strategy.keys()):
        grp = sorted(by_strategy[sid], key=lambda x: x.bar_index)
        outcomes = [1 if t.result == "win" else 0 for t in grp]
        series: list[dict[str, float | int]] = []
        window = 30
        for i in range(len(outcomes)):
            a = max(0, i - window + 1)
            chunk = outcomes[a : i + 1]
            series.append({"trade_num": i + 1, "rolling_wr_pct": 100.0 * sum(chunk) / len(chunk)})
        push(
            cache_type="ROLLING_EDGE",
            group_key=sid,
            strategy_id=sid,
            trades_count=len(grp),
            wins=sum(outcomes),
            losses=len(outcomes) - sum(outcomes),
            win_rate=(sum(outcomes) / len(outcomes) * 100.0) if outcomes else 0.0,
            profit_factor=0.0,
            expectancy_r=0.0,
            payload={"series": series},
        )

    for sid, grp in sorted(by_strategy.items()):
        vals = [float(t.pnl_r) for t in grp]
        push(
            cache_type="RR_DISTRIBUTION",
            group_key=sid,
            strategy_id=sid,
            trades_count=len(vals),
            wins=sum(1 for t in grp if t.result == "win"),
            losses=sum(1 for t in grp if t.result == "loss"),
            win_rate=0.0,
            profit_factor=0.0,
            expectancy_r=float(sum(vals) / len(vals)) if vals else 0.0,
            payload={"pnl_r_values": vals},
        )

    conn.executemany(
        """
        INSERT OR REPLACE INTO analysis_cache VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        cache_batch,
    )


def save_signal_engine_backtest(result: Any, *, initial_balance: float = 10_000.0) -> dict[str, Any]:
    init_db()
    run_id = result.run_id
    trades_json = _json([_serialize_wf_trade(t) for t in result.trades])
    metrics = {
        "total_trades": result.total_trades,
        "wins": result.wins,
        "losses": result.losses,
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
        "sharpe_r": result.sharpe_r,
        "sortino_r": result.sortino_r,
        "max_drawdown_r": result.max_drawdown_r,
        "expectancy_r": result.expectancy_r,
        "avg_rr_target": result.avg_rr_target,
        "avg_rr_achieved": result.avg_rr_achieved,
        "validated": result.validated,
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "regime_id_filter": result.regime_id_filter,
    }
    equity_json = _json(list(result.equity_curve))
    with get_duckdb() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO signal_engine_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run_id,
                _now(),
                result.symbol,
                result.timeframe,
                result.regime_id_filter,
                _json(metrics),
                trades_json,
                equity_json,
                result.validation_note or "",
            ],
        )
        peak = float(result.equity_curve[0]) if result.equity_curve else float(initial_balance)
        for i, eq in enumerate(result.equity_curve):
            peak = max(peak, float(eq))
            dd_pct = (peak - float(eq)) / peak * 100.0 if peak else 0.0
            pnl_r_cum = (float(eq) - float(initial_balance)) / (float(initial_balance) * 0.01) if initial_balance else 0.0
            conn.execute(
                """
                INSERT OR REPLACE INTO equity_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [f"{run_id}_wf_{i:05d}", run_id, i, "", float(eq), float(dd_pct), float(pnl_r_cum)],
            )
        populate_all(conn, run_id, result, initial_balance)
    return {"run_id": run_id, "saved": True, "duckdb": str(DUCKDB_PATH)}


def list_signal_engine_runs(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    colnames = ["run_id", "created_at", "symbol", "timeframe", "regime_id_filter", "metrics_json", "validation_note"]
    with get_duckdb() as conn:
        rows = conn.execute(
            """
            SELECT run_id, created_at, symbol, timeframe, regime_id_filter, metrics_json, validation_note
            FROM signal_engine_runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [int(limit)],
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(zip(colnames, row))
        if item.get("metrics_json"):
            item["metrics"] = json.loads(item["metrics_json"])
        out.append(item)
    return out
