from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import fail, ok
from systems.journal import service

PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["journal"])


@router.get("/decisions", response_class=HTMLResponse)
def decisions_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/journal/templates/decisions.html", {"decisions": service.list_journal()})


@router.get("/journal", response_class=HTMLResponse)
def journal_page_alias(request: Request) -> HTMLResponse:
    """Section 17 — decision log (same as /decisions)."""
    return decisions_page(request)


@router.get("/api/decisions")
def decisions() -> JSONResponse:
    return ok({"decisions": service.list_journal()}, "Decision journal loaded.")


@router.get("/api/decisions/{decision_id}")
def decision_detail(decision_id: str) -> JSONResponse:
    return fail("Decision not found.", code="not_found", detail=decision_id, status_code=404)


@router.post("/api/decisions/paper-run-one")
def paper_run_one() -> JSONResponse:
    return fail("Paper execution is not implemented in this safe build.", code="not_built", status_code=409)


@router.get("/api/journal/history")
def journal_history(limit: int = 200, action: str = "all") -> JSONResponse:
    return ok(
        {"entries": service.load_history(limit=limit, action_filter=action)},
        "Journal history loaded.",
    )


@router.get("/partials/decision-log", response_class=HTMLResponse)
def decision_log(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/journal/partials/decision_log.html", {"decisions": service.list_journal()})


@router.get("/partials/decision-detail", response_class=HTMLResponse)
def decision_detail_partial(request: Request, decision_id: str = "") -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/journal/partials/decision_detail.html", {"decision_id": decision_id})
