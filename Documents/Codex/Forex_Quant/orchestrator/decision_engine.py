from __future__ import annotations

from uuid import uuid4

from core.models.decision import DecisionResult
from systems.regime.service import detect_regime_for_rows
from systems.strategy_router.service import get_candidates_for_regime


def decide_from_rows(rows: list[dict], symbol: str, timeframe: str, mode: str = "research") -> DecisionResult:
    regime = detect_regime_for_rows(rows, symbol=symbol, timeframe=timeframe)
    candidates, router_reasons = get_candidates_for_regime(regime.regime_id, mode=mode)
    reasons = [reason.message for reason in regime.reasons] + router_reasons
    if not regime.tradable:
        action = "no_trade"
        reasons.append("Regime is not tradable.")
    elif not candidates:
        action = "no_trade"
        reasons.append("No eligible strategy candidates for selected mode.")
    else:
        action = "research_only"
        reasons.append("Signal generation/risk execution is reserved for later phases.")
    return DecisionResult(
        decision_id=str(uuid4()),
        symbol=symbol,
        regime_result=regime,
        candidate_strategies=candidates,
        final_action=action,
        reasons=reasons,
        metadata={"timeframe": timeframe, "mode": mode},
    )

