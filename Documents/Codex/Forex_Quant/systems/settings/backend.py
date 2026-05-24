from __future__ import annotations

from systems.settings import service


def list_settings_files() -> list[dict[str, str]]:
    return service.list_files()


def get_settings(system: str) -> dict:
    return service.get_file(system)


def preview_settings(system: str, content: str) -> dict:
    return service.preview(system, content)


def save_settings(system: str, content: str) -> dict:
    return service.save(system, content)

