from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import fail, ok
from systems.strategy_router import backend, service


PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["strategy-router"])


@router.get("/strategy-gate", response_class=HTMLResponse)
def strategy_enablement_gate_page(request: Request) -> HTMLResponse:
    """Section 19 — documented gates before status or enabled flags change."""
    return templates.TemplateResponse(request, "systems/strategy_router/templates/enablement_gate.html", {})


@router.get("/priority-setups", response_class=HTMLResponse)
def priority_setups_page(request: Request) -> HTMLResponse:
    """Section 23 — ordered list of setups to validate first."""
    return templates.TemplateResponse(request, "systems/strategy_router/templates/priority_setups.html", {})


@router.get("/strategies", response_class=HTMLResponse)
def strategies_page(request: Request, regime_id: str = "Q1_M01") -> HTMLResponse:
    rid = regime_id.strip().upper() or "Q1_M01"
    registry = backend.get_registry()
    selected = backend.get_by_regime(rid)
    summary = backend.get_registry_summary()
    return templates.TemplateResponse(
        request,
        "systems/strategy_router/templates/strategies.html",
        {"registry": registry, "selected": selected, "summary": summary},
    )


@router.get("/api/strategies")
def strategies_api() -> JSONResponse:
    return ok({"strategies": backend.get_registry(), "summary": backend.get_registry_summary()}, "Strategy registry loaded.")


@router.get("/api/strategies/by-regime/{regime_id}")
def strategies_by_regime(regime_id: str, mode: str = "research") -> JSONResponse:
    return ok(backend.get_by_regime(regime_id.upper(), mode=mode), "Regime playbook loaded.")


@router.get("/api/strategies/playbook/{regime_id}")
def strategies_playbook_alias(regime_id: str, mode: str = "research") -> JSONResponse:
    """Section 17 alias — same payload as GET /api/strategies/by-regime/{regime_id}."""
    return strategies_by_regime(regime_id, mode=mode)


@router.post("/api/strategies/run-signal")
def run_strategy_signal_api(
    symbol: str = Form("EURUSD"),
    timeframe: str = Form("M15"),
    mode: str = Form("research"),
) -> JSONResponse:
    try:
        payload = service.run_strategy_signals(symbol, timeframe, mode=mode)
        return ok(payload, "Strategy signals evaluated on latest cleaned bars.")
    except FileNotFoundError as exc:
        return fail("No cleaned data for symbol/timeframe.", code="missing_data", detail=str(exc), status_code=404)
    except Exception as exc:
        return fail("Signal run failed.", code="signal_run_failed", detail=str(exc), status_code=400)


@router.get("/api/strategies/{strategy_id}")
def strategy_detail(strategy_id: str) -> JSONResponse:
    matches = [item for item in backend.get_registry() if item["id"] == strategy_id]
    if matches:
        return ok(matches[0], "Strategy loaded.")
    return fail("Strategy not found.", code="not_found", detail=strategy_id, status_code=404)


@router.get("/partials/strategy-table", response_class=HTMLResponse)
def strategy_table(request: Request, regime_id: str = "Q1_M01") -> HTMLResponse:
    selected = backend.get_by_regime(regime_id.upper())
    return templates.TemplateResponse(request, "systems/strategy_router/partials/strategy_table.html", {"selected": selected})


@router.get("/partials/regime-playbook", response_class=HTMLResponse)
def regime_playbook(request: Request, regime_id: str = "Q1_M01") -> HTMLResponse:
    selected = backend.get_by_regime(regime_id.upper())
    return templates.TemplateResponse(request, "systems/strategy_router/partials/regime_playbook.html", {"selected": selected})


@router.post("/api/strategies/{strategy_id}/research-enable")
def research_enable(strategy_id: str) -> JSONResponse:
    return ok(backend.research_enable_preview(strategy_id), "Research enable preview loaded.")


@router.post("/api/strategies/{strategy_id}/approval-preview")
def approval_preview(strategy_id: str, regime_id: str | None = None) -> JSONResponse:
    return ok(backend.approval_preview(strategy_id, regime_id=regime_id.upper() if regime_id else None), "Strategy approval preview recorded.")
