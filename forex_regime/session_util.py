"""UTC session bucket for strategy scoring and risk gate (coarse)."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_session_label(now: datetime | None = None) -> str:
    """
    LONDON ≈ 08–13 UTC, OVERLAP ≈ 13–17, NEW_YORK ≈ 17–22, ASIA ≈ 22–08, else OFF.
    Approximation only; adjust to broker/server time if needed.
    """
    dt = now or datetime.now(timezone.utc)
    h = dt.astimezone(timezone.utc).hour
    if 8 <= h < 13:
        return "LONDON"
    if 13 <= h < 17:
        return "OVERLAP"
    if 17 <= h < 22:
        return "NEW_YORK"
    if h >= 22 or h < 8:
        return "ASIA"
    return "OFF"
