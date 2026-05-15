from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo


def parse_timestamp(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    raise ValueError(f"Unsupported timestamp: {value!r}")


def to_utc(value: str | datetime, source_tz: str = "UTC") -> datetime:
    dt = parse_timestamp(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(source_tz))
    return dt.astimezone(timezone.utc)


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def time_in_window(moment: datetime, start_hhmm: str, end_hhmm: str) -> bool:
    current = moment.timetz().replace(tzinfo=None)
    start = parse_hhmm(start_hhmm)
    end = parse_hhmm(end_hhmm)
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def classify_session(moment: str | datetime, sessions_config: dict) -> dict:
    tz_name = sessions_config.get("timezone", "UTC")
    dt = to_utc(moment)
    if tz_name != "UTC":
        dt = dt.astimezone(ZoneInfo(tz_name))
    for session in sessions_config.get("sessions", []):
        if time_in_window(dt, session["start"], session["end"]):
            return {
                "session": session.get("id"),
                "modifier": session.get("modifier"),
                "notes": session.get("notes"),
                "kill_zone_active": bool(session.get("kill_zone", False)),
            }
    return {
        "session": "Unclassified",
        "modifier": "M01",
        "notes": None,
        "kill_zone_active": False,
    }

