from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import yaml


class ConfigError(RuntimeError):
    """Raised when configuration is missing or malformed."""


class ConfigManager:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or Path.cwd()).resolve()
        self._cache: dict[Path, dict[str, Any]] = {}

    def resolve(self, path: str | Path) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        return candidate.resolve()

    def load_yaml(self, path: str | Path, required_keys: Iterable[str] | None = None) -> dict[str, Any]:
        resolved = self.resolve(path)
        if not resolved.exists():
            raise ConfigError(f"Config file not found: {resolved}")
        if resolved in self._cache:
            data = self._cache[resolved]
        else:
            try:
                loaded = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as exc:
                raise ConfigError(f"Invalid YAML in {resolved}: {exc}") from exc
            if not isinstance(loaded, dict):
                raise ConfigError(f"Config must be a mapping: {resolved}")
            data = loaded
            self._cache[resolved] = data
        missing = [key for key in required_keys or [] if key not in data]
        if missing:
            raise ConfigError(f"Missing required keys in {resolved}: {', '.join(missing)}")
        return data

    def get(self, file_path: str | Path, dotted_path: str, default: Any = None, required: bool = False) -> Any:
        data: Any = self.load_yaml(file_path)
        for part in dotted_path.split("."):
            if isinstance(data, dict) and part in data:
                data = data[part]
            else:
                if required:
                    raise ConfigError(f"Missing config path '{dotted_path}' in {file_path}")
                return default
        return data

