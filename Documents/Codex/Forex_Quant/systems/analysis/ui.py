from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import ok
from systems.analysis import db
from systems.context import service as context_service


PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["analysis"])


@router.get("/evaluation-metrics", response_class=HTMLResponse)
def evaluation_metrics_page(request: Request) -> HTMLResponse:
    """Metric definitions, formulas, and interpretive targets."""
    return templates.TemplateResponse(request, "systems/analysis/templates/evaluation_metrics.html", {})


@router.get("/analysis", response_class=HTMLResponse)
def analysis_page(request: Request) -> HTMLResponse:
    db.init_db()
    return templates.TemplateResponse(
        request,
        "systems/analysis/templates/analysis.html",
        {"runs": db.list_backtest_runs(), "cache": db.get_analysis_cache()},
    )


@router.get("/analytics", response_class=HTMLResponse)
def analytics_dashboard(request: Request, run_id: str | None = None) -> HTMLResponse:
    db.init_db()
    wf_runs = db.list_signal_engine_runs(limit=40)
    if not run_id and wf_runs:
        run_id = wf_runs[0]["run_id"]
    return templates.TemplateResponse(
        request,
        "systems/analysis/templates/analytics.html",
        {"wf_runs": wf_runs, "default_run_id": run_id or ""},
    )


@router.get("/api/analytics/data")
def analytics_data(run_id: str | None = None) -> JSONResponse:
    db.init_db()
    wf_runs = db.list_signal_engine_runs(limit=40)
    if not run_id and wf_runs:
        run_id = wf_runs[0]["run_id"]
    if not run_id:
        return ok({"run_id": None, "cache": [], "equity": [], "wf_runs": wf_runs}, "No signal-engine runs yet.")
    cache = db.get_analysis_cache(run_id=run_id)
    equity: list[dict[str, float | int]] = []
    with db.get_duckdb() as conn:
        rows = conn.execute(
            """
            SELECT trade_number, equity, drawdown, pnl_r_cumulative
            FROM equity_snapshots
            WHERE run_id = ?
            ORDER BY trade_number
            """,
            [run_id],
        ).fetchall()
        for row in rows:
            equity.append(
                {
                    "trade_number": int(row[0]),
                    "equity": float(row[1]),
                    "drawdown_pct": float(row[2]),
                    "pnl_r_cumulative": float(row[3]),
                }
            )
    return ok(
        {
            "run_id": run_id,
            "cache": cache,
            "equity": equity,
            "wf_runs": wf_runs,
        },
        "Analytics payload loaded.",
    )


@router.get("/api/analytics/runs")
def analytics_runs(limit: int = 40) -> JSONResponse:
    """Thin list for run selector (Section 17)."""
    db.init_db()
    return ok({"runs": db.list_signal_engine_runs(limit=min(limit, 200))}, "Analytics runs loaded.")


@router.get("/api/analysis/status")
def analysis_status() -> JSONResponse:
    paths = db.init_db()
    return ok({"paths": paths, "runs": db.list_backtest_runs(limit=10)}, "Analysis database ready.")


@router.get("/api/analysis/cache")
def analysis_cache(run_id: str | None = None, cache_type: str | None = None) -> JSONResponse:
    return ok({"cache": db.get_analysis_cache(run_id=run_id, cache_type=cache_type)}, "Analysis cache loaded.")


@router.get("/api/context/status")
def context_status(symbol: str = "EURUSD", timeframe: str = "M15") -> JSONResponse:
    return ok(context_service.full_context_status(symbol=symbol.upper(), timeframe=timeframe.upper()), "External context status loaded.")
