from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import fail, ok
from systems.settings import backend


PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["settings"])


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, system: str = "app") -> HTMLResponse:
    try:
        selected = backend.get_settings(system)
    except Exception:
        selected = backend.get_settings("app")
    return templates.TemplateResponse(
        request,
        "systems/settings/templates/settings.html",
        {"files": backend.list_settings_files(), "selected": selected},
    )


@router.get("/api/settings/files")
def settings_files() -> JSONResponse:
    return ok({"files": backend.list_settings_files()}, "Settings files loaded.")


@router.get("/api/settings/{system}")
def settings_get(system: str) -> JSONResponse:
    try:
        return ok(backend.get_settings(system), "Settings file loaded.")
    except Exception as exc:
        return fail("Settings file not found.", code="not_found", detail=str(exc), status_code=404)


@router.post("/api/settings/{system}/preview")
def settings_preview(system: str, content: str = Form("")) -> JSONResponse:
    try:
        return ok(backend.preview_settings(system, content), "Settings preview valid.")
    except Exception as exc:
        return fail("Settings preview failed.", code="settings_preview_failed", detail=str(exc), status_code=400)


@router.post("/api/settings/{system}/save")
def settings_save(system: str, content: str = Form("")) -> JSONResponse:
    try:
        return ok(backend.save_settings(system, content), "Settings saved with backup.")
    except Exception as exc:
        return fail("Settings save failed.", code="settings_save_failed", detail=str(exc), status_code=400)


@router.get("/partials/settings-editor", response_class=HTMLResponse)
def settings_editor(request: Request, system: str = "app") -> HTMLResponse:
    try:
        selected = backend.get_settings(system)
    except Exception as exc:
        selected = {"system": system, "path": "", "content": f"# {exc}"}
    return templates.TemplateResponse(request, "systems/settings/partials/settings_editor.html", {"selected": selected})
