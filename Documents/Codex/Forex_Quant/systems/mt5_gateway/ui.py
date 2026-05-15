from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import fail, ok, timestamp
from systems.mt5_gateway import backend, service
from systems.mt5_gateway.schemas import RatesQuery


PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["mt5-gateway"])


def _gateway_fail(exc: Exception) -> JSONResponse:
    if isinstance(exc, service.MT5GatewayError):
        return fail(exc.detail, code=exc.code, status_code=exc.status_code)
    return fail("MT5 gateway request failed.", code="mt5_gateway_error", detail=str(exc), status_code=500)


@router.get("/mt5", response_class=HTMLResponse)
def mt5_page(request: Request, symbol: str = "") -> HTMLResponse:
    status = backend.get_status()
    symbols = backend.get_symbols()
    all_symbols = symbols.get("symbols", [])
    display_symbols = [item for item in all_symbols if item.get("popular")] or all_symbols[:250]
    symbols = {**symbols, "symbols": display_symbols, "total_symbols": len(all_symbols)}
    timeframes = backend.get_timeframes()
    tick = None
    selected_symbol = symbol or next((item["symbol"] for item in symbols.get("symbols", [])), "")
    if selected_symbol:
        try:
            tick = backend.get_tick(selected_symbol)
        except Exception:
            tick = None
    return templates.TemplateResponse(
        request,
        "systems/mt5_gateway/templates/mt5.html",
        {"status": status, "symbols": symbols, "timeframes": timeframes, "selected_symbol": selected_symbol, "tick": tick},
    )


@router.get("/api/mt5/status")
def mt5_status() -> JSONResponse:
    return ok(backend.get_status(), "MT5 status loaded.")


@router.get("/api/mt5/account")
def mt5_account() -> JSONResponse:
    status = backend.get_status()
    return ok(status.get("account_info"), "MT5 account info loaded." if status.get("account_info") else "MT5 account info unavailable.")


@router.get("/api/mt5/symbols")
def mt5_symbols() -> JSONResponse:
    payload = backend.get_symbols()
    message = "MT5 symbols loaded." if payload.get("available") else "MT5 symbols unavailable."
    return ok(payload, message, warnings=[payload.get("reason")] if payload.get("reason") else None)


@router.get("/api/mt5/timeframes")
def mt5_timeframes() -> JSONResponse:
    return ok({"timeframes": backend.get_timeframes()}, "MT5 timeframe options loaded.")


@router.get("/api/mt5/symbol/{symbol}")
def mt5_symbol(symbol: str) -> JSONResponse:
    try:
        symbols = backend.get_symbols()
        resolved = backend.resolve_symbol(symbol)
        match = next((item for item in symbols.get("symbols", []) if item["symbol"] == resolved), None)
        if not match:
            return fail(f"Symbol not found: {symbol}", code="invalid_symbol", status_code=404)
        return ok(match, "MT5 symbol loaded.")
    except Exception as exc:
        return _gateway_fail(exc)


@router.get("/api/mt5/tick")
def mt5_tick_query(symbol: str) -> JSONResponse:
    try:
        return ok(backend.get_tick(symbol), "MT5 tick loaded.")
    except Exception as exc:
        return _gateway_fail(exc)


@router.get("/api/mt5/tick/{symbol}")
def mt5_tick_path(symbol: str) -> JSONResponse:
    try:
        return ok(backend.get_tick(symbol), "MT5 tick loaded.")
    except Exception as exc:
        return _gateway_fail(exc)


@router.get("/api/mt5/rates")
def mt5_rates(query: RatesQuery = Depends()) -> JSONResponse:
    try:
        return ok(backend.get_rates(query.symbol, query.timeframe, query.bars), "MT5 rates loaded.")
    except Exception as exc:
        return _gateway_fail(exc)


@router.post("/api/mt5/rates")
def mt5_rates_post(query: RatesQuery = Depends()) -> JSONResponse:
    try:
        return ok(backend.get_rates(query.symbol, query.timeframe, query.bars), "MT5 rates loaded.")
    except Exception as exc:
        return _gateway_fail(exc)


@router.get("/partials/mt5-status", response_class=HTMLResponse)
def mt5_status_partial(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/mt5_gateway/partials/mt5_status.html", {"status": backend.get_status()})


@router.websocket("/ws/mt5/tick")
async def mt5_tick_ws(websocket: WebSocket, symbol: str) -> None:
    await websocket.accept()
    poll_seconds = float(service._config().get("tick_poll_seconds", 1.0))
    try:
        while True:
            try:
                tick = backend.get_tick(symbol)
                payload = {"type": "tick", **tick, "mt5_connected": True, "ok": True}
            except Exception as exc:
                status = backend.get_status()
                detail = exc.detail if isinstance(exc, service.MT5GatewayError) else str(exc)
                payload = {
                    "type": "tick",
                    "symbol": symbol,
                    "bid": None,
                    "ask": None,
                    "last": None,
                    "spread_points": None,
                    "spread_price": None,
                    "time": timestamp(),
                    "mt5_connected": bool(status.get("connected")),
                    "ok": False,
                    "error": detail,
                }
            await websocket.send_json(payload)
            await asyncio.sleep(poll_seconds)
    except WebSocketDisconnect:
        return


@router.websocket("/ws/mt5/status")
async def mt5_status_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    poll_seconds = float(service._config().get("status_poll_seconds", 5.0))
    try:
        while True:
            status = backend.get_status()
            await websocket.send_json({"type": "mt5_status", **status, "ok": True})
            await asyncio.sleep(poll_seconds)
    except WebSocketDisconnect:
        return
