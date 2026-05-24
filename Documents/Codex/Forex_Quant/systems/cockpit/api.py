from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import fail, ok
from systems.cockpit import db, regime_map, service


PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["cockpit"])


def _template_context(request: Request, symbol: str = "EURUSD", timeframe: str = "M15") -> dict:
    symbol = symbol.upper()
    timeframe = timeframe.upper()
    mapping = regime_map.full_regime_strategy_map()
    strategies = [strategy for regime in mapping["regimes"] for strategy in regime["strategies"]]
    state = {
        "symbol": symbol,
        "timeframe": timeframe,
        "map": mapping,
        "current": {"symbol": symbol, "timeframe": timeframe, "current_regime": None},
        "rankings": db.rankings(limit=25),
        "recent_runs": db.list_runs(limit=25),
        "api_links": service.api_links(symbol, timeframe),
    }
    return {
        "request": request,
        "state": state,
        "symbols": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "XAUUSD"],
        "timeframes": ["M5", "M15", "M30", "H1", "H4", "D1"],
        "regimes": mapping["regimes"],
        "strategies": strategies,
    }


@router.get("/cockpit", response_class=HTMLResponse)
def cockpit_page(request: Request, symbol: str = "EURUSD", timeframe: str = "M15") -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/cockpit/templates/cockpit.html", _template_context(request, symbol, timeframe))


@router.get("/cockpit/api/live-state")
def cockpit_prefixed_live_state(symbol: str = "EURUSD", timeframe: str = "M15", capital: float = 10000.0) -> JSONResponse:
    """Returns live regime + 4 strategies + market values as raw JSON."""
    return JSONResponse(content=service.get_live_cockpit_state(symbol, timeframe, capital))


@router.get("/cockpit/api/ranking")
def cockpit_prefixed_ranking(symbol: str = "EURUSD", timeframe: str = "M15") -> JSONResponse:
    """Returns all 52 regimes sorted by net profit, then expected EV for untested regimes."""
    return JSONResponse(content=service.get_regime_ranking(symbol, timeframe))


@router.get("/cockpit/api/strategy-detail/{regime_id}")
def cockpit_prefixed_strategy_detail(regime_id: str, symbol: str = "EURUSD", timeframe: str = "M15") -> JSONResponse:
    """Returns four-slot backtest detail for an expanded regime row."""
    return JSONResponse(content=service.get_strategy_backtest_detail(regime_id, symbol, timeframe))


@router.post("/cockpit/api/run-backtest/{regime_id}")
def cockpit_prefixed_run_backtest(
    regime_id: str,
    symbol: str = Form("EURUSD"),
    timeframe: str = Form("M15"),
    capital: float = Form(10000.0),
    risk_pct: float = Form(1.0),
) -> JSONResponse:
    """Triggers MT5-backed backtest for all four strategy slots of a regime."""
    return JSONResponse(content=service.run_regime_backtest(regime_id, symbol, timeframe, capital, risk_pct))


@router.get("/cockpit/api/playbook-json")
def cockpit_prefixed_playbook_json(symbol: str = "EURUSD", timeframe: str = "M15", capital: float = 10000.0) -> JSONResponse:
    """Returns complete copyable JSON playbook for the current regime."""
    return JSONResponse(content=service.build_playbook_json(symbol, timeframe, capital))


@router.get("/cockpit/api/trade-list/{run_id}")
def cockpit_prefixed_trade_list(run_id: str) -> JSONResponse:
    """Returns all simulated trades for a stored cockpit backtest run."""
    with db.get_conn() as conn:
        trades = conn.execute("SELECT * FROM trade_log WHERE run_id = ? ORDER BY trade_number", (run_id,)).fetchall()
        payload = [{key: row[key] for key in row.keys()} for row in trades]
    return JSONResponse(content=payload)


@router.get("/api/cockpit/state")
def cockpit_state(symbol: str = "EURUSD", timeframe: str = "M15") -> JSONResponse:
    try:
        return ok(service.initial_state(symbol, timeframe), "Cockpit state loaded.")
    except Exception as exc:
        return fail("Could not load cockpit state.", code="cockpit_state_failed", detail=str(exc), status_code=400)


@router.get("/api/cockpit/map")
def cockpit_map() -> JSONResponse:
    try:
        return ok(regime_map.full_regime_strategy_map(), "52 regime x 4 strategy map loaded.")
    except Exception as exc:
        return fail("Could not load cockpit map.", code="cockpit_map_failed", detail=str(exc), status_code=400)


@router.get("/api/cockpit/rankings")
def cockpit_rankings(symbol: str = "EURUSD", timeframe: str = "M15", limit: int = 52) -> JSONResponse:
    return ok(
        {
            "regime_ranking": service.get_regime_ranking(symbol, timeframe)[:limit],
            "stored_strategy_rankings": db.rankings(limit=limit),
            "recent_runs": db.list_runs(limit=limit),
        },
        "Cockpit rankings loaded.",
    )


@router.get("/api/cockpit/live-state")
def cockpit_live_state(symbol: str = "EURUSD", timeframe: str = "M15", capital: float = 10000.0) -> JSONResponse:
    try:
        return ok(service.get_live_cockpit_state(symbol, timeframe, capital), "Live cockpit state loaded.")
    except Exception as exc:
        return fail("Could not load live cockpit state.", code="cockpit_live_failed", detail=str(exc), status_code=400)


@router.get("/api/cockpit/regimes/{regime_id}/strategies")
def cockpit_strategy_detail(regime_id: str, symbol: str = "EURUSD", timeframe: str = "M15") -> JSONResponse:
    try:
        return ok(service.get_strategy_backtest_detail(regime_id, symbol, timeframe), "Strategy backtest detail loaded.")
    except Exception as exc:
        return fail("Could not load strategy detail.", code="cockpit_strategy_detail_failed", detail=str(exc), status_code=400)


@router.get("/api/cockpit/runs/{run_id}")
def cockpit_run_detail(run_id: str) -> JSONResponse:
    detail = db.get_run_detail(run_id)
    if not detail:
        return fail("Cockpit run not found.", code="not_found", detail=run_id, status_code=404)
    return ok(detail, "Cockpit run detail loaded.")


@router.get("/api/cockpit/export/live-playbook")
def export_live_playbook(symbol: str = "EURUSD", timeframe: str = "M15", capital: float = 10000.0) -> JSONResponse:
    try:
        return ok(service.build_playbook_json(symbol, timeframe, capital), "Live regime playbook exported.")
    except Exception as exc:
        return fail("Could not export live playbook.", code="live_playbook_failed", detail=str(exc), status_code=400)


@router.post("/api/cockpit/backtest/strategy")
def api_run_strategy(
    symbol: str = Form("EURUSD"),
    selected_regime: str = Form("Q1_M01"),
    selected_strategy: str = Form("Q1_M01_S01"),
    timeframes: str = Form("M15,H1,H4,D1"),
    lookback_months: int = Form(6),
    bars: int = Form(0),
    investment_amount: float = Form(10000.0),
    source: str = Form("mt5_demo"),
    killzone_enabled: bool = Form(True),
    breakout_enabled: bool = Form(True),
    sweep_enabled: bool = Form(True),
    alpha_enabled: bool = Form(True),
    spread_filter_enabled: bool = Form(True),
    force_refresh: bool = Form(False),
) -> JSONResponse:
    try:
        payload = service.run_strategy_backtest(
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
        return ok(payload, "Strategy backtest complete.")
    except Exception as exc:
        return fail("Strategy backtest failed.", code="cockpit_strategy_failed", detail=str(exc), status_code=400)


@router.post("/api/cockpit/backtest/regime")
def api_run_regime(
    symbol: str = Form("EURUSD"),
    selected_regime: str = Form("Q1_M01"),
    timeframes: str = Form("M15,H1,H4,D1"),
    lookback_months: int = Form(6),
    bars: int = Form(0),
    investment_amount: float = Form(10000.0),
    source: str = Form("mt5_demo"),
    killzone_enabled: bool = Form(True),
    breakout_enabled: bool = Form(True),
    sweep_enabled: bool = Form(True),
    alpha_enabled: bool = Form(True),
    spread_filter_enabled: bool = Form(True),
    force_refresh: bool = Form(False),
) -> JSONResponse:
    try:
        payload = service.run_regime_backtests(
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
        return ok(payload, "Regime matrix backtest complete.")
    except Exception as exc:
        return fail("Regime matrix backtest failed.", code="cockpit_regime_failed", detail=str(exc), status_code=400)


@router.post("/api/cockpit/backtest/full")
def api_run_full(
    symbol: str = Form("EURUSD"),
    timeframe: str = Form("M15"),
    bars: int = Form(0),
    max_strategies: int = Form(208),
    source: str = Form("mt5_demo"),
    killzone_enabled: bool = Form(True),
    breakout_enabled: bool = Form(True),
    sweep_enabled: bool = Form(True),
    alpha_enabled: bool = Form(True),
    spread_filter_enabled: bool = Form(True),
) -> JSONResponse:
    try:
        payload = service.run_full_backtests(
            symbol=symbol,
            timeframe=timeframe,
            bars=bars,
            max_strategies=max_strategies,
            source=source,
            killzone_enabled=killzone_enabled,
            breakout_enabled=breakout_enabled,
            sweep_enabled=sweep_enabled,
            alpha_enabled=alpha_enabled,
            spread_filter_enabled=spread_filter_enabled,
        )
        return ok(payload, "Full 208-slot backtest complete.")
    except Exception as exc:
        return fail("Full cockpit backtest failed.", code="cockpit_full_failed", detail=str(exc), status_code=400)


@router.get("/partials/cockpit/overview", response_class=HTMLResponse)
def cockpit_overview(request: Request, symbol: str = "EURUSD", timeframe: str = "M15") -> HTMLResponse:
    try:
        payload = service.initial_state(symbol, timeframe)
    except Exception as exc:
        payload = {"error": str(exc), "symbol": symbol.upper(), "timeframe": timeframe.upper()}
    return templates.TemplateResponse(request, "systems/cockpit/templates/partials/overview.html", {"state": payload})


@router.get("/partials/cockpit/rankings", response_class=HTMLResponse)
def cockpit_rankings_partial(request: Request, limit: int = 25) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "systems/cockpit/templates/partials/rankings.html",
        {"rankings": db.rankings(limit=limit), "recent_runs": db.list_runs(limit=limit)},
    )


@router.post("/partials/cockpit/run-strategy", response_class=HTMLResponse)
def run_strategy_partial(
    request: Request,
    symbol: str = Form("EURUSD"),
    selected_regime: str = Form("Q1_M01"),
    selected_strategy: str = Form("Q1_M01_S01"),
    timeframes: str = Form("M15,H1,H4,D1"),
    lookback_months: int = Form(6),
    bars: int = Form(0),
    investment_amount: float = Form(10000.0),
    source: str = Form("mt5_demo"),
    killzone_enabled: bool = Form(False),
    breakout_enabled: bool = Form(False),
    sweep_enabled: bool = Form(False),
    alpha_enabled: bool = Form(False),
    spread_filter_enabled: bool = Form(False),
    force_refresh: bool = Form(False),
) -> HTMLResponse:
    try:
        payload = service.run_strategy_backtest(
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
        payload = {"blocked": True, "reason": str(exc), "label": "cockpit_strategy_backtest"}
    return templates.TemplateResponse(request, "systems/cockpit/templates/partials/result.html", {"result": payload})


@router.post("/partials/cockpit/run-regime", response_class=HTMLResponse)
def run_regime_partial(
    request: Request,
    symbol: str = Form("EURUSD"),
    selected_regime: str = Form("Q1_M01"),
    timeframes: str = Form("M15,H1,H4,D1"),
    lookback_months: int = Form(6),
    bars: int = Form(0),
    investment_amount: float = Form(10000.0),
    source: str = Form("mt5_demo"),
    killzone_enabled: bool = Form(False),
    breakout_enabled: bool = Form(False),
    sweep_enabled: bool = Form(False),
    alpha_enabled: bool = Form(False),
    spread_filter_enabled: bool = Form(False),
    force_refresh: bool = Form(False),
) -> HTMLResponse:
    try:
        payload = service.run_regime_backtests(
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
        payload = {"blocked": True, "reason": str(exc), "label": "cockpit_regime_matrix"}
    return templates.TemplateResponse(request, "systems/cockpit/templates/partials/result.html", {"result": payload})
