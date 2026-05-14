from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import fail, ok

PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["research"])


@router.get("/backtester", response_class=HTMLResponse)
def backtester_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/research/templates/backtester.html")


@router.post("/api/backtests/run")
def run_backtest() -> JSONResponse:
    return fail("Backtester engine is the next build phase; no trade simulation runs yet.", code="not_built", status_code=409)


@router.get("/api/backtests/results")
def backtest_results() -> JSONResponse:
    return ok({"results": []}, "No backtest results yet.")


@router.get("/api/backtests/results/{result_id}")
def backtest_result(result_id: str) -> JSONResponse:
    return fail("Backtest result not found.", code="not_found", detail=result_id, status_code=404)


@router.get("/partials/backtest-status", response_class=HTMLResponse)
def backtest_status(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/research/partials/backtest_status.html")


@router.get("/partials/backtest-metrics", response_class=HTMLResponse)
def backtest_metrics(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/research/partials/backtest_metrics.html")


@router.get("/partials/regime-heatmap", response_class=HTMLResponse)
def regime_heatmap(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/research/partials/regime_heatmap.html")
