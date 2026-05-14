from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SystemHeartbeat:
    name: str
    status: str
    last_heartbeat: str
    last_message: str
    page_url: str

