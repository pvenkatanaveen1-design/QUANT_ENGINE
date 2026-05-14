from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from core.config_manager import ConfigManager
from core.models.signal import StrategyCandidate


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SLOT_ORDER = {"primary": 0, "secondary": 1, "confirmation": 2, "fallback": 3}
PAPER_STATUSES = {"paper_approved", "live_approved"}
LIVE_STATUSES = {"live_approved"}


class StrategyRegistryError(RuntimeError):
    pass


def _candidate_from_entry(entry: dict[str, Any]) -> StrategyCandidate:
    return StrategyCandidate(
        id=str(entry["id"]),
        name=str(entry["name"]),
        regime_id=str(entry["regime_id"]),
        slot=str(entry["slot"]),
        family=str(entry.get("family", "general")),
        status=str(entry.get("status", "not_tested")),
        enabled=bool(entry.get("enabled", False)),
        description=str(entry.get("description") or entry.get("regime_logic") or ""),
        logic_status=str(entry.get("logic_status", "name_only")),
        live_allowed=bool(entry.get("live_allowed", False)),
    )


def load_registry(path: str | Path = "config/strategy_registry.yaml") -> list[StrategyCandidate]:
    data = ConfigManager(PROJECT_ROOT).load_yaml(path, required_keys=["strategies"])
    entries = data["strategies"]
    if not isinstance(entries, list):
        raise StrategyRegistryError("strategies must be a list")
    candidates = [_candidate_from_entry(entry) for entry in entries]
    validate_registry(candidates)
    return candidates


def validate_registry(candidates: list[StrategyCandidate]) -> None:
    if len(candidates) != 208:
        raise StrategyRegistryError(f"Expected 208 strategies, found {len(candidates)}")
    ids = [candidate.id for candidate in candidates]
    duplicate_ids = [strategy_id for strategy_id, count in Counter(ids).items() if count > 1]
    if duplicate_ids:
        raise StrategyRegistryError(f"Duplicate strategy ids: {', '.join(duplicate_ids[:10])}")

    by_regime: dict[str, list[StrategyCandidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.slot not in SLOT_ORDER:
            raise StrategyRegistryError(f"Invalid slot {candidate.slot!r} for {candidate.id}")
        by_regime[candidate.regime_id].append(candidate)

    if len(by_regime) != 52:
        raise StrategyRegistryError(f"Expected 52 regimes, found {len(by_regime)}")
    bad = [regime_id for regime_id, items in by_regime.items() if len(items) != 4]
    if bad:
        raise StrategyRegistryError(f"Regimes without exactly four strategies: {', '.join(bad[:10])}")


def registry_by_regime(candidates: list[StrategyCandidate] | None = None) -> dict[str, list[StrategyCandidate]]:
    candidates = candidates or load_registry()
    grouped: dict[str, list[StrategyCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.regime_id].append(candidate)
    return {regime: sorted(items, key=lambda item: SLOT_ORDER[item.slot]) for regime, items in sorted(grouped.items())}


def get_candidates_for_regime(regime_id: str, mode: str = "research") -> tuple[list[StrategyCandidate], list[str]]:
    grouped = registry_by_regime()
    candidates = grouped.get(regime_id, [])
    if not candidates:
        return [], [f"No strategy registry entries found for {regime_id}."]

    if mode == "research":
        return candidates, ["Research mode shows all four candidates even when not tested."]
    if mode == "paper":
        allowed = [candidate for candidate in candidates if candidate.enabled and candidate.status in PAPER_STATUSES]
        if not allowed:
            return [], [f"{regime_id} has no paper-approved enabled strategies."]
        return allowed, ["Paper mode returned only enabled paper-approved strategies."]
    if mode == "live":
        allowed = [candidate for candidate in candidates if candidate.enabled and candidate.status in LIVE_STATUSES and candidate.live_allowed]
        if not allowed:
            return [], [f"{regime_id} has no live-approved enabled strategies. Live remains blocked."]
        return allowed, ["Live mode returned only enabled live-approved strategies."]
    raise ValueError("mode must be research, paper, or live")


def registry_summary() -> dict[str, Any]:
    candidates = load_registry()
    grouped = registry_by_regime(candidates)
    status_counts = Counter(candidate.status for candidate in candidates)
    family_counts = Counter(candidate.family for candidate in candidates)
    return {
        "total": len(candidates),
        "regimes": len(grouped),
        "status_counts": dict(status_counts),
        "family_counts": dict(family_counts),
        "all_live_allowed": all(candidate.live_allowed for candidate in candidates),
    }

