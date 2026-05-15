from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi import Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import fail, ok
from systems.analysis import db as analysis_db
from systems.data.service import load_cleaned_rows
from systems.regime import backend as regime_backend
from systems.research import service

PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["research"])


@router.get("/backtester", response_class=HTMLResponse)
def backtester_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/research/templates/backtester.html", {"options": regime_backend.get_regime_options()})


@router.get("/research", response_class=HTMLResponse)
def research_page_alias(request: Request) -> HTMLResponse:
    """Section 17 — Backtester lives here and at /backtester."""
    return backtester_page(request)


@router.post("/api/backtests/signal-engine")
def run_signal_engine_backtest(
    symbol: str = Form("EURUSD"),
    timeframe: str = Form("M15"),
    regime_id_filter: str = Form("all"),
    min_bars_context: int = Form(100),
    initial_balance: float = Form(10_000.0),
) -> JSONResponse:
    try:
        rows = load_cleaned_rows(symbol.upper(), timeframe.upper())
        result = service.run_backtest(
            rows,
            symbol.upper(),
            timeframe.upper(),
            regime_id_filter=regime_id_filter,
            min_bars_context=int(min_bars_context),
            initial_balance=float(initial_balance),
            persist=True,
        )
        payload = asdict(result)
        return ok(payload, "Signal-engine walk-forward complete." if not result.error else result.error)
    except Exception as exc:
        return fail("Signal-engine backtest failed.", code="signal_engine_failed", detail=str(exc), status_code=400)


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


@router.post("/api/backtests/walk-forward")
def run_walk_forward(
    symbol: str = Form("EURUSD"),
    timeframe: str = Form("M15"),
    selected_regime: str = Form("Q3_M04"),
    selected_strategy: str = Form("Q3_M04_S01"),
    train_bars: int = Form(400),
    step_bars: int = Form(200),
    investment_amount: float = Form(10000.0),
    killzone_enabled: bool = Form(True),
    breakout_enabled: bool = Form(True),
    sweep_enabled: bool = Form(True),
    alpha_enabled: bool = Form(True),
    spread_filter_enabled: bool = Form(True),
) -> JSONResponse:
    try:
        result = service.run_walk_forward_backtest(
            symbol=symbol,
            timeframe=timeframe,
            selected_regime=selected_regime,
            selected_strategy=selected_strategy,
            train_bars=int(train_bars),
            step_bars=int(step_bars),
            investment_amount=investment_amount,
            killzone_enabled=killzone_enabled,
            breakout_enabled=breakout_enabled,
            sweep_enabled=sweep_enabled,
            alpha_enabled=alpha_enabled,
            spread_filter_enabled=spread_filter_enabled,
            save_result=False,
        )
        return ok(result, "Walk-forward pass complete." if not result.get("blocked") else "Walk-forward blocked.")
    except Exception as exc:
        return fail("Walk-forward failed.", code="walk_forward_failed", detail=str(exc), status_code=400)


@router.post("/api/backtests/batch")
def run_backtest_batch(
    symbol: str = Form("EURUSD"),
    timeframe: str = Form("M15"),
    selected_regime: str = Form(""),
    bars: int = Form(672),
    source: str = Form("mt5_demo"),
    max_strategies: int = Form(208),
    killzone_enabled: bool = Form(True),
    breakout_enabled: bool = Form(True),
    sweep_enabled: bool = Form(True),
    alpha_enabled: bool = Form(True),
    spread_filter_enabled: bool = Form(True),
) -> JSONResponse:
    try:
        result = service.run_batch_backtest(
            symbol=symbol,
            timeframe=timeframe,
            selected_regime=selected_regime or None,
            bars=bars,
            source=source,
            max_strategies=max_strategies,
            killzone_enabled=killzone_enabled,
            breakout_enabled=breakout_enabled,
            sweep_enabled=sweep_enabled,
            alpha_enabled=alpha_enabled,
            spread_filter_enabled=spread_filter_enabled,
        )
        return ok(result, "Batch backtest complete.")
    except Exception as exc:
        return fail("Batch backtest failed.", code="batch_backtest_failed", detail=str(exc), status_code=400)


@router.get("/api/backtests/results")
def backtest_results() -> JSONResponse:
    return ok({"results": analysis_db.list_backtest_runs()}, "Backtest results loaded.")


@router.get("/api/backtests/results/{result_id}")
def backtest_result(result_id: str) -> JSONResponse:
    rows = [item for item in analysis_db.list_backtest_runs(limit=500) if item["run_id"] == result_id]
    if not rows:
        return fail("Backtest result not found.", code="not_found", detail=result_id, status_code=404)
    return ok({"run": rows[0], "cache": analysis_db.get_analysis_cache(run_id=result_id)}, "Backtest result loaded.")


@router.get("/api/backtests/regime-matrix")
def regime_backtest_matrix(
    symbol: str = "EURUSD",
    selected_regime: str = "Q1_M01",
    timeframes: str = "M15,H1,H4,D1",
    lookback_months: int = 6,
    bars: int = 0,
    investment_amount: float = 10000.0,
    source: str = "mt5_demo",
    killzone_enabled: bool = True,
    breakout_enabled: bool = True,
    sweep_enabled: bool = True,
    alpha_enabled: bool = True,
    spread_filter_enabled: bool = True,
    force_refresh: bool = False,
) -> JSONResponse:
    try:
        result = service.run_regime_strategy_matrix(
            symbol=symbol,
            selected_regime=selected_regime,
            timeframes=timeframes,
            lookback_months=lookback_months,
            bars=bars,
            investment_amount=investment_amount,
            source=source,
            killzone_enabled=killzone_enabled,
            breakout_enabled=breakout_enabled,
            sweep_enabled=sweep_enabled,
            alpha_enabled=alpha_enabled,
            spread_filter_enabled=spread_filter_enabled,
            force_refresh=force_refresh,
        )
        return ok(result, "Regime strategy matrix loaded.")
    except Exception as exc:
        return fail("Regime strategy matrix failed.", code="regime_matrix_failed", detail=str(exc), status_code=400)


@router.get("/api/backtests/strategy-detail")
def strategy_backtest_detail(
    symbol: str = "EURUSD",
    selected_regime: str = "Q1_M01",
    selected_strategy: str = "Q1_M01_S01",
    timeframes: str = "M15,H1,H4,D1",
    lookback_months: int = 6,
    bars: int = 0,
    investment_amount: float = 10000.0,
    source: str = "mt5_demo",
    killzone_enabled: bool = True,
    breakout_enabled: bool = True,
    sweep_enabled: bool = True,
    alpha_enabled: bool = True,
    spread_filter_enabled: bool = True,
    force_refresh: bool = False,
) -> JSONResponse:
    try:
        result = service.run_strategy_detail_matrix(
            symbol=symbol,
            selected_regime=selected_regime,
            selected_strategy=selected_strategy,
            timeframes=timeframes,
            lookback_months=lookback_months,
            bars=bars,
            investment_amount=investment_amount,
            source=source,
            killzone_enabled=killzone_enabled,
            breakout_enabled=breakout_enabled,
            sweep_enabled=sweep_enabled,
            alpha_enabled=alpha_enabled,
            spread_filter_enabled=spread_filter_enabled,
            force_refresh=force_refresh,
        )
        return ok(result, "Strategy detail backtest loaded.")
    except Exception as exc:
        return fail("Strategy detail backtest failed.", code="strategy_detail_failed", detail=str(exc), status_code=400)


@router.get("/partials/backtest-status", response_class=HTMLResponse)
def backtest_status(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/research/partials/backtest_status.html")


@router.get("/partials/backtest-metrics", response_class=HTMLResponse)
def backtest_metrics(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/research/partials/backtest_metrics.html")


@router.get("/partials/regime-heatmap", response_class=HTMLResponse)
def regime_heatmap(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/research/partials/regime_heatmap.html")


@router.get("/partials/regime-backtest-matrix", response_class=HTMLResponse)
def regime_backtest_matrix_partial(
    request: Request,
    symbol: str = "EURUSD",
    selected_regime: str = "Q1_M01",
    timeframes: str = "M15,H1,H4,D1",
    lookback_months: int = 6,
    bars: int = 0,
    investment_amount: float = 10000.0,
    source: str = "mt5_demo",
    killzone_enabled: bool = True,
    breakout_enabled: bool = True,
    sweep_enabled: bool = True,
    alpha_enabled: bool = True,
    spread_filter_enabled: bool = True,
    force_refresh: bool = False,
) -> HTMLResponse:
    try:
        result = service.run_regime_strategy_matrix(
            symbol=symbol,
            selected_regime=selected_regime,
            timeframes=timeframes,
            lookback_months=lookback_months,
            bars=bars,
            investment_amount=investment_amount,
            source=source,
            killzone_enabled=killzone_enabled,
            breakout_enabled=breakout_enabled,
            sweep_enabled=sweep_enabled,
            alpha_enabled=alpha_enabled,
            spread_filter_enabled=spread_filter_enabled,
            force_refresh=force_refresh,
        )
    except Exception as exc:
        result = {"blocked": True, "reason": str(exc), "label": "regime_strategy_matrix"}
    return templates.TemplateResponse(request, "systems/research/partials/regime_backtest_matrix.html", {"result": result})


@router.get("/partials/strategy-backtest-detail", response_class=HTMLResponse)
def strategy_backtest_detail_partial(
    request: Request,
    symbol: str = "EURUSD",
    selected_regime: str = "Q1_M01",
    selected_strategy: str = "Q1_M01_S01",
    timeframes: str = "M15,H1,H4,D1",
    lookback_months: int = 6,
    bars: int = 0,
    investment_amount: float = 10000.0,
    source: str = "mt5_demo",
    killzone_enabled: bool = True,
    breakout_enabled: bool = True,
    sweep_enabled: bool = True,
    alpha_enabled: bool = True,
    spread_filter_enabled: bool = True,
    force_refresh: bool = False,
) -> HTMLResponse:
    try:
        result = service.run_strategy_detail_matrix(
            symbol=symbol,
            selected_regime=selected_regime,
            selected_strategy=selected_strategy,
            timeframes=timeframes,
            lookback_months=lookback_months,
            bars=bars,
            investment_amount=investment_amount,
            source=source,
            killzone_enabled=killzone_enabled,
            breakout_enabled=breakout_enabled,
            sweep_enabled=sweep_enabled,
            alpha_enabled=alpha_enabled,
            spread_filter_enabled=spread_filter_enabled,
            force_refresh=force_refresh,
        )
    except Exception as exc:
        result = {"blocked": True, "reason": str(exc), "label": "strategy_detail_matrix"}
    return templates.TemplateResponse(request, "systems/research/partials/strategy_backtest_detail.html", {"result": result})


@router.post("/research/partials/run-backtest", response_class=HTMLResponse)
def research_run_backtest_partial(
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
    """Section 17 alias — HTMX partial for a single scenario run."""
    return scenario_result(
        request,
        symbol=symbol,
        timeframe=timeframe,
        selected_regime=selected_regime,
        selected_strategy=selected_strategy,
        investment_amount=investment_amount,
        bars=bars,
        source=source,
        regime_scope=regime_scope,
        killzone_enabled=killzone_enabled,
        breakout_enabled=breakout_enabled,
        sweep_enabled=sweep_enabled,
        alpha_enabled=alpha_enabled,
        spread_filter_enabled=spread_filter_enabled,
    )


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
