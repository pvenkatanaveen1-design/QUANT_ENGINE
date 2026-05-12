"""
Phase 2 — strategy shortlist and scoring from headline quadrant + session + spread.

Pair-agnostic: `symbol` is accepted on public APIs for downstream use; scoring does
not hardcode any instrument. Wire to MT5 snapshot in a later step.
"""

from __future__ import annotations

from typing import Any

STRATEGY_MAP: dict[str, dict[str, Any]] = {
    "Q1": {
        "strategies": [
            {"name": "alpha_breakout", "min_score": 65, "size_mult": 1.0},
            {"name": "alpha_pullback", "min_score": 60, "size_mult": 1.0},
            {"name": "london_ob_entry", "min_score": 70, "size_mult": 0.8},
        ],
        "trade_allowed": True,
        "size_multiplier": 1.0,
    },
    "Q2": {
        "strategies": [
            {"name": "alpha_breakout", "min_score": 70, "size_mult": 0.5},
            {"name": "momentum_entry", "min_score": 65, "size_mult": 0.5},
        ],
        "trade_allowed": True,
        "size_multiplier": 0.5,
    },
    "Q3": {
        "strategies": [
            {"name": "alpha_sweep", "min_score": 60, "size_mult": 1.0},
            {"name": "mean_reversion", "min_score": 65, "size_mult": 0.8},
            {"name": "session_breakout", "min_score": 70, "size_mult": 1.0},
        ],
        "trade_allowed": True,
        "size_multiplier": 1.0,
    },
    "Q4": {
        "strategies": [],
        "trade_allowed": False,
        "size_multiplier": 0.0,
    },
}


def _session_points(session: str) -> float:
    s = (session or "").upper().strip()
    if s == "LONDON":
        return 20.0
    if s == "NEW_YORK":
        return 15.0
    if s == "OVERLAP":
        return 20.0
    if s == "ASIA":
        return 0.0
    if s == "OFF":
        return 0.0
    return 0.0


def _spread_points(spread: float | None) -> float:
    if spread is None:
        return 0.0
    try:
        sp = float(spread)
    except (TypeError, ValueError):
        return 0.0
    if sp < 1.0:
        return 10.0
    if sp < 2.0:
        return 5.0
    return 0.0


def _confidence_tier_mult(confidence: float) -> tuple[float, str]:
    """Returns (multiplier applied to quadrant size_multiplier, tier label)."""
    c = float(confidence)
    if c < 50.0:
        return 0.0, "low"
    if c < 70.0:
        return 0.5, "medium"
    return 1.0, "high"


def get_strategy_scores(
    quadrant: str,
    confidence: float,
    spread: float | None,
    session: str,
    *,
    symbol: str = "",
) -> list[dict[str, Any]]:
    """
    Raw 0–100 score per allowed strategy in this quadrant.

    - regime_points: 40 (row is in quadrant list)
    - confidence_points: (confidence / 100) * 30
    - session_points: LONDON=20, NEW_YORK=15, OVERLAP=20, ASIA/OFF/unknown=0
    - spread_points: spread < 1 → 10, < 2 → 5, else 0

    `symbol` is reserved (logged by callers later); not used in the formula.
    """
    _ = symbol  # reserved for pair-specific rules later
    q = (quadrant or "").upper().strip()
    block = STRATEGY_MAP.get(q) or {"strategies": []}
    rows = list(block.get("strategies") or [])
    conf_f = float(confidence)
    cp = (conf_f / 100.0) * 30.0
    sp_sess = _session_points(session)
    sp_sprd = _spread_points(spread)

    out: list[dict[str, Any]] = []
    for spec in rows:
        name = str(spec["name"])
        regime_pts = 40.0
        total = regime_pts + cp + sp_sess + sp_sprd
        total = round(min(100.0, max(0.0, total)), 2)
        out.append(
            {
                "name": name,
                "score": total,
                "regime_points": regime_pts,
                "confidence_points": round(cp, 4),
                "session_points": sp_sess,
                "spread_points": sp_sprd,
                "min_score": int(spec["min_score"]),
                "size_mult": float(spec["size_mult"]),
            }
        )
    return out


def get_active_strategies(
    quadrant: str,
    confidence: float,
    spread: float | None,
    session: str,
    *,
    symbol: str = "",
    signal_conditions_met: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """
    Build tradability summary and per-strategy status.

    Status rules:
    - confidence < 50: all NOT_READY, trade_allowed False, reason explains low confidence.
    - Q4: no strategies, trade_allowed False.
    - confidence in [50, 70): eligible strategies (score >= min_score) are WATCHING;
      trade_allowed True for Q1–Q3 with quadrant size_multiplier * 0.5.
    - confidence >= 70: **WATCHING** when score >= min_score; **ARMED** only if
      ``signal_conditions_met[name]`` is True (no default ARMED until signals exist).

    ``symbol`` is passed through for future pair-specific gates; unused in scoring today.
    """
    _ = symbol
    q = (quadrant or "").upper().strip()
    conf_f = float(confidence)
    block = STRATEGY_MAP.get(q) or {"strategies": [], "trade_allowed": False, "size_multiplier": 0.0}
    base_allowed = bool(block.get("trade_allowed"))
    base_sz = float(block.get("size_multiplier") or 0.0)

    scored = get_strategy_scores(q, conf_f, spread, session, symbol=symbol)

    if q == "Q4" or not base_allowed:
        return {
            "trade_allowed": False,
            "reason": "Q4 — transition / chaos (no trading)",
            "size_multiplier": 0.0,
            "strategies": [],
        }

    if conf_f < 50.0:
        strats_out: list[dict[str, Any]] = []
        for row in scored:
            strats_out.append(
                {
                    "name": row["name"],
                    "score": row["score"],
                    "status": "NOT_READY",
                    "min_score": row["min_score"],
                    "size_mult": 0.0,
                }
            )
        return {
            "trade_allowed": False,
            "reason": "Regime confidence too low to trade",
            "size_multiplier": 0.0,
            "strategies": strats_out,
        }

    tier_mult, _tier = _confidence_tier_mult(conf_f)
    global_sz = base_sz * tier_mult
    reason = ""
    if conf_f < 70.0:
        reason = "Confidence 50–69: reduced size (50% of quadrant multiplier)"

    sig = signal_conditions_met or {}

    strats_out = []
    for row in scored:
        name = row["name"]
        score = float(row["score"])
        min_sc = int(row["min_score"])
        eff_size = float(row["size_mult"]) * global_sz

        if score < float(min_sc):
            status = "NOT_READY"
        elif conf_f < 70.0:
            status = "WATCHING"
        elif sig.get(name, False):
            status = "ARMED"
        else:
            status = "WATCHING"

        strats_out.append(
            {
                "name": name,
                "score": score,
                "status": status,
                "min_score": min_sc,
                "size_mult": round(eff_size, 4),
            }
        )

    return {
        "trade_allowed": True,
        "reason": reason,
        "size_multiplier": round(global_sz, 4),
        "strategies": strats_out,
    }
