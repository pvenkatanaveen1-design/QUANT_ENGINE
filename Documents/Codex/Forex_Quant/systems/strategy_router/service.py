from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.config_manager import ConfigManager
from core.models.signal import StrategyCandidate
from systems.strategy.signals import SIGNAL_CODE_TO_TEMPLATE


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SLOT_ORDER = {"primary": 0, "secondary": 1, "confirmation": 2, "fallback": 3}
PAPER_STATUSES = {"paper_approved", "live_approved"}
LIVE_STATUSES = {"live_approved"}
_EXPECTED_STRATEGIES = 52 * 4
_IMPLEMENTED_SIGNAL_FNS = frozenset(SIGNAL_CODE_TO_TEMPLATE)


class StrategyRegistryError(RuntimeError):
    pass


def _family_for_signal_fn(signal_fn: str, fallback: str) -> str:
    fn = (signal_fn or "").strip()
    if fn.startswith("S01") or fn.startswith("S07"):
        return "trend_momentum"
    if fn.startswith("S02"):
        return "breakout"
    if fn.startswith("S03") or fn.startswith("S06"):
        return "mean_reversion"
    if fn.startswith("S04") or fn.startswith("S05"):
        return "liquidity"
    if fn.startswith("S08"):
        return "defensive"
    return fallback


def _candidate_from_entry(entry: dict[str, Any]) -> StrategyCandidate:
    regime_id = str(entry.get("regime_id") or entry.get("regime") or "").strip()
    signal_fn = str(entry.get("signal_fn") or "").strip()
    family = str(entry.get("family") or _family_for_signal_fn(signal_fn, "general"))
    size_ov = entry.get("size_override")
    size_override = float(size_ov) if size_ov is not None and size_ov != "" else None
    research_active = signal_fn in _IMPLEMENTED_SIGNAL_FNS
    logic_status = str(entry.get("logic_status") or ("template_executable" if research_active else "name_only"))
    return StrategyCandidate(
        id=str(entry["id"]),
        name=str(entry["name"]),
        regime_id=regime_id,
        slot=str(entry["slot"]),
        family=family,
        status=str(entry.get("status", "not_tested")),
        enabled=bool(entry.get("enabled", False)),
        description=str(entry.get("description") or entry.get("regime_logic") or ""),
        logic_status=logic_status,
        research_active=research_active,
        live_allowed=bool(entry.get("live_allowed", False)),
        signal_fn=signal_fn,
        win_rate_low=float(entry.get("win_rate_low") or 0.0),
        win_rate_high=float(entry.get("win_rate_high") or 0.0),
        rrr=float(entry.get("rrr") or 0.0),
        ev=float(entry.get("ev") or 0.0),
        evidence=str(entry.get("evidence") or ""),
        size_override=size_override,
        notes=str(entry.get("notes") or ""),
    )


def load_registry(path: str | Path = "config/strategy_registry.yaml") -> list[StrategyCandidate]:
    data = ConfigManager(PROJECT_ROOT).load_yaml(path, required_keys=["strategies"])
    entries = data["strategies"]
    if not isinstance(entries, list):
        raise StrategyRegistryError("strategies must be a list")
    candidates = [_candidate_from_entry(entry) for entry in entries]
    validate_registry(candidates)
    return candidates


def _router_validation_cfg() -> dict[str, Any]:
    raw = ConfigManager(PROJECT_ROOT).load_yaml("config/strategy_router.yaml")
    return (raw.get("registry") or {}) if isinstance(raw, dict) else {}


def validate_registry(candidates: list[StrategyCandidate]) -> None:
    if not candidates:
        raise StrategyRegistryError("Strategy registry empty — check config/strategy_registry.yaml")

    cfg = _router_validation_cfg()
    strict = bool(cfg.get("strict_blueprint", False))

    ids = [candidate.id for candidate in candidates]
    duplicate_ids = [strategy_id for strategy_id, count in Counter(ids).items() if count > 1]
    if duplicate_ids:
        raise StrategyRegistryError(f"Duplicate strategy ids: {', '.join(duplicate_ids[:10])}")

    by_regime: dict[str, list[StrategyCandidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.slot not in SLOT_ORDER:
            raise StrategyRegistryError(f"Invalid slot {candidate.slot!r} for {candidate.id}")
        by_regime[candidate.regime_id].append(candidate)

    for regime_id, items in by_regime.items():
        if len(items) > 4:
            raise StrategyRegistryError(f"Regime {regime_id} has more than four strategies ({len(items)}).")
        slots = [item.slot for item in items]
        if len(slots) != len(set(slots)):
            raise StrategyRegistryError(f"Duplicate strategy slots for regime {regime_id}.")

    if strict:
        if len(candidates) != _EXPECTED_STRATEGIES:
            raise StrategyRegistryError(f"strict_blueprint: expected {_EXPECTED_STRATEGIES} strategies, found {len(candidates)}")
        if len(by_regime) != 52:
            raise StrategyRegistryError(f"strict_blueprint: expected 52 regimes, found {len(by_regime)}")
        bad = [regime_id for regime_id, items in by_regime.items() if len(items) != 4]
        if bad:
            raise StrategyRegistryError(f"strict_blueprint: regimes without exactly four strategies: {', '.join(bad[:10])}")


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


def get_strategies_by_regime(regime_id: str, mode: str = "research") -> list[StrategyCandidate]:
    """All four playbook strategies for a regime (research mode by default)."""
    candidates, _ = get_candidates_for_regime(regime_id, mode=mode)
    return candidates


def registry_summary() -> dict[str, Any]:
    candidates = load_registry()
    grouped = registry_by_regime(candidates)
    status_counts = Counter(candidate.status for candidate in candidates)
    family_counts = Counter(candidate.family for candidate in candidates)
    research_active = sum(1 for candidate in candidates if candidate.research_active)
    paper_enabled = sum(1 for candidate in candidates if candidate.enabled and candidate.status in PAPER_STATUSES)
    live_enabled = sum(1 for candidate in candidates if candidate.enabled and candidate.status in LIVE_STATUSES and candidate.live_allowed)
    return {
        "total": len(candidates),
        "regimes": len(grouped),
        "research_active": research_active,
        "research_inactive": len(candidates) - research_active,
        "all_research_active": research_active == len(candidates),
        "paper_enabled": paper_enabled,
        "live_enabled": live_enabled,
        "status_counts": dict(status_counts),
        "family_counts": dict(family_counts),
        "all_live_allowed": all(candidate.live_allowed for candidate in candidates),
    }


def run_strategy_signals(symbol: str, timeframe: str, mode: str = "research") -> dict[str, Any]:
    """Evaluate the four playbook slots for the detected regime on the latest cleaned bars."""
    from systems.data.service import load_cleaned_rows
    from systems.regime import service as regime_service
    from systems.strategy.signals import evaluate_strategy_signal

    sym, tf = symbol.upper(), timeframe.upper()
    rows = load_cleaned_rows(sym, tf)
    detected = regime_service.detect_regime_for_rows(rows, symbol=sym, timeframe=tf)
    candidates, playbook_reasons = get_candidates_for_regime(detected.regime_id, mode=mode)
    regime_payload = asdict(detected)
    out: list[dict[str, Any]] = []
    for cand in candidates:
        strat = asdict(cand)
        eva = evaluate_strategy_signal(rows, strat, detected, symbol=sym, timeframe=tf)
        block = eva.to_dict()
        block["registry"] = {
            "id": cand.id,
            "slot": cand.slot,
            "name": cand.name,
            "signal_fn": cand.signal_fn,
            "win_rate_low": cand.win_rate_low,
            "win_rate_high": cand.win_rate_high,
            "rrr": cand.rrr,
            "ev_prior_r": cand.ev,
            "evidence": cand.evidence,
            "status": cand.status,
            "enabled": cand.enabled,
            "logic_status": cand.logic_status,
            "research_active": cand.research_active,
            "live_allowed": cand.live_allowed,
            "size_override": cand.size_override,
        }
        sig = eva.signal
        direction = ((sig.direction or "").lower()) if sig else ""
        if direction == "long":
            block["signal_direction"] = "BUY"
        elif direction == "short":
            block["signal_direction"] = "SELL"
        else:
            block["signal_direction"] = "NONE"
        if sig and sig.target is not None:
            risk = abs(float(sig.entry) - float(sig.stop)) or 1e-12
            reward = abs(float(sig.target) - float(sig.entry))
            block["rr_measured"] = round(reward / risk, 3)
        else:
            block["rr_measured"] = None
        out.append(block)
    return {
        "symbol": sym,
        "timeframe": tf,
        "mode": mode,
        "regime": regime_payload,
        "playbook_reasons": playbook_reasons,
        "candidates": out,
    }
