from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config_manager import ConfigManager
from systems.cockpit import db, regime_map
from systems.data import backend as data_backend
from systems.data.service import load_cleaned_rows
from systems.regime import backend as regime_backend
from systems.regime.service import calculate_feature_snapshot, detect_regime_for_rows
from systems.research import service as research_service
from systems.strategy.signals import evaluate_strategy_signal
from systems.strategy_router import backend as strategy_backend
from systems.strategy_router.service import get_candidates_for_regime


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SLOTS = ("primary", "secondary", "confirmation", "fallback")


def _config(path: str) -> dict[str, Any]:
    return ConfigManager(PROJECT_ROOT).load_yaml(path)


def _safe_round(value: Any, digits: int = 2) -> float | None:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _row_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _load_live_rows(symbol: str, timeframe: str, bars: int = 500) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    try:
        data_backend.fetch_mt5_bars(symbol.upper(), timeframe.upper(), bars=bars)
    except Exception as exc:
        warnings.append(f"MT5 refresh failed, using latest cleaned rows if present: {exc}")
    rows = load_cleaned_rows(symbol.upper(), timeframe.upper())
    return rows[-bars:], warnings


def _regime_def_by_id(regime_id: str) -> dict[str, Any]:
    for item in regime_map.full_regime_strategy_map().get("regimes", []):
        if item["regime_id"] == regime_id.upper():
            return item
    return {}


def _strategy_defs_by_slot(regime_id: str) -> dict[str, dict[str, Any]]:
    regime_def = _regime_def_by_id(regime_id)
    return {slot: dict(regime_def.get(slot) or {}) for slot in SLOTS}


def get_live_cockpit_state(symbol: str, timeframe: str, capital: float = 10000.0) -> dict[str, Any]:
    """
    Live cockpit banner state: current regime, current feature values, four
    strategy definitions, per-strategy signal evaluations, and risk values.
    Market data comes from MT5 refresh when available, then cleaned rows.
    """
    symbol = symbol.upper()
    timeframe = timeframe.upper()
    rows, warnings = _load_live_rows(symbol, timeframe)
    if not rows:
        return {"error": f"No data for {symbol}/{timeframe}", "warnings": warnings}

    regime_result = detect_regime_for_rows(rows, symbol, timeframe)
    features = calculate_feature_snapshot(rows)
    candidates, reasons = get_candidates_for_regime(regime_result.regime_id, mode="research")
    candidate_by_slot = {candidate.slot: asdict(candidate) for candidate in candidates}
    regime_def = _regime_def_by_id(regime_result.regime_id)
    strategy_defs = _strategy_defs_by_slot(regime_result.regime_id)

    signals: dict[str, Any] = {}
    for slot in SLOTS:
        strat_def = strategy_defs.get(slot) or {}
        candidate = candidate_by_slot.get(slot) or _strategy_by_id(str(strat_def.get("strategy_id", "")))
        if not strat_def and not candidate.get("id"):
            continue
        evaluation = evaluate_strategy_signal(rows, candidate, regime_result, symbol=symbol, timeframe=timeframe)
        signal = evaluation.signal
        signals[slot] = {
            "strategy_id": strat_def.get("strategy_id") or candidate.get("id"),
            "name": strat_def.get("name") or candidate.get("name"),
            "slot": slot,
            "signal_fn": strat_def.get("signal_fn") or candidate.get("signal_fn"),
            "signal_direction": (signal.direction.upper() if signal else "NONE"),
            "entry_price": signal.entry if signal else None,
            "stop_price": signal.stop if signal else None,
            "tp_price": signal.target if signal else None,
            "rr_ratio": _safe_round(abs(float(signal.target or 0.0) - float(signal.entry)) / max(abs(float(signal.entry) - float(signal.stop)), 1e-12), 2) if signal and signal.target is not None else None,
            "confidence": signal.confidence if signal else 0.0,
            "reason": evaluation.reason,
            "passed": evaluation.passed,
            "metadata": evaluation.metadata or {},
        }

    risk_cfg = _config("config/risk_rules.yaml")
    regimes_cfg = _config("config/regimes.yaml")
    risk_pct = float(risk_cfg.get("base_risk_per_trade_percent", risk_cfg.get("base_risk_percent", 1.0)) or 0.0)
    size_mult = float(regime_def.get("size_multiplier") or regime_def.get("risk_multiplier") or 0.0)
    risk_usd = float(capital) * risk_pct / 100.0
    feature_extra = features.extra or {}
    current = rows[-1]
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "warnings": warnings,
        "router_reasons": reasons,
        "regime": {
            "regime_id": regime_result.regime_id,
            "base_regime": regime_result.base_regime,
            "modifier": regime_result.modifier,
            "confidence": round(float(regime_result.confidence), 4),
            "tradable": bool(regime_result.tradable),
            "risk_posture": regime_result.risk_posture,
            "reasons": [reason.message for reason in regime_result.reasons],
        },
        "market_values": {
            "adx": _safe_round(features.adx, 2),
            "efficiency_ratio": _safe_round(features.efficiency_ratio, 4),
            "atr": _safe_round(features.atr, 6),
            "atr_percent": _safe_round(features.atr_percent, 6),
            "volatility_pctile": _safe_round(features.volatility_percentile, 1),
            "spread_pctile": _safe_round(features.spread_percentile, 1),
            "compression_pctile": _safe_round(features.compression_percentile, 1),
            "jump_z": _safe_round(features.jump_z, 3),
            "body_ratio": _safe_round(features.body_ratio, 3),
            "upper_wick_ratio": _safe_round(features.upper_wick_ratio, 3),
            "lower_wick_ratio": _safe_round(features.lower_wick_ratio, 3),
            "sweep_high": bool(features.sweep_high),
            "sweep_low": bool(features.sweep_low),
            "session_label": features.session_label,
            "kill_zone_active": bool(feature_extra.get("kill_zone_active", current.get("kill_zone_active", False))),
            "current_bar_time": str(current.get("time", "")),
            "current_close": current.get("close"),
            "current_spread": current.get("spread"),
            "institutional_trap_score": feature_extra.get("institutional_trap_score"),
            "retail_stop_zones": feature_extra.get("retail_stop_zones"),
            "liquidity_sweep_direction": feature_extra.get("liquidity_sweep_direction"),
            "news_proxy": feature_extra.get("news_proxy"),
        },
        "strategies": signals,
        "strategy_definitions": strategy_defs,
        "regime_definition": {
            "description": regime_def.get("description", ""),
            "detection_summary": regime_def.get("detection_summary", ""),
            "size_multiplier": size_mult,
            "risk_multiplier": regime_def.get("risk_multiplier", size_mult),
            "tradable": regime_def.get("tradable", False),
            "risk_posture": regime_def.get("risk_posture", ""),
            "thresholds_source": regime_def.get("thresholds_source", "config/regimes.yaml"),
            "modifier_definition": regime_def.get("modifier_definition", {}),
        },
        "risk_parameters": {
            "initial_capital": float(capital),
            "risk_per_trade_pct": risk_pct,
            "risk_per_trade_usd": round(risk_usd, 2),
            "size_multiplier": size_mult,
            "effective_risk_usd": round(risk_usd * size_mult, 2),
            "live_trading_enabled": False,
            "real_order_enabled": False,
        },
        "classification_thresholds": regimes_cfg.get("thresholds", {}),
    }


def get_regime_ranking(symbol: str, timeframe: str) -> list[dict[str, Any]]:
    """All 52 regimes sorted by latest tested primary result, then research EV prior."""
    symbol = symbol.upper()
    timeframe = timeframe.upper()
    mapping = regime_map.full_regime_strategy_map()
    out: list[dict[str, Any]] = []
    with db.get_conn() as conn:
        for regime_def in mapping.get("regimes", []):
            regime_id = regime_def["regime_id"]
            primary = regime_def["primary"]
            row = conn.execute(
                """
                SELECT run_id, net_profit_usd, win_rate, profit_factor, total_trades,
                       sharpe_ratio, max_drawdown_pct, kill_zone_win_rate,
                       institutional_trap_failures, sweep_no_reclaim_failures,
                       spread_rejection_count, validated, validation_note, created_at
                FROM backtest_runs
                WHERE regime_id = ? AND slot = 'primary'
                  AND upper(symbol) = upper(?) AND upper(timeframe) = upper(?)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (regime_id, symbol, timeframe),
            ).fetchone()
            expected_wr = [primary.get("expected_wr_low", 0.0), primary.get("expected_wr_high", 0.0)]
            if row:
                out.append(
                    {
                        "regime_id": regime_id,
                        "base_regime": regime_def["base_regime"],
                        "modifier": regime_def["modifier"],
                        "description": regime_def.get("description", ""),
                        "tested": True,
                        "run_id": row["run_id"],
                        "net_profit_usd": _safe_round(row["net_profit_usd"], 2),
                        "win_rate_pct": _safe_round((row["win_rate"] or 0.0) * 100.0, 1),
                        "profit_factor": _safe_round(row["profit_factor"], 2),
                        "total_trades": row["total_trades"] or 0,
                        "sharpe": _safe_round(row["sharpe_ratio"], 2),
                        "max_drawdown_pct": _safe_round(row["max_drawdown_pct"], 2),
                        "kill_zone_win_rate_pct": _safe_round((row["kill_zone_win_rate"] or 0.0) * 100.0, 1),
                        "institutional_trap_failures": row["institutional_trap_failures"] or 0,
                        "sweep_failures": row["sweep_no_reclaim_failures"] or 0,
                        "spread_rejections": row["spread_rejection_count"] or 0,
                        "validated": bool(row["validated"]),
                        "validation_note": row["validation_note"],
                        "tradable": regime_def.get("tradable", False),
                        "expected_ev_r": primary.get("expected_ev_r", 0.0),
                        "expected_wr_range": expected_wr,
                        "evidence": primary.get("evidence", []),
                        "created_at": row["created_at"],
                    }
                )
            else:
                out.append(
                    {
                        "regime_id": regime_id,
                        "base_regime": regime_def["base_regime"],
                        "modifier": regime_def["modifier"],
                        "description": regime_def.get("description", ""),
                        "tested": False,
                        "run_id": None,
                        "net_profit_usd": None,
                        "win_rate_pct": None,
                        "profit_factor": None,
                        "total_trades": 0,
                        "sharpe": None,
                        "max_drawdown_pct": None,
                        "kill_zone_win_rate_pct": None,
                        "institutional_trap_failures": 0,
                        "sweep_failures": 0,
                        "spread_rejections": 0,
                        "validated": False,
                        "validation_note": f"Not yet tested. Expected EV={float(primary.get('expected_ev_r') or 0.0):.2f}R, WR={float(expected_wr[0] or 0.0) * 100:.0f}-{float(expected_wr[1] or 0.0) * 100:.0f}%",
                        "tradable": regime_def.get("tradable", False),
                        "expected_ev_r": primary.get("expected_ev_r", 0.0),
                        "expected_wr_range": expected_wr,
                        "evidence": primary.get("evidence", []),
                        "created_at": None,
                    }
                )
    tested = sorted([row for row in out if row["tested"]], key=lambda row: float(row.get("net_profit_usd") or 0.0), reverse=True)
    untested = sorted([row for row in out if not row["tested"]], key=lambda row: float(row.get("expected_ev_r") or 0.0), reverse=True)
    return tested + untested


def get_strategy_backtest_detail(regime_id: str, symbol: str, timeframe: str) -> dict[str, Any]:
    """Latest stored cockpit result for each of the four slots in one regime."""
    regime_id = regime_id.upper()
    symbol = symbol.upper()
    timeframe = timeframe.upper()
    strategy_defs = _strategy_defs_by_slot(regime_id)
    detail: dict[str, Any] = {}
    with db.get_conn() as conn:
        for slot in SLOTS:
            strat_def = strategy_defs.get(slot, {})
            row = conn.execute(
                """
                SELECT * FROM backtest_runs
                WHERE regime_id = ? AND slot = ? AND upper(symbol) = upper(?) AND upper(timeframe) = upper(?)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (regime_id, slot, symbol, timeframe),
            ).fetchone()
            if row:
                run = _row_dict(row)
                trades = [_row_dict(item) for item in conn.execute("SELECT * FROM trade_log WHERE run_id = ? ORDER BY trade_number", (run["run_id"],)).fetchall()]
                equity = [_row_dict(item) for item in conn.execute("SELECT * FROM equity_snapshots WHERE run_id = ? ORDER BY trade_number", (run["run_id"],)).fetchall()]
                detail[slot] = {
                    "tested": True,
                    "strategy_id": run["strategy_id"],
                    "name": strat_def.get("name", ""),
                    "signal_fn": run["signal_fn"],
                    "slot": slot,
                    "total_trades": run["total_trades"],
                    "wins": run["wins"],
                    "losses": run["losses"],
                    "win_rate_pct": _safe_round((run["win_rate"] or 0.0) * 100.0, 1),
                    "profit_factor": _safe_round(run["profit_factor"], 2),
                    "sharpe": _safe_round(run["sharpe_ratio"], 2),
                    "sortino": _safe_round(run["sortino_ratio"], 2),
                    "max_drawdown_pct": _safe_round(run["max_drawdown_pct"], 2),
                    "net_profit_usd": _safe_round(run["net_profit_usd"], 2),
                    "expectancy_r": _safe_round(run["expectancy_r"], 3),
                    "avg_rr_target": _safe_round(run["avg_rr_target"], 2),
                    "avg_rr_achieved": _safe_round(run["avg_rr_achieved"], 2),
                    "avg_bars_held": _safe_round(run["avg_bars_held"], 1),
                    "kill_zone_win_rate_pct": _safe_round((run["kill_zone_win_rate"] or 0.0) * 100.0, 1),
                    "no_kill_zone_win_rate_pct": _safe_round((run["no_kill_zone_win_rate"] or 0.0) * 100.0, 1),
                    "kill_zone_trades": run["kill_zone_trades"],
                    "institutional_trap_failures": run["institutional_trap_failures"],
                    "sweep_failures": run["sweep_no_reclaim_failures"],
                    "spread_rejections": run["spread_rejection_count"],
                    "validated": bool(run["validated"]),
                    "validation_note": run["validation_note"],
                    "expected_wr_low": strat_def.get("expected_wr_low"),
                    "expected_wr_high": strat_def.get("expected_wr_high"),
                    "expected_rrr": strat_def.get("expected_rrr"),
                    "expected_ev_r": strat_def.get("expected_ev_r"),
                    "evidence": strat_def.get("evidence", []),
                    "filters": strat_def.get("filters", []),
                    "invalidations": strat_def.get("invalidations", []),
                    "trades": trades,
                    "equity_curve": equity,
                }
            else:
                detail[slot] = {
                    "tested": False,
                    "strategy_id": strat_def.get("strategy_id", f"{regime_id}_{slot}"),
                    "name": strat_def.get("name", ""),
                    "slot": slot,
                    "total_trades": 0,
                    "expected_wr_low": strat_def.get("expected_wr_low"),
                    "expected_wr_high": strat_def.get("expected_wr_high"),
                    "expected_rrr": strat_def.get("expected_rrr"),
                    "expected_ev_r": strat_def.get("expected_ev_r"),
                    "evidence": strat_def.get("evidence", []),
                    "entry_logic": strat_def.get("entry_logic", ""),
                    "filters": strat_def.get("filters", []),
                    "invalidations": strat_def.get("invalidations", []),
                    "trades": [],
                    "equity_curve": [],
                }
    return detail


def run_regime_backtest(
    regime_id: str,
    symbol: str,
    timeframe: str,
    capital: float = 10000.0,
    risk_pct: float | None = None,
) -> dict[str, Any]:
    """Run all four strategy slots for one regime on one timeframe and save cockpit DB rows."""
    result = run_regime_backtests(
        symbol=symbol,
        selected_regime=regime_id,
        timeframes=timeframe.upper(),
        lookback_months=6,
        bars=0,
        investment_amount=capital,
        source="mt5_demo",
        killzone_enabled=True,
        breakout_enabled=True,
        sweep_enabled=True,
        alpha_enabled=True,
        spread_filter_enabled=True,
        force_refresh=True,
    )
    result["risk_per_trade_pct"] = risk_pct if risk_pct is not None else _config("config/risk_rules.yaml").get("base_risk_per_trade_percent")
    result["strategy_detail"] = get_strategy_backtest_detail(regime_id, symbol, timeframe)
    return result


def build_playbook_json(symbol: str, timeframe: str, capital: float = 10000.0) -> dict[str, Any]:
    """Copyable live playbook JSON for the current regime. No live orders."""
    state = get_live_cockpit_state(symbol, timeframe, capital)
    if "error" in state:
        return state
    regimes_cfg = _config("config/regimes.yaml")
    risk_cfg = _config("config/risk_rules.yaml")
    sessions_cfg = _config("config/sessions.yaml")
    regime_id = state["regime"]["regime_id"]
    regime_def = _regime_def_by_id(regime_id)
    strategy_defs = _strategy_defs_by_slot(regime_id)
    strategies_export: list[dict[str, Any]] = []
    for slot in SLOTS:
        strat = strategy_defs.get(slot, {})
        sig = state["strategies"].get(slot, {})
        if not strat:
            continue
        strategies_export.append(
            {
                "slot": slot,
                "strategy_id": strat.get("strategy_id"),
                "name": strat.get("name"),
                "family": strat.get("family"),
                "signal_fn": strat.get("signal_fn"),
                "entry_logic": strat.get("entry_logic"),
                "conditions": {
                    "direction": sig.get("signal_direction", "NONE"),
                    "entry_trigger": strat.get("entry_trigger"),
                    "stop_rule": strat.get("stop_rule"),
                    "tp_rule": strat.get("tp_rule"),
                    "min_rr": strat.get("min_rr"),
                    "live_entry": sig.get("entry_price"),
                    "live_stop": sig.get("stop_price"),
                    "live_tp": sig.get("tp_price"),
                    "live_rr": sig.get("rr_ratio"),
                    "filters": strat.get("filters", []),
                    "invalidations": strat.get("invalidations", []),
                    "signal_reason": sig.get("reason"),
                },
                "expected_win_rate": [strat.get("expected_wr_low"), strat.get("expected_wr_high")],
                "expected_rrr": strat.get("expected_rrr"),
                "expected_ev_r": strat.get("expected_ev_r"),
                "size_multiplier": strat.get("size_mult"),
                "evidence": strat.get("evidence", []),
                "sources": strat.get("sources", []),
                "notes": strat.get("notes", ""),
            }
        )
    return {
        "export_version": "2.0",
        "generated_utc": state["generated_utc"],
        "platform": "Quanta Forex Control Center",
        "data_source": f"{symbol.upper()} {timeframe.upper()} MT5/read-only cleaned rows",
        "live_trading_enabled": False,
        "real_order_enabled": False,
        "current_regime": state["regime"],
        "market_values": state["market_values"],
        "strategies": strategies_export,
        "regime_definition": {
            "description": regime_def.get("description", ""),
            "detection_summary": regime_def.get("detection_summary", ""),
            "tradable": regime_def.get("tradable", False),
            "risk_posture": regime_def.get("risk_posture", ""),
            "size_multiplier": regime_def.get("size_multiplier"),
            "risk_multiplier": regime_def.get("risk_multiplier"),
            "base_wr_adjustment": regime_def.get("base_wr_adjustment"),
            "base_rrr_adjustment": regime_def.get("base_rrr_adjustment"),
            "modifier_definition": regime_def.get("modifier_definition", {}),
            "thresholds_source": "config/regimes.yaml",
        },
        "classification_thresholds": regimes_cfg.get("thresholds", {}),
        "risk_parameters": state["risk_parameters"],
        "risk_config": risk_cfg,
        "session_config": sessions_cfg,
        "research_sources": sorted(
            {source["key"]: source for strat in strategies_export for source in strat.get("sources", [])}.values(),
            key=lambda item: item.get("key", ""),
        ),
        "warnings": state.get("warnings", []),
    }


def _strategy_by_id(strategy_id: str) -> dict[str, Any]:
    for item in strategy_backend.get_registry():
        if item["id"] == strategy_id:
            return item
    return {"id": strategy_id, "regime_id": "", "slot": "", "signal_fn": ""}


def _detail_for_cockpit_save(
    *,
    detail: dict[str, Any],
    summary: dict[str, Any],
    strategy_id: str,
    request_query: dict[str, Any],
) -> dict[str, Any]:
    if detail.get("strategy"):
        return detail
    strategy = _strategy_by_id(strategy_id)
    metrics = detail.get("metrics") or summary
    period = detail.get("period") or summary.get("period") or {}
    return {
        "blocked": False,
        "symbol": detail.get("symbol") or request_query.get("symbol"),
        "timeframe": detail.get("timeframe") or summary.get("timeframe"),
        "selected_regime": detail.get("selected_regime") or strategy.get("regime_id"),
        "strategy": strategy,
        "strategy_family": detail.get("strategy_family") or strategy.get("family"),
        "period": period,
        "executed_simulated_trades": metrics.get("executed_simulated_trades") or summary.get("trades") or 0,
        "wins": metrics.get("wins") or summary.get("wins") or 0,
        "losses": metrics.get("losses") or summary.get("losses") or 0,
        "win_rate": metrics.get("win_rate") or summary.get("win_rate") or 0.0,
        "net_pl": metrics.get("net_pl") or summary.get("net_pl") or 0.0,
        "return_percent": metrics.get("return_percent") or summary.get("return_percent") or 0.0,
        "profit_factor": metrics.get("profit_factor") or summary.get("profit_factor") or 0.0,
        "average_r": metrics.get("average_r") or summary.get("average_r") or 0.0,
        "max_drawdown": metrics.get("max_drawdown") or summary.get("max_drawdown") or 0.0,
        "trades_all": detail.get("trades") or [],
        "equity_curve_all": detail.get("equity") or [],
        "fail_reason_counts": summary.get("fail_reason_counts") or {},
        "institutional_impact_flags": summary.get("institutional_impact_flags") or {},
        "api_request": {"method": "GET", "url": "/api/backtests/strategy-detail", "body": request_query},
    }


def initial_state(symbol: str = "EURUSD", timeframe: str = "M15") -> dict[str, Any]:
    mapping = regime_map.full_regime_strategy_map()
    try:
        current = regime_backend.current_regime_state(symbol.upper(), timeframe.upper())
    except Exception as exc:
        current = {"error": str(exc), "symbol": symbol.upper(), "timeframe": timeframe.upper()}
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe.upper(),
        "map": mapping,
        "current": current,
        "rankings": db.rankings(limit=25),
        "recent_runs": db.list_runs(limit=25),
        "api_links": api_links(symbol.upper(), timeframe.upper()),
    }


def api_links(symbol: str, timeframe: str) -> dict[str, str]:
    return {
        "state": f"/api/cockpit/state?symbol={symbol}&timeframe={timeframe}",
        "map": "/api/cockpit/map",
        "rankings": "/api/cockpit/rankings",
        "live_playbook": f"/api/cockpit/export/live-playbook?symbol={symbol}&timeframe={timeframe}",
        "run_strategy": "/api/cockpit/backtest/strategy",
        "run_regime": "/api/cockpit/backtest/regime",
        "run_full": "/api/cockpit/backtest/full",
    }


def live_playbook(symbol: str = "EURUSD", timeframe: str = "M15") -> dict[str, Any]:
    return build_playbook_json(symbol, timeframe, capital=10000.0)


def run_strategy_backtest(
    *,
    symbol: str,
    selected_regime: str,
    selected_strategy: str,
    timeframes: str = "M15,H1,H4,D1",
    lookback_months: int = 6,
    bars: int = 0,
    investment_amount: float = 10000.0,
    source: str = "mt5_demo",
    killzone_enabled: bool = True,
    breakout_enabled: bool = True,
    sweep_enabled: bool = True,
    alpha_enabled: bool = True,
    spread_filter_enabled: bool = True,
    force_refresh: bool = False,
) -> dict[str, Any]:
    payload = research_service.run_strategy_detail_matrix(
        symbol=symbol.upper(),
        selected_regime=selected_regime.upper(),
        selected_strategy=selected_strategy,
        timeframes=timeframes,
        lookback_months=lookback_months,
        bars=bars,
        investment_amount=investment_amount,
        source=source,
        killzone_enabled=killzone_enabled,
        breakout_enabled=breakout_enabled,
        sweep_enabled=sweep_enabled,
        alpha_enabled=alpha_enabled,
        spread_filter_enabled=spread_filter_enabled,
        force_refresh=force_refresh,
    )
    saved_ids: list[str] = []
    request_query = payload.get("api_request", {}).get("query", {})
    for item in payload.get("results", []):
        detail = item.get("json_copy") or {}
        if isinstance(detail, dict) and not detail.get("blocked"):
            savable = _detail_for_cockpit_save(
                detail=detail,
                summary=item,
                strategy_id=selected_strategy,
                request_query=request_query,
            )
            saved_ids.append(db.save_backtest_result(savable, request=request_query))
    payload["cockpit_saved_run_ids"] = saved_ids
    payload["cockpit_rankings"] = db.rankings(limit=25)
    return payload


def run_regime_backtests(
    *,
    symbol: str,
    selected_regime: str,
    timeframes: str = "M15,H1,H4,D1",
    lookback_months: int = 6,
    bars: int = 0,
    investment_amount: float = 10000.0,
    source: str = "mt5_demo",
    killzone_enabled: bool = True,
    breakout_enabled: bool = True,
    sweep_enabled: bool = True,
    alpha_enabled: bool = True,
    spread_filter_enabled: bool = True,
    force_refresh: bool = False,
) -> dict[str, Any]:
    selected_regime = selected_regime.upper()
    strategies = strategy_backend.get_by_regime(selected_regime, mode="research").get("candidates", [])
    matrix: list[dict[str, Any]] = []
    saved_ids: list[str] = []
    child_payloads: list[dict[str, Any]] = []
    for strategy in strategies:
        child = run_strategy_backtest(
            symbol=symbol,
            selected_regime=selected_regime,
            selected_strategy=strategy["id"],
            timeframes=timeframes,
            lookback_months=lookback_months,
            bars=bars,
            investment_amount=investment_amount,
            source=source,
            killzone_enabled=killzone_enabled,
            breakout_enabled=breakout_enabled,
            sweep_enabled=sweep_enabled,
            alpha_enabled=alpha_enabled,
            spread_filter_enabled=spread_filter_enabled,
            force_refresh=force_refresh,
        )
        child_payloads.append(child)
        saved_ids.extend(child.get("cockpit_saved_run_ids") or [])
        for row in child.get("results", []):
            matrix.append(
                {
                    "regime_id": row.get("regime_id"),
                    "quadrant": row.get("quadrant"),
                    "modifier": row.get("modifier"),
                    "strategy_id": row.get("strategy_id"),
                    "strategy_name": row.get("strategy_name"),
                    "slot": strategy.get("slot"),
                    "family": strategy.get("family"),
                    "signal_fn": strategy.get("signal_fn"),
                    "timeframe": row.get("timeframe"),
                    "bars": row.get("bars"),
                    "blocked": row.get("blocked", False),
                    "reason": row.get("reason"),
                    "trades": row.get("trades"),
                    "wins": row.get("wins"),
                    "losses": row.get("losses"),
                    "win_rate": row.get("win_rate"),
                    "net_pl": row.get("net_pl"),
                    "return_percent": row.get("return_percent"),
                    "profit_factor": row.get("profit_factor"),
                    "expectancy": row.get("expectancy"),
                    "average_r": row.get("average_r"),
                    "max_drawdown": row.get("max_drawdown"),
                    "fail_reason_counts": row.get("fail_reason_counts"),
                    "institutional_impact_flags": row.get("institutional_impact_flags"),
                }
            )
    ranked = sorted(
        [item for item in matrix if not item.get("blocked")],
        key=lambda item: (float(item.get("net_pl") or 0.0), float(item.get("profit_factor") or 0.0), int(item.get("trades") or 0)),
        reverse=True,
    )
    return {
        "blocked": False,
        "label": "cockpit_regime_matrix",
        "symbol": symbol.upper(),
        "selected_regime": selected_regime,
        "timeframes": research_service.parse_timeframes(timeframes),
        "lookback_months": lookback_months,
        "investment_amount": investment_amount,
        "rules": {
            "killzone_enabled": killzone_enabled,
            "breakout_enabled": breakout_enabled,
            "sweep_enabled": sweep_enabled,
            "alpha_enabled": alpha_enabled,
            "spread_filter_enabled": spread_filter_enabled,
            "live_orders": False,
        },
        "strategies": strategies,
        "matrix": matrix,
        "ranked": ranked,
        "children": child_payloads,
        "cockpit_saved_run_ids": saved_ids,
        "cockpit_rankings": db.rankings(limit=25),
        "api_request": {
            "method": "POST",
            "url": "/api/cockpit/backtest/regime",
            "body": {
                "symbol": symbol.upper(),
                "selected_regime": selected_regime,
                "timeframes": timeframes,
                "lookback_months": lookback_months,
                "bars": bars,
                "investment_amount": investment_amount,
                "source": source,
                "killzone_enabled": killzone_enabled,
                "breakout_enabled": breakout_enabled,
                "sweep_enabled": sweep_enabled,
                "alpha_enabled": alpha_enabled,
                "spread_filter_enabled": spread_filter_enabled,
                "force_refresh": force_refresh,
            },
        },
    }


def run_full_backtests(
    *,
    symbol: str,
    timeframe: str = "M15",
    bars: int = 0,
    max_strategies: int = 208,
    source: str = "mt5_demo",
    killzone_enabled: bool = True,
    breakout_enabled: bool = True,
    sweep_enabled: bool = True,
    alpha_enabled: bool = True,
    spread_filter_enabled: bool = True,
) -> dict[str, Any]:
    registry = strategy_backend.get_registry()[: max(1, int(max_strategies))]
    results: list[dict[str, Any]] = []
    saved_ids: list[str] = []
    for strategy in registry:
        child = run_strategy_backtest(
            symbol=symbol,
            selected_regime=strategy["regime_id"],
            selected_strategy=strategy["id"],
            timeframes=timeframe.upper(),
            lookback_months=6,
            bars=bars or 5000,
            investment_amount=10000.0,
            source=source,
            killzone_enabled=killzone_enabled,
            breakout_enabled=breakout_enabled,
            sweep_enabled=sweep_enabled,
            alpha_enabled=alpha_enabled,
            spread_filter_enabled=spread_filter_enabled,
            force_refresh=False,
        )
        saved_ids.extend(child.get("cockpit_saved_run_ids") or [])
        for row in child.get("results", []):
            results.append(
                {
                    "strategy_id": strategy["id"],
                    "regime_id": strategy["regime_id"],
                    "blocked": row.get("blocked", False),
                    "reason": row.get("reason"),
                    "run_id": row.get("run_id"),
                    "trades": row.get("trades", 0),
                    "win_rate": row.get("win_rate", 0.0),
                    "net_pl": row.get("net_pl", 0.0),
                    "profit_factor": row.get("profit_factor", 0.0),
                    "expectancy_r": row.get("average_r", 0.0),
                }
            )
    ranked = sorted(
        [item for item in results if not item.get("blocked")],
        key=lambda item: (float(item.get("expectancy_r") or 0.0), float(item.get("profit_factor") or 0.0), int(item.get("trades") or 0)),
        reverse=True,
    )
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe.upper(),
        "strategies_requested": len(registry),
        "completed": len(results),
        "blocked": sum(1 for item in results if item.get("blocked")),
        "ranked": ranked,
        "results": results,
        "cockpit_saved_run_ids": saved_ids,
        "cockpit_rankings": db.rankings(limit=25),
        "api_request": {
            "method": "POST",
            "url": "/api/cockpit/backtest/full",
            "body": {
                "symbol": symbol.upper(),
                "timeframe": timeframe.upper(),
                "bars": bars,
                "max_strategies": max_strategies,
                "source": source,
                "killzone_enabled": killzone_enabled,
                "breakout_enabled": breakout_enabled,
                "sweep_enabled": sweep_enabled,
                "alpha_enabled": alpha_enabled,
                "spread_filter_enabled": spread_filter_enabled,
            },
        },
    }
