from __future__ import annotations

from dataclasses import asdict
from typing import Any

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
