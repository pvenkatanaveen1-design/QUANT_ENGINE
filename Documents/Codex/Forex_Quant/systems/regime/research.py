from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config_manager import ConfigManager


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_research_config() -> dict[str, Any]:
    return ConfigManager(PROJECT_ROOT).load_yaml("config/regime_research.yaml")


def _mid(value: list[float] | tuple[float, float] | None) -> float:
    if not value:
        return 0.0
    if len(value) == 1:
        return float(value[0])
    return (float(value[0]) + float(value[1])) / 2.0


def _clamp_rate(value: float) -> float:
    return max(0.0, min(0.85, value))


def expected_value(win_rate: float, rrr: float) -> float:
    if win_rate <= 0 or rrr <= 0:
        return 0.0
    return round((win_rate * rrr) - ((1.0 - win_rate) * 1.0), 3)


def regime_model(regime_id: str) -> dict[str, Any]:
    cfg = load_research_config()
    base, _, modifier = regime_id.upper().partition("_")
    base_model = dict(cfg.get("base_models", {}).get(base, {}))
    modifier_model = dict(cfg.get("modifier_adjustments", {}).get(modifier, {}))
    override = dict(cfg.get("regime_overrides", {}).get(regime_id.upper(), {}))
    base_range = base_model.get("expected_win_rate", [0.0, 0.0])
    shifted = [
        _clamp_rate(float(base_range[0]) + float(modifier_model.get("win_rate_shift", 0.0))),
        _clamp_rate(float(base_range[1]) + float(modifier_model.get("win_rate_shift", 0.0))),
    ]
    win_range = override.get("expected_win_rate", shifted)
    rrr = float(override.get("expected_rrr", float(base_model.get("expected_rrr", 0.0)) + float(modifier_model.get("rrr_shift", 0.0))))
    risk_multiplier = float(base_model.get("risk_multiplier", 0.0)) * float(modifier_model.get("risk_multiplier", 1.0))
    if base == "Q4":
        risk_multiplier = 0.0
    win_mid = _mid(win_range)
    return {
        "regime_id": regime_id.upper(),
        "base": base,
        "modifier": modifier,
        "priority": override.get("priority", "normal" if base != "Q4" else "defensive"),
        "focus": override.get("focus") or modifier_model.get("trap_focus") or base_model.get("thesis"),
        "expected_win_rate": [round(float(win_range[0]) * 100, 2), round(float(win_range[1]) * 100, 2)] if win_range else [0.0, 0.0],
        "expected_win_rate_mid": round(win_mid * 100, 2),
        "expected_rrr": round(max(0.0, rrr), 2),
        "expected_ev_r": expected_value(win_mid, max(0.0, rrr)),
        "risk_multiplier": round(max(0.0, risk_multiplier), 3),
        "evidence": sorted(set(base_model.get("evidence", []) + override.get("evidence", []))),
        "sources": base_model.get("sources", []) + override.get("sources", []),
        "thesis": base_model.get("thesis"),
        "trap_focus": modifier_model.get("trap_focus"),
    }


def strategy_family_spec(family: str) -> dict[str, Any]:
    cfg = load_research_config()
    if family == "liquidity":
        family = "sweep_reversal"
    if family in {"news", "macro_correlation"}:
        family = "general"
    return dict(cfg.get("strategy_family_specs", {}).get(family, cfg.get("strategy_family_specs", {}).get("general", {})))


def enrich_strategy(strategy: dict[str, Any], selected_regime_id: str) -> dict[str, Any]:
    item = dict(strategy)
    family = str(item.get("family", "general"))
    spec = strategy_family_spec(family)
    regime = regime_model(selected_regime_id)
    family_mid = _mid(spec.get("expected_win_rate", [0.0, 0.0]))
    regime_mid = float(regime.get("expected_win_rate_mid", 0.0)) / 100.0
    blended_mid = _clamp_rate((family_mid + regime_mid) / 2.0 if regime_mid else family_mid)
    rrr = max(float(spec.get("expected_rrr", 0.0)), float(regime.get("expected_rrr", 0.0)))
    if family == "defensive" or str(selected_regime_id).startswith("Q4"):
        blended_mid = 0.0
        rrr = 0.0
    item["research_spec"] = {
        "scenario_executable": bool(spec.get("executable", False)),
        "expected_win_rate_mid": round(blended_mid * 100, 2),
        "expected_rrr": round(rrr, 2),
        "expected_ev_r": expected_value(blended_mid, rrr),
        "entry_logic": spec.get("entry_logic"),
        "invalid_when": spec.get("invalid_when"),
        "evidence": spec.get("evidence", []),
        "sources": spec.get("sources", []),
        "regime_priority": regime.get("priority"),
    }
    return item


def enrich_playbook(playbook: dict[str, Any], selected_regime_id: str) -> dict[str, Any]:
    out = dict(playbook)
    out["research_model"] = regime_model(selected_regime_id)
    out["candidates"] = [enrich_strategy(item, selected_regime_id) for item in playbook.get("candidates", [])]
    return out


def source_details(keys: list[str]) -> list[dict[str, Any]]:
    cfg = load_research_config()
    sources = cfg.get("sources", {})
    return [{**{"key": key}, **dict(sources.get(key, {}))} for key in keys]


def news_sentiment_status() -> dict[str, Any]:
    return dict(load_research_config().get("news_and_sentiment", {}))
