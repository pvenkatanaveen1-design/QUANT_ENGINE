from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import fail, ok
from systems.data import backend


PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["data"])


@router.get("/data", response_class=HTMLResponse)
def data_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "systems/data/templates/data.html",
        {"status": backend.get_dataset_status(), "config": backend.get_data_config()},
    )


@router.get("/api/data/status")
def data_status() -> JSONResponse:
    return ok(backend.get_dataset_status(), "Data status loaded.")


@router.post("/api/data/load-csv")
def load_csv(symbol: str = Form("EURUSD"), timeframe: str = Form("M15"), input_path: str = Form("")) -> JSONResponse:
    try:
        result = backend.load_csv(symbol.upper(), timeframe.upper(), input_path=input_path.strip() or None)
        return ok(
            {
                "symbol": result.symbol,
                "timeframe": result.timeframe,
                "quality_status": result.quality_status,
                "rows_in": result.rows_in,
                "rows_out": result.rows_out,
                "cleaned_path": result.cleaned_path,
                "report_path": result.report_path,
                "issues": [issue.__dict__ for issue in result.issues],
            },
            "CSV loaded and cleaned.",
        )
    except FileNotFoundError as exc:
        return fail("Could not load CSV data.", code="missing_file", detail=str(exc), status_code=404)
    except Exception as exc:
        return fail("Could not load CSV data.", code="data_load_failed", detail=str(exc), status_code=400)


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
def data_load_result_partial(request: Request, symbol: str = Form("EURUSD"), timeframe: str = Form("M15"), input_path: str = Form("")) -> HTMLResponse:
    try:
        result = backend.load_csv(symbol.upper(), timeframe.upper(), input_path=input_path.strip() or None)
        payload = {
            "ok": True,
            "message": "CSV loaded and cleaned.",
            "symbol": result.symbol,
            "timeframe": result.timeframe,
            "quality_status": result.quality_status,
            "rows_in": result.rows_in,
            "rows_out": result.rows_out,
            "cleaned_path": result.cleaned_path,
            "issues": [issue.__dict__ for issue in result.issues],
        }
    except Exception as exc:
        payload = {"ok": False, "message": "Could not load CSV data.", "error": str(exc)}
    return templates.TemplateResponse(request, "systems/data/partials/data_load_result.html", {"result": payload})


@router.get("/partials/data-quality", response_class=HTMLResponse)
def data_quality_partial(request: Request, symbol: str = "EURUSD", timeframe: str = "M15") -> HTMLResponse:
    report = backend.get_quality_report(symbol.upper(), timeframe.upper())
    return templates.TemplateResponse(
        request,
        "systems/data/partials/data_quality.html",
        {"report": report},
    )
