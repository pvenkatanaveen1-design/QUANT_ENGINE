from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from core.api_response import fail, ok
from systems.risk import backend
from systems.risk.kelly import kelly_full_fraction, kelly_quarter_fraction, prop_capped_risk_fraction


PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(PROJECT_ROOT))
router = APIRouter(tags=["risk"])


@router.get("/position-sizing", response_class=HTMLResponse)
def position_sizing_math_page(request: Request) -> HTMLResponse:
    """Section 20 — Kelly / regime multipliers / prop rules (reference)."""
    return templates.TemplateResponse(request, "systems/risk/templates/position_sizing_math.html", {})


@router.get("/api/risk/kelly-demo")
def kelly_demo(p: float = 0.65, b: float = 3.0) -> JSONResponse:
    """Worked example matching Section 20 Q3_M04 numbers (no account-specific sizing)."""
    full_f = kelly_full_fraction(win_rate=p, payoff_ratio=b)
    q_f = kelly_quarter_fraction(win_rate=p, payoff_ratio=b)
    capped = prop_capped_risk_fraction(win_rate=p, payoff_ratio=b, max_risk_fraction=0.02, kelly_scale=0.25)
    return ok(
        {
            "inputs": {"win_rate": p, "payoff_ratio_b": b},
            "kelly_full_fraction": round(full_f, 6),
            "kelly_quarter_fraction": round(q_f, 6),
            "capped_at_2pct_equity": round(capped, 6),
        },
        "Section 20 Kelly demo.",
    )


@router.get("/risk", response_class=HTMLResponse)
def risk_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "systems/risk/templates/risk.html",
        {"summary": backend.get_risk_summary(), "rules": backend.get_risk_rules(), "funded": backend.get_funded_rules()},
    )


@router.get("/api/risk/rules")
def risk_rules() -> JSONResponse:
    return ok(backend.get_risk_rules(), "Risk rules loaded.")


@router.post("/api/risk/rules/preview")
def preview_risk_rules(
    account_balance: float = Form(10000),
    stop_distance_pips: float = Form(10),
    regime_confidence: float = Form(0.75),
    historical_trust_factor: float = Form(0.25),
    present_risk_factor: float = Form(1.0),
) -> JSONResponse:
    try:
        return ok(
            backend.preview_position_size(account_balance, stop_distance_pips, regime_confidence, historical_trust_factor, present_risk_factor),
            "Risk preview calculated. No order was created.",
        )
    except Exception as exc:
        return fail("Risk preview failed.", code="risk_preview_failed", detail=str(exc), status_code=400)


@router.post("/api/risk/preview-position")
def preview_position_alias(
    account_balance: float = Form(10000),
    stop_distance_pips: float = Form(10),
    regime_confidence: float = Form(0.75),
    historical_trust_factor: float = Form(0.25),
    present_risk_factor: float = Form(1.0),
) -> JSONResponse:
    """Section 17 alias — same as POST /api/risk/rules/preview."""
    return preview_risk_rules(
        account_balance=account_balance,
        stop_distance_pips=stop_distance_pips,
        regime_confidence=regime_confidence,
        historical_trust_factor=historical_trust_factor,
        present_risk_factor=present_risk_factor,
    )


@router.post("/api/risk/rules/save")
def save_risk_rules() -> JSONResponse:
    return fail("Saving risk rules is intentionally disabled in the first safe build.", code="save_disabled", status_code=403)


@router.get("/api/risk/funded-rules")
def funded_rules() -> JSONResponse:
    return ok(backend.get_funded_rules(), "Funded rules loaded.")


@router.get("/api/risk/funded-status")
def funded_status_alias() -> JSONResponse:
    """Section 17 alias — same payload as GET /api/risk/funded-rules."""
    return funded_rules()


@router.get("/partials/risk-summary", response_class=HTMLResponse)
def risk_summary_partial(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/risk/partials/risk_summary.html", {"summary": backend.get_risk_summary()})


@router.get("/partials/funded-rules", response_class=HTMLResponse)
def funded_rules_partial(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/risk/partials/funded_rules.html", {"funded": backend.get_funded_rules()})


@router.get("/partials/kill-switch", response_class=HTMLResponse)
def kill_switch_partial(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "systems/risk/partials/kill_switch.html", {"summary": backend.get_risk_summary()})


@router.post("/partials/risk-preview", response_class=HTMLResponse)
def risk_preview_partial(
    request: Request,
    account_balance: float = Form(10000),
    stop_distance_pips: float = Form(10),
    regime_confidence: float = Form(0.75),
    historical_trust_factor: float = Form(0.25),
    present_risk_factor: float = Form(1.0),
) -> HTMLResponse:
    try:
        preview = backend.preview_position_size(account_balance, stop_distance_pips, regime_confidence, historical_trust_factor, present_risk_factor)
    except Exception as exc:
        preview = {"approval": "rejected_preview", "reasons": [str(exc)], "lot_size": 0, "risk_amount": 0, "final_risk_percent": 0}
    return templates.TemplateResponse(request, "systems/risk/partials/risk_preview.html", {"preview": preview})
