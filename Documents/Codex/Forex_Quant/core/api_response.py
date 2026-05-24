from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi.responses import JSONResponse


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def envelope(
    ok: bool,
    data: Any = None,
    message: str = "",
    warnings: list[Any] | None = None,
    errors: list[Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "data": data,
        "message": message,
        "warnings": warnings or [],
        "errors": errors or [],
        "timestamp": timestamp(),
    }


def ok(data: Any = None, message: str = "ok", warnings: list[Any] | None = None, status_code: int = 200) -> JSONResponse:
    return JSONResponse(envelope(True, data=data, message=message, warnings=warnings), status_code=status_code)


def fail(message: str, code: str = "error", detail: str | None = None, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        envelope(False, data=None, message=message, errors=[{"code": code, "detail": detail or message}]),
        status_code=status_code,
    )

