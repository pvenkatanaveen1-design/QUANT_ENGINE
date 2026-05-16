"""Canonical list of regime IDs (52 = base_regimes × modifiers from config/regimes.yaml)."""

from __future__ import annotations

from pathlib import Path

from core.config_manager import ConfigManager

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _regime_ids_from_yaml() -> list[str]:
    cfg = ConfigManager(_PROJECT_ROOT).load_yaml("config/regimes.yaml")
    return [
        f"{base}_{modifier}"
        for base in cfg.get("base_regimes", {})
        for modifier in cfg.get("modifiers", {})
    ]


regimes: list[str] = _regime_ids_from_yaml()
