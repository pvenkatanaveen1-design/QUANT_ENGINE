from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import fail, ok
from core.config_manager import ConfigManager
from systems.regime import backend


PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["regime"])


@router.get("/regimes", response_class=HTMLResponse)
def regimes_page(request: Request, symbol: str = "EURUSD", timeframe: str = "M15") -> HTMLResponse:
    latest = backend.latest_regime_as_dict(symbol.upper(), timeframe.upper())
    definitions = ConfigManager(PROJECT_ROOT).load_yaml("config/regimes.yaml")
    return templates.TemplateResponse(
        request,
        "systems/regime/templates/regimes.html",
        {"latest": latest, "definitions": definitions},
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
