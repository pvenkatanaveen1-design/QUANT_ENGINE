from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DANGEROUS_TRUE_KEYS = {"live_trading_enabled", "allow_live_trading", "allow_real_orders"}
CONFIG_FILES = {
    "app": PROJECT_ROOT / "config" / "app.yaml",
    "symbols": PROJECT_ROOT / "config" / "symbols.yaml",
    "sessions": PROJECT_ROOT / "config" / "sessions.yaml",
    "regimes": PROJECT_ROOT / "config" / "regimes.yaml",
    "risk": PROJECT_ROOT / "config" / "risk_rules.yaml",
    "funded": PROJECT_ROOT / "config" / "funded_rules.yaml",
    "data": PROJECT_ROOT / "config" / "data_sources.yaml",
    "strategy_registry": PROJECT_ROOT / "config" / "strategy_registry.yaml",
}


def list_files() -> list[dict[str, str]]:
    return [{"system": name, "path": str(path)} for name, path in CONFIG_FILES.items()]


def get_file(system: str) -> dict[str, Any]:
    path = CONFIG_FILES.get(system)
    if not path:
        raise KeyError(f"Unknown settings system: {system}")
    return {"system": system, "path": str(path), "content": path.read_text(encoding="utf-8")}


def _dangerous_true_paths(data: Any, prefix: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            dotted = f"{prefix}.{key}" if prefix else str(key)
            if key in DANGEROUS_TRUE_KEYS and value is True:
                hits.append(dotted)
            hits.extend(_dangerous_true_paths(value, dotted))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            hits.extend(_dangerous_true_paths(value, f"{prefix}[{index}]"))
    return hits


def validate_yaml_content(content: str) -> dict[str, Any]:
    parsed = yaml.safe_load(content) or {}
    dangerous = _dangerous_true_paths(parsed)
    if dangerous:
        raise ValueError(f"Dangerous live-trading fields cannot be set true from UI: {', '.join(dangerous)}")
    return parsed


def preview(system: str, content: str) -> dict[str, Any]:
    current = get_file(system)["content"]
    parsed = validate_yaml_content(content)
    return {
        "system": system,
        "valid": True,
        "changed": current != content,
        "top_level_keys": list(parsed.keys()) if isinstance(parsed, dict) else [],
        "message": "YAML is valid and dangerous live flags are blocked.",
    }


def save(system: str, content: str) -> dict[str, Any]:
    path = CONFIG_FILES.get(system)
    if not path:
        raise KeyError(f"Unknown settings system: {system}")
    validate_yaml_content(content)
    backup = path.with_suffix(path.suffix + f".bak-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup)
    path.write_text(content, encoding="utf-8")
    return {"system": system, "path": str(path), "backup": str(backup), "message": "Settings saved with backup."}

