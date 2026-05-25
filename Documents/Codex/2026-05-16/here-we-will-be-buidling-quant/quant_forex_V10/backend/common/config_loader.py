from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


CONFIG_DIR = Path(__file__).resolve().parent / "config"


@lru_cache
def load_config(name: str) -> Any:
    with (CONFIG_DIR / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_thresholds() -> dict[str, Any]:
    return load_config("thresholds.json")


def load_regimes() -> list[dict[str, Any]]:
    return load_config("regimes.json")


def load_strategies() -> list[dict[str, Any]]:
    return load_config("strategies.json")


def load_modifiers() -> list[dict[str, Any]]:
    return load_config("modifiers.json")


def load_formulas() -> dict[str, str]:
    return load_config("formulas.json")


def load_market_defaults() -> dict[str, Any]:
    return load_config("market.json")
