from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import fail, ok, timestamp
from core.config_manager import ConfigManager
from systems.regime import backend


PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["regime"])


@router.get("/regimes", response_class=HTMLResponse)
def regimes_page(request: Request, symbol: str = "EURUSD", timeframe: str = "M15") -> HTMLResponse:
    options = backend.get_regime_options()
    definitions = ConfigManager(PROJECT_ROOT).load_yaml("config/regimes.yaml")
    return templates.TemplateResponse(
        request,
        "systems/regime/templates/regimes.html",
        {"definitions": definitions, "options": options},
    )


@router.get("/api/regimes/latest")
def latest_regime(symbol: str = "EURUSD", timeframe: str = "M15") -> JSONResponse:
    latest = backend.latest_regime_as_dict(symbol.upper(), timeframe.upper())
    if latest.get("confidence") == 0.0 and latest.get("risk_posture") == "missing_data":
        return fail("Could not detect latest regime.", code="missing_data", detail=latest["reasons"][0]["message"], status_code=404)
    return ok(latest, "Latest regime detected.")


@router.post("/api/regimes/detect")
def detect_regime(symbol: str = Form("EURUSD"), timeframe: str = Form("M15")) -> JSONResponse:
    latest = backend.latest_regime_as_dict(symbol.upper(), timeframe.upper())
    if latest.get("confidence") == 0.0 and latest.get("risk_posture") == "missing_data":
        return fail("Could not detect regime.", code="missing_data", detail=latest["reasons"][0]["message"], status_code=404)
    return ok(latest, "Regime detected.")


@router.get("/api/regimes/history")
def regime_history() -> JSONResponse:
    return ok({"history": []}, "History storage lands with the research/journal phase.")


@router.get("/api/regimes/definitions")
def regime_definitions() -> JSONResponse:
    return ok(ConfigManager(PROJECT_ROOT).load_yaml("config/regimes.yaml"), "Regime definitions loaded.")


@router.get("/api/regimes/options")
def regime_options() -> JSONResponse:
    return ok(backend.get_regime_options(), "Regime options loaded.")


@router.get("/api/regimes/one-week")
def one_week_regime(
    source: str = "mt5_demo",
    symbol: str = "EURUSD",
    timeframe: str = "M15",
    bars: int = 0,
    killzone_enabled: bool = True,
    include_spread_filter: bool = True,
    include_sweep_detection: bool = True,
    include_alpha_features: bool = True,
    selected_regime: str | None = None,
) -> JSONResponse:
    try:
        return ok(
            backend.run_one_week_test(
                source=source,
                symbol=symbol.upper(),
                timeframe=timeframe.upper(),
                bars=bars or None,
                killzone_enabled=killzone_enabled,
                include_spread_filter=include_spread_filter,
                include_sweep_detection=include_sweep_detection,
                include_alpha_features=include_alpha_features,
                selected_regime=selected_regime,
            ),
            "One-week regime snapshot loaded.",
        )
    except Exception as exc:
        return fail("Could not build one-week regime snapshot.", code="regime_window_failed", detail=str(exc), status_code=400)


@router.get("/api/regimes/scan")
def scan_regimes(
    symbol: str = "EURUSD",
    timeframe: str = "M15",
    lookback_days: int = 7,
    bars: int = 0,
    killzone_enabled: bool = True,
    selected_regime: str | None = None,
    source: str = "mt5_demo",
) -> JSONResponse:
    try:
        return ok(
            backend.run_regime_scan(
                source=source,
                symbol=symbol.upper(),
                timeframe=timeframe.upper(),
                lookback_days=lookback_days,
                bars=bars or None,
                killzone_enabled=killzone_enabled,
                selected_regime=selected_regime.upper() if selected_regime else None,
            ),
            "Full 52-regime scan loaded.",
        )
    except Exception as exc:
        return fail("Could not scan regimes.", code="regime_scan_failed", detail=str(exc), status_code=400)


@router.get("/api/regimes/current")
def current_regime_state(symbol: str = "EURUSD", timeframe: str = "M15") -> JSONResponse:
    try:
        return ok(backend.current_regime_state(symbol.upper(), timeframe.upper()), "Current regime state loaded.")
    except Exception as exc:
        return fail("Could not load current regime.", code="current_regime_failed", detail=str(exc), status_code=400)


@router.get("/api/regimes/change-stats")
def change_stats(symbol: str = "EURUSD", timeframe: str = "M15", lookback_days: int = 7) -> JSONResponse:
    try:
        return ok(backend.regime_change_stats(symbol.upper(), timeframe.upper(), lookback_days), "Regime change stats loaded.")
    except Exception as exc:
        return fail("Could not load regime change stats.", code="change_stats_failed", detail=str(exc), status_code=400)


@router.get("/api/regimes/{regime_id}/trade-state")
def trade_state(regime_id: str, symbol: str = "EURUSD", timeframe: str = "M15", bars: int = 0) -> JSONResponse:
    try:
        return ok(
            backend.trade_state_for_regime(symbol.upper(), timeframe.upper(), regime_id.upper(), bars=bars or None),
            "Trade-ready regime state loaded.",
        )
    except Exception as exc:
        return fail("Could not load trade-ready state.", code="trade_state_failed", detail=str(exc), status_code=400)


@router.post("/partials/regime-wizard", response_class=HTMLResponse)
def regime_wizard_partial(
    request: Request,
    source: str = Form("mt5_demo"),
    symbol: str = Form("EURUSD"),
    timeframe: str = Form("M15"),
    bars: int = Form(0),
    killzone_enabled: bool = Form(False),
    include_spread_filter: bool = Form(False),
    include_sweep_detection: bool = Form(False),
    include_alpha_features: bool = Form(False),
    selected_regime: str | None = Form(None),
) -> HTMLResponse:
    snapshot = None
    snapshot_error = None
    try:
        snapshot = backend.run_one_week_test(
            source=source,
            symbol=symbol.upper(),
            timeframe=timeframe.upper(),
            bars=bars or None,
            killzone_enabled=killzone_enabled,
            include_spread_filter=include_spread_filter,
            include_sweep_detection=include_sweep_detection,
            include_alpha_features=include_alpha_features,
            selected_regime=selected_regime,
            force_refresh=True,
        )
    except Exception as exc:
        snapshot_error = str(exc)
    return templates.TemplateResponse(request, "systems/regime/partials/regime_wizard.html", {"snapshot": snapshot, "snapshot_error": snapshot_error})


@router.get("/partials/regime-wizard", response_class=HTMLResponse)
def regime_wizard_partial_get(
    request: Request,
    source: str = "mt5_demo",
    symbol: str = "EURUSD",
    timeframe: str = "M15",
    bars: int = 160,
    killzone_enabled: bool = True,
    include_spread_filter: bool = True,
    include_sweep_detection: bool = True,
    include_alpha_features: bool = True,
    selected_regime: str | None = None,
) -> HTMLResponse:
    snapshot = None
    snapshot_error = None
    try:
        snapshot = backend.run_one_week_test(
            source=source,
            symbol=symbol.upper(),
            timeframe=timeframe.upper(),
            bars=bars or None,
            killzone_enabled=killzone_enabled,
            include_spread_filter=include_spread_filter,
            include_sweep_detection=include_sweep_detection,
            include_alpha_features=include_alpha_features,
            selected_regime=selected_regime,
        )
    except Exception as exc:
        snapshot_error = str(exc)
    return templates.TemplateResponse(request, "systems/regime/partials/regime_wizard.html", {"snapshot": snapshot, "snapshot_error": snapshot_error})


@router.get("/partials/latest-regime", response_class=HTMLResponse)
def latest_regime_partial(request: Request, symbol: str = "EURUSD", timeframe: str = "M15") -> HTMLResponse:
    latest = backend.latest_regime_as_dict(symbol.upper(), timeframe.upper())
    return templates.TemplateResponse(request, "systems/regime/partials/latest_regime.html", {"latest": latest})


@router.get("/partials/regime-feature-table", response_class=HTMLResponse)
def regime_feature_table(request: Request, symbol: str = "EURUSD", timeframe: str = "M15") -> HTMLResponse:
    latest = backend.latest_regime_as_dict(symbol.upper(), timeframe.upper())
    return templates.TemplateResponse(request, "systems/regime/partials/regime_feature_table.html", {"features": latest.get("features", {})})


@router.get("/partials/regime-reasons", response_class=HTMLResponse)
def regime_reasons(request: Request, symbol: str = "EURUSD", timeframe: str = "M15") -> HTMLResponse:
    latest = backend.latest_regime_as_dict(symbol.upper(), timeframe.upper())
    return templates.TemplateResponse(request, "systems/regime/partials/regime_reasons.html", {"latest": latest})


@router.websocket("/ws/regime/live")
async def regime_live_ws(websocket: WebSocket, symbol: str, tf_minutes: int = 15, timeframe: str | None = None) -> None:
    await websocket.accept()
    timeframe_key = (timeframe or {1: "M1", 5: "M5", 15: "M15", 30: "M30", 60: "H1", 240: "H4", 1440: "D1"}.get(int(tf_minutes), "M15")).upper()
    try:
        while True:
            try:
                snapshot = backend.run_one_week_test(symbol=symbol.upper(), timeframe=timeframe_key, bars=160)
                payload = {
                    "type": "regime",
                    "symbol": snapshot.get("symbol", symbol.upper()),
                    "tf_minutes": tf_minutes,
                    "timeframe": timeframe_key,
                    "current_regime": snapshot.get("current_regime"),
                    "previous_regime": snapshot.get("previous_regime"),
                    "active_duration_minutes": snapshot.get("active_duration_minutes"),
                    "change_stats": snapshot.get("change_stats"),
                    "risk_state": {
                        "kill_switch": False,
                        "live_trading": "disabled",
                        "data_quality": (snapshot.get("data_quality") or {}).get("status", "unknown"),
                    },
                    "time": timestamp(),
                    "ok": True,
                }
            except Exception as exc:
                payload = {
                    "type": "regime",
                    "symbol": symbol.upper(),
                    "tf_minutes": tf_minutes,
                    "timeframe": timeframe_key,
                    "current_regime": None,
                    "previous_regime": None,
                    "risk_state": {"live_trading": "disabled"},
                    "time": timestamp(),
                    "ok": False,
                    "error": str(exc),
                }
            await websocket.send_json(payload)
            await asyncio.sleep(3.0)
    except WebSocketDisconnect:
        return
