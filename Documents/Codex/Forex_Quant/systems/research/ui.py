from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi import Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import fail, ok
from systems.regime import backend as regime_backend
from systems.research import service

PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["research"])


@router.get("/backtester", response_class=HTMLResponse)
def backtester_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/research/templates/backtester.html", {"options": regime_backend.get_regime_options()})


@router.post("/api/backtests/run")
def run_backtest(
    symbol: str = Form("EURUSD"),
    timeframe: str = Form("M15"),
    selected_regime: str = Form("Q1_M01"),
    selected_strategy: str = Form("Q1_M01_S01"),
    investment_amount: float = Form(10000.0),
    bars: int = Form(672),
    source: str = Form("mt5_demo"),
    regime_scope: str = Form(""),
    killzone_enabled: bool = Form(False),
    breakout_enabled: bool = Form(False),
    sweep_enabled: bool = Form(False),
    alpha_enabled: bool = Form(False),
    spread_filter_enabled: bool = Form(False),
) -> JSONResponse:
    try:
        result = service.run_scenario(
            symbol=symbol,
            timeframe=timeframe,
            selected_regime=selected_regime,
            selected_strategy=selected_strategy,
            investment_amount=investment_amount,
            bars=bars,
            source=source,
            regime_scope=regime_scope or None,
            killzone_enabled=killzone_enabled,
            breakout_enabled=breakout_enabled,
            sweep_enabled=sweep_enabled,
            alpha_enabled=alpha_enabled,
            spread_filter_enabled=spread_filter_enabled,
        )
        return ok(result, "Scenario backtest complete." if not result.get("blocked") else "Scenario blocked.")
    except Exception as exc:
        return fail("Scenario backtest failed.", code="scenario_failed", detail=str(exc), status_code=400)


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


@router.post("/partials/scenario-result", response_class=HTMLResponse)
def scenario_result(
    request: Request,
    symbol: str = Form("EURUSD"),
    timeframe: str = Form("M15"),
    selected_regime: str = Form("Q1_M01"),
    selected_strategy: str = Form("Q1_M01_S01"),
    investment_amount: float = Form(10000.0),
    bars: int = Form(672),
    source: str = Form("mt5_demo"),
    regime_scope: str = Form(""),
    killzone_enabled: bool = Form(False),
    breakout_enabled: bool = Form(False),
    sweep_enabled: bool = Form(False),
    alpha_enabled: bool = Form(False),
    spread_filter_enabled: bool = Form(False),
) -> HTMLResponse:
    try:
        result = service.run_scenario(
            symbol=symbol,
            timeframe=timeframe,
            selected_regime=selected_regime,
            selected_strategy=selected_strategy,
            investment_amount=investment_amount,
            bars=bars,
            source=source,
            regime_scope=regime_scope or None,
            killzone_enabled=killzone_enabled,
            breakout_enabled=breakout_enabled,
            sweep_enabled=sweep_enabled,
            alpha_enabled=alpha_enabled,
            spread_filter_enabled=spread_filter_enabled,
        )
    except Exception as exc:
        result = {"blocked": True, "reason": str(exc), "label": "scenario estimate"}
    return templates.TemplateResponse(request, "systems/research/partials/scenario_result.html", {"result": result})
