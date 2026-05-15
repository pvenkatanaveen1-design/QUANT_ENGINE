from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config_manager import ConfigManager

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CODE = "S08_no_trade"


def _routing_cfg() -> dict[str, Any]:
    return ConfigManager(PROJECT_ROOT).load_yaml("config/signal_routing.yaml")


def signal_code_for_regime(regime_id: str) -> str:
    rid = str(regime_id).upper()
    table = _routing_cfg().get("signal_routing") or {}
    return str(table.get(rid) or DEFAULT_CODE)


def position_size_multiplier_for_regime(regime_id: str) -> float:
    """Combined quadrant size × per-regime override (Q4 → 0)."""
    rid = str(regime_id).upper()
    cfg = _routing_cfg()
    base_key = rid[:2] if len(rid) >= 2 else "Q4"
    base = float((cfg.get("size_multipliers") or {}).get(base_key, 0.0))
    overrides = cfg.get("size_overrides") or {}
    if rid in overrides:
        return float(overrides[rid])
    return base


def routing_settings() -> dict[str, Any]:
    return dict(_routing_cfg().get("settings") or {})
