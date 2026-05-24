from __future__ import annotations

from dataclasses import asdict
from typing import Any

from systems.analysis import db as analysis_db
from systems.strategy_router import service


def get_registry(regime_id: str | None = None, family: str | None = None, status: str | None = None, slot: str | None = None) -> list[dict[str, Any]]:
    items = [asdict(candidate) for candidate in service.load_registry()]
    if regime_id:
        items = [item for item in items if item["regime_id"] == regime_id]
    if family:
        items = [item for item in items if item["family"] == family]
    if status:
        items = [item for item in items if item["status"] == status]
    if slot:
        items = [item for item in items if item["slot"] == slot]
    return items


def get_registry_summary() -> dict[str, Any]:
    return service.registry_summary()


def get_by_regime(regime_id: str, mode: str = "research") -> dict[str, Any]:
    candidates, reasons = service.get_candidates_for_regime(regime_id, mode=mode)
    return {"regime_id": regime_id, "mode": mode, "candidates": [asdict(candidate) for candidate in candidates], "reasons": reasons}


def research_enable_preview(strategy_id: str) -> dict[str, Any]:
    matches = [candidate for candidate in service.load_registry() if candidate.id == strategy_id]
    if not matches:
        return {"ok": False, "reason": f"Unknown strategy id {strategy_id}"}
    return {
        "ok": True,
        "strategy_id": strategy_id,
        "note": "Research display can be enabled later, but this endpoint does not approve paper or live trading.",
    }


def approval_preview(strategy_id: str, regime_id: str | None = None) -> dict[str, Any]:
    matches = [candidate for candidate in get_registry() if candidate["id"] == strategy_id]
    if not matches:
        return {"ok": False, "reason": f"Unknown strategy id {strategy_id}"}
    candidate = matches[0]
    regime_id = regime_id or candidate["regime_id"]
    runs = [run for run in analysis_db.list_backtest_runs(limit=500) if run["selected_strategy"] == strategy_id and run["selected_regime"] == regime_id]
    totals = {
        "runs": len(runs),
        "trades": sum(int((run.get("metrics") or {}).get("executed_simulated_trades") or 0) for run in runs),
        "wins": sum(int((run.get("metrics") or {}).get("wins") or 0) for run in runs),
        "losses": sum(int((run.get("metrics") or {}).get("losses") or 0) for run in runs),
        "net_pl": round(sum(float((run.get("metrics") or {}).get("net_pl") or 0.0) for run in runs), 2),
    }
    win_rate = 100.0 * totals["wins"] / max(totals["trades"], 1)
    profit_factors = [float((run.get("metrics") or {}).get("profit_factor") or 0.0) for run in runs]
    expectancy_values = [float((run.get("metrics") or {}).get("average_r") or 0.0) for run in runs]
    evidence = {
        **totals,
        "win_rate": round(win_rate, 2),
        "profit_factor_avg": round(sum(profit_factors) / len(profit_factors), 3) if profit_factors else 0.0,
        "expectancy_r_avg": round(sum(expectancy_values) / len(expectancy_values), 3) if expectancy_values else 0.0,
    }
    checks = {
        "minimum_runs": evidence["runs"] >= 1,
        "minimum_trades": evidence["trades"] >= 30,
        "positive_expectancy": evidence["expectancy_r_avg"] > 0.05,
        "profit_factor": evidence["profit_factor_avg"] >= 1.2,
        "registry_not_live": not bool(candidate.get("live_allowed")),
    }
    approved = all(checks.values())
    reason = "eligible for manual paper approval" if approved else "not enough validated evidence for paper approval"
    audit = analysis_db.record_strategy_approval(
        strategy_id=strategy_id,
        regime_id=regime_id,
        from_status=str(candidate.get("status")),
        to_status="paper_approved",
        approved=approved,
        reason=reason,
        evidence={"checks": checks, "evidence": evidence},
    )
    return {"ok": True, "approved": approved, "reason": reason, "strategy": candidate, "evidence": evidence, "checks": checks, "audit": audit}
