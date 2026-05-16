"""
Dashboard JSON API: current regime, backtest ranking, per-regime summaries, run-all-slots backtest.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from config.regimes import regimes as regime_id_list
from core.models.backtest import BacktestRun, get_backtest_db
from systems.data.service import load_cleaned_rows
from systems.regime import service as regime_service
from systems.research import service as research_service
from systems.strategy_router.service import get_strategies_by_regime

dashboard_router = APIRouter()


def _kill_zone_tranche(trades: list[dict[str, Any]]) -> tuple[float | None, float | None, int, int]:
    if not trades:
        return None, None, 0, 0
    kz = [t for t in trades if t.get("kill_zone_active")]
    nkz = [t for t in trades if not t.get("kill_zone_active")]
    kz_wins = sum(1 for t in kz if float(t.get("pnl") or 0) > 0)
    nkz_wins = sum(1 for t in nkz if float(t.get("pnl") or 0) > 0)
    kz_wr = kz_wins / len(kz) if kz else None
    nkz_wr = nkz_wins / len(nkz) if nkz else None
    return kz_wr, nkz_wr, len(kz), len(nkz)


def _failure_counts(scenario: dict[str, Any]) -> tuple[int, int, int]:
    fail_reasons = scenario.get("fail_reason_counts") or {}
    trap_low = 0
    for ev in scenario.get("failure_events") or []:
        try:
            score = float(ev.get("trap_score") if ev.get("trap_score") is not None else 100.0)
        except (TypeError, ValueError):
            score = 100.0
        if score < 60.0:
            trap_low += 1
    sweep = int(fail_reasons.get("sweep failed", 0) or 0) + int(fail_reasons.get("liquidity sweep", 0) or 0)
    spread = int(fail_reasons.get("spread too high", 0) or 0)
    return trap_low, sweep, spread


def _scenario_to_equity_json(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    curve = scenario.get("equity_curve_all") or scenario.get("equity_curve") or []
    out: list[dict[str, Any]] = []
    for i, pt in enumerate(curve):
        row = dict(pt) if isinstance(pt, dict) else {"value": pt}
        row.setdefault("trade_no", i + 1)
        out.append(row)
    return out


def _backtest_run_from_scenario(
    *,
    regime_id: str,
    strategy_id: str,
    slot: str,
    symbol: str,
    timeframe: str,
    investment: float,
    scenario: dict[str, Any],
) -> BacktestRun:
    if scenario.get("blocked"):
        return BacktestRun(
            regime_id=regime_id,
            strategy_id=strategy_id,
            slot=slot,
            symbol=symbol.upper(),
            timeframe=timeframe.upper(),
            investment=investment,
            total_trades=0,
            wins=0,
            losses=0,
            win_rate=0.0,
            profit_factor=0.0,
            sharpe=None,
            sortino=None,
            max_drawdown=0.0,
            expectancy=0.0,
            net_profit=0.0,
            avg_rr_achieved=0.0,
            kill_zone_win_rate=None,
            no_kill_zone_win_rate=None,
            kill_zone_count=0,
            no_kill_zone_count=0,
            trades_json=[],
            equity_curve_json=[],
            settings_json={
                "killzone": True,
                "sweep": True,
                "alpha": True,
                "spread_filter": True,
                "blocked": True,
            },
            validated=False,
            validation_note=str(scenario.get("reason") or scenario.get("label") or "blocked"),
            institutional_trap_failures=0,
            sweep_failures=0,
            spread_rejections=0,
        )

    trades = list(scenario.get("trades_all") or scenario.get("trades") or [])
    kz_wr, nkz_wr, kz_n, nkz_n = _kill_zone_tranche(trades)
    trap_f, sweep_f, spread_f = _failure_counts(scenario)
    win_rate_pct = float(scenario.get("win_rate") or 0.0)
    win_rate_frac = win_rate_pct / 100.0 if win_rate_pct > 1.0 + 1e-6 else win_rate_pct

    return BacktestRun(
        regime_id=regime_id,
        strategy_id=strategy_id,
        slot=slot,
        symbol=symbol.upper(),
        timeframe=timeframe.upper(),
        investment=investment,
        total_trades=int(scenario.get("executed_simulated_trades") or 0),
        wins=int(scenario.get("wins") or 0),
        losses=int(scenario.get("losses") or 0),
        win_rate=win_rate_frac,
        profit_factor=float(scenario.get("profit_factor") or 0.0),
        sharpe=None,
        sortino=None,
        max_drawdown=float(scenario.get("max_drawdown") or 0.0),
        expectancy=float(scenario.get("average_r") or 0.0),
        net_profit=float(scenario.get("net_pl") or 0.0),
        avg_rr_achieved=float(scenario.get("average_r") or 0.0),
        kill_zone_win_rate=kz_wr,
        no_kill_zone_win_rate=nkz_wr,
        kill_zone_count=kz_n,
        no_kill_zone_count=nkz_n,
        trades_json=trades,
        equity_curve_json=_scenario_to_equity_json(scenario),
        settings_json={
            "killzone": True,
            "sweep": True,
            "alpha": True,
            "spread_filter": True,
        },
        validated=False,
        validation_note="",
        institutional_trap_failures=trap_f,
        sweep_failures=sweep_f,
        spread_rejections=spread_f,
    )


def _empty_slot_payload(strategy_id: str) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "total_trades": None,
        "win_rate": None,
        "profit_factor": None,
        "net_profit": None,
        "sharpe": None,
        "max_drawdown": None,
        "expectancy": None,
        "kill_zone_win_rate": None,
        "institutional_trap_failures": None,
        "sweep_failures": None,
        "spread_rejections": None,
        "trades": None,
        "equity_curve": None,
        "validated": None,
        "validation_note": None,
    }


@dashboard_router.get("/current-regime")
async def current_regime(
    symbol: str = "EURUSD",
    timeframe: str = "M15",
    bars: int = 500,
) -> dict[str, Any]:
    """
    Current regime (RegimeResult), feature snapshot (RegimeFeatureSet), and four playbook strategies.
    """
    sym, tf = symbol.upper(), timeframe.upper()
    full_rows = load_cleaned_rows(sym, tf)
    rows = full_rows[-int(bars) :] if len(full_rows) > int(bars) else full_rows
    regime = regime_service.detect_regime_for_rows(full_rows, symbol=sym, timeframe=tf)
    features = regime_service.calculate_feature_snapshot(rows)
    strategies = get_strategies_by_regime(regime.regime_id)
    return {
        "regime": regime_service.regime_to_dict(regime),
        "market_values": asdict(features),
        "strategies": [asdict(s) for s in strategies],
    }


@dashboard_router.get("/ranking")
async def ranking(
    symbol: str = "EURUSD",
    timeframe: str = "M15",
    investment: float = 10000.0,
    db: Session = Depends(get_backtest_db),
) -> list[dict[str, Any]]:
    """
    All catalogue regimes with the latest primary backtest (else latest any-slot), sorted by net_profit desc.
    """
    _ = investment  # reserved for future risk-normalized ranking
    sym, tf = symbol.upper(), timeframe.upper()
    results: list[dict[str, Any]] = []
    for rid in regime_id_list:
        run = db.execute(
            select(BacktestRun)
            .where(
                BacktestRun.regime_id == rid,
                BacktestRun.slot == "primary",
                BacktestRun.symbol == sym,
                BacktestRun.timeframe == tf,
            )
            .order_by(desc(BacktestRun.created_at))
            .limit(1)
        ).scalar_one_or_none()
        if run is None:
            run = db.execute(
                select(BacktestRun)
                .where(
                    BacktestRun.regime_id == rid,
                    BacktestRun.symbol == sym,
                    BacktestRun.timeframe == tf,
                )
                .order_by(desc(BacktestRun.created_at))
                .limit(1)
            ).scalar_one_or_none()
        parts = rid.split("_", 1)
        base, modifier = parts[0], parts[1] if len(parts) > 1 else ""
        results.append(
            {
                "regime_id": rid,
                "base": base,
                "modifier": modifier,
                "net_profit": run.net_profit if run else None,
                "win_rate": run.win_rate if run else None,
                "profit_factor": run.profit_factor if run else None,
                "total_trades": run.total_trades if run else None,
                "sharpe": run.sharpe if run else None,
                "max_drawdown": run.max_drawdown if run else None,
                "kill_zone_win_rate": run.kill_zone_win_rate if run else None,
                "institutional_trap_failures": run.institutional_trap_failures if run else None,
                "sweep_failures": run.sweep_failures if run else None,
                "spread_rejections": run.spread_rejections if run else None,
                "last_run": run.created_at.isoformat() if run and run.created_at else None,
                "tested": run is not None,
                "status": "tested" if run else "not_tested",
            }
        )

    results.sort(
        key=lambda x: x["net_profit"] if x["net_profit"] is not None else -1e9,
        reverse=True,
    )
    return results


@dashboard_router.get("/backtest-summary/{regime_id}")
async def backtest_summary(
    regime_id: str,
    symbol: str = "EURUSD",
    timeframe: str = "M15",
    db: Session = Depends(get_backtest_db),
) -> dict[str, Any]:
    rid_key = regime_id.strip().upper()
    sym, tf = symbol.upper(), timeframe.upper()
    runs = db.execute(
        select(BacktestRun)
        .where(
            BacktestRun.regime_id == rid_key,
            BacktestRun.symbol == sym,
            BacktestRun.timeframe == tf,
        )
        .order_by(desc(BacktestRun.created_at))
    ).scalars().all()

    by_slot: dict[str, dict[str, Any]] = {}
    for run in runs:
        if not run.slot or run.slot in by_slot:
            continue
        by_slot[run.slot] = {
            "strategy_id": run.strategy_id,
            "total_trades": run.total_trades,
            "win_rate": run.win_rate,
            "profit_factor": run.profit_factor,
            "net_profit": run.net_profit,
            "sharpe": run.sharpe,
            "max_drawdown": run.max_drawdown,
            "expectancy": run.expectancy,
            "kill_zone_win_rate": run.kill_zone_win_rate,
            "institutional_trap_failures": run.institutional_trap_failures,
            "sweep_failures": run.sweep_failures,
            "spread_rejections": run.spread_rejections,
            "trades": run.trades_json,
            "equity_curve": run.equity_curve_json,
            "validated": run.validated,
            "validation_note": run.validation_note,
        }

    merged: dict[str, Any] = {}
    for strat in get_strategies_by_regime(rid_key):
        merged[strat.slot] = by_slot.get(strat.slot) or _empty_slot_payload(strat.id)
    return merged


@dashboard_router.post("/run-backtest/{regime_id}")
async def run_backtest_for_regime(
    regime_id: str,
    symbol: str = "EURUSD",
    timeframe: str = "M15",
    investment: float = 10000.0,
    bars: int = 17280,
    db: Session = Depends(get_backtest_db),
) -> dict[str, Any]:
    """Run scenario backtest for each playbook slot and persist a BacktestRun row."""
    rid_key = regime_id.strip().upper()
    strategies = get_strategies_by_regime(rid_key)
    results: dict[str, BacktestRun] = {}
    for strat in strategies:
        scenario = research_service.run_scenario(
            symbol=symbol,
            timeframe=timeframe,
            selected_regime=rid_key,
            selected_strategy=strat.id,
            investment_amount=investment,
            bars=int(bars),
            killzone_enabled=True,
            breakout_enabled=True,
            sweep_enabled=True,
            alpha_enabled=True,
            spread_filter_enabled=True,
            save_result=False,
            regime_scope=rid_key,
        )
        db_run = _backtest_run_from_scenario(
            regime_id=rid_key,
            strategy_id=strat.id,
            slot=strat.slot,
            symbol=symbol,
            timeframe=timeframe,
            investment=investment,
            scenario=scenario,
        )
        db.add(db_run)
        db.commit()
        db.refresh(db_run)
        results[strat.slot] = db_run
    return {"success": True, "runs": len(results)}