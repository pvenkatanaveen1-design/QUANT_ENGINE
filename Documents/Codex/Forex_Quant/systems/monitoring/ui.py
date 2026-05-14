from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import ok
from systems.monitoring import backend


PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["monitoring"])


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/monitoring/templates/dashboard.html", {"status": backend.system_status()})


@router.get("/api/system/status")
def system_status() -> JSONResponse:
    return ok(backend.system_status(), "System status loaded.")


@router.get("/api/system/health")
def system_health() -> JSONResponse:
    return ok({"status": "ok", "live_trading": "disabled"}, "System health ok.")


@router.get("/api/system/kill-switch")
def kill_switch() -> JSONResponse:
    status = backend.system_status()
    return ok(
        {"manual_kill_switch": status["risk"]["manual_kill_switch"], "status": status["kill_switch_status"], "live_trading": "disabled"},
        "Kill switch status loaded.",
    )


@router.get("/partials/system-summary", response_class=HTMLResponse)
def system_summary(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/monitoring/partials/system_summary.html", {"status": backend.system_status()})


@router.get("/partials/system-grid", response_class=HTMLResponse)
def system_grid(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/monitoring/partials/system_grid.html", {"status": backend.system_status()})
