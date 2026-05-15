from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import fail, ok, timestamp
from systems.data import backend
from systems.mt5_gateway import service as mt5_service


PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["data"])


@router.get("/data", response_class=HTMLResponse)
def data_page(request: Request) -> HTMLResponse:
    options = backend.get_market_options()
    return templates.TemplateResponse(
        request,
        "systems/data/templates/data.html",
        {"status": backend.get_dataset_status(), "config": backend.get_data_config(), "options": options},
    )


@router.get("/api/data/status")
def data_status() -> JSONResponse:
    return ok(backend.get_dataset_status(), "Data status loaded.")


@router.get("/api/data/options")
def data_options() -> JSONResponse:
    return ok(backend.get_market_options(), "Data options loaded.")


@router.post("/api/data/fetch")
def fetch_data(
    source: str = Form("mt5_demo"),
    symbol: str = Form(""),
    timeframe: str = Form("M15"),
    bars: int = Form(672),
    input_path: str = Form(""),
) -> JSONResponse:
    try:
        if source != "mt5_demo":
            return fail("Only MT5 data is supported in the runtime app.", code="mt5_only", detail="Offline fallback is disabled.", status_code=400)
        result = backend.fetch_mt5_bars(symbol.upper(), timeframe.upper(), bars=bars)
        message = "MT5 bars fetched, cleaned, and saved."
        return ok(
            {
                "symbol": result.symbol,
                "timeframe": result.timeframe,
                "source": source,
                "quality_status": result.quality_status,
                "rows_in": result.rows_in,
                "rows_out": result.rows_out,
                "cleaned_path": result.cleaned_path,
                "report_path": result.report_path,
                "issues": [issue.__dict__ for issue in result.issues],
                "metadata": result.metadata,
            },
            message,
        )
    except FileNotFoundError as exc:
        return fail("Could not load data.", code="missing_file", detail=str(exc), status_code=404)
    except Exception as exc:
        status_code = exc.status_code if hasattr(exc, "status_code") else 400
        code = exc.code if hasattr(exc, "code") else "data_load_failed"
        return fail("Could not load data.", code=code, detail=str(exc), status_code=status_code)


@router.post("/api/data/load-csv")
def load_csv(symbol: str = Form("EURUSD"), timeframe: str = Form("M15"), input_path: str = Form("")) -> JSONResponse:
    return fail("CSV loading is disabled in the runtime app.", code="mt5_only", detail="Use /api/data/fetch with source=mt5_demo.", status_code=410)


@router.get("/api/data/quality/{symbol}/{timeframe}")
def data_quality_api(symbol: str, timeframe: str) -> JSONResponse:
    report = backend.get_quality_report(symbol.upper(), timeframe.upper())
    if report.get("status") == "missing":
        return fail(
            f"Could not load cleaned {symbol.upper()} {timeframe.upper()} data.",
            code="missing_file",
            detail=f"data/cleaned/{symbol.upper()}_{timeframe.upper()}_quality.json not found",
            status_code=404,
        )
    return ok(report, "Quality report loaded.")


@router.get("/partials/data-files", response_class=HTMLResponse)
def data_files_partial(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "systems/data/partials/data_files.html",
        {"status": backend.get_dataset_status()},
    )


@router.post("/partials/data-load-result", response_class=HTMLResponse)
def data_load_result_partial(
    request: Request,
    source: str = Form("mt5_demo"),
    symbol: str = Form(""),
    timeframe: str = Form("M15"),
    bars: int = Form(672),
    input_path: str = Form(""),
) -> HTMLResponse:
    try:
        if source != "mt5_demo":
            raise ValueError("Only MT5 data is supported in the runtime app. Offline fallback is disabled.")
        result = backend.fetch_mt5_bars(symbol.upper(), timeframe.upper(), bars=bars)
        message = "MT5 bars fetched, cleaned, and saved."
        payload = {
            "ok": True,
            "message": message,
            "symbol": result.symbol,
            "timeframe": result.timeframe,
            "source": source,
            "quality_status": result.quality_status,
            "rows_in": result.rows_in,
            "rows_out": result.rows_out,
            "cleaned_path": result.cleaned_path,
            "metadata": result.metadata,
            "issues": [issue.__dict__ for issue in result.issues],
        }
    except Exception as exc:
        payload = {"ok": False, "message": "Could not load data.", "error": str(exc)}
    return templates.TemplateResponse(request, "systems/data/partials/data_load_result.html", {"result": payload})


@router.get("/partials/data-quality", response_class=HTMLResponse)
def data_quality_partial(request: Request, symbol: str = "EURUSD", timeframe: str = "M15") -> HTMLResponse:
    report = backend.get_quality_report(symbol.upper(), timeframe.upper())
    return templates.TemplateResponse(
        request,
        "systems/data/partials/data_quality.html",
        {"report": report},
    )


@router.websocket("/ws/data/live")
async def data_live_ws(websocket: WebSocket, symbol: str) -> None:
    await websocket.accept()
    poll_seconds = float(mt5_service._config().get("tick_poll_seconds", 1.0))
    try:
        while True:
            try:
                tick = backend.get_latest_tick(symbol)
                payload = {
                    "type": "tick",
                    "symbol": tick["symbol"],
                    "bid": tick.get("bid"),
                    "ask": tick.get("ask"),
                    "spread": tick.get("spread_points"),
                    "spread_price": tick.get("spread_price"),
                    "time": tick.get("time"),
                    "mt5_connected": True,
                    "ok": True,
                }
            except Exception as exc:
                payload = {
                    "type": "tick",
                    "symbol": symbol,
                    "bid": None,
                    "ask": None,
                    "spread": None,
                    "spread_price": None,
                    "time": timestamp(),
                    "mt5_connected": False,
                    "ok": False,
                    "error": str(exc),
                }
            await websocket.send_json(payload)
            await asyncio.sleep(poll_seconds)
    except WebSocketDisconnect:
        return
