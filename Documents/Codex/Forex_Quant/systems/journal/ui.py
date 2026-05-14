from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import fail, ok

PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["journal"])


@router.get("/decisions", response_class=HTMLResponse)
def decisions_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/journal/templates/decisions.html", {"decisions": []})


@router.get("/api/decisions")
def decisions() -> JSONResponse:
    return ok({"decisions": []}, "No decisions recorded yet.")


@router.get("/api/decisions/{decision_id}")
def decision_detail(decision_id: str) -> JSONResponse:
    return fail("Decision not found.", code="not_found", detail=decision_id, status_code=404)


@router.post("/api/decisions/paper-run-one")
def paper_run_one() -> JSONResponse:
    return fail("Paper execution is not implemented in this safe build.", code="not_built", status_code=409)


@router.get("/partials/decision-log", response_class=HTMLResponse)
def decision_log(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/journal/partials/decision_log.html", {"decisions": []})


@router.get("/partials/decision-detail", response_class=HTMLResponse)
def decision_detail_partial(request: Request, decision_id: str = "") -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/journal/partials/decision_detail.html", {"decision_id": decision_id})
