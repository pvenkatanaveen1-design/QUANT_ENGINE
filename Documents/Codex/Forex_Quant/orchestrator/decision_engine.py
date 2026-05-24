from __future__ import annotations

from uuid import uuid4

from systems.journal.service import log_decision
from core.models.decision import DecisionResult
from core.models.risk import PresentRiskSnapshot
from core.models.signal import Signal
from systems.regime.service import detect_regime_for_rows
from systems.risk.cost_guard import check_costs
from systems.strategy.signals import SignalResult, compute_signal

Q1_SIZE_MULTIPLIER = 1.00
Q2_SIZE_MULTIPLIER = 0.50
Q3_SIZE_MULTIPLIER = 0.75

SIZE_OVERRIDES: dict[str, float] = {
    "Q1_M03": 0.50,
    "Q1_M07": 0.00,
    "Q1_M11": 0.75,
    "Q2_M08": 0.35,
    "Q2_M09": 0.35,
    "Q3_M02": 0.50,
}


def _log(result: DecisionResult) -> None:
    try:
        log_decision(result)
    except Exception:
        pass


def _signal_to_core(symbol: str, sig: SignalResult, size_mult: float) -> Signal:
    return Signal(
        strategy_id=sig.strategy_id,
        symbol=symbol,
        direction="long" if sig.direction == "BUY" else "short",
        entry=round(sig.entry_price, 6),
        stop=round(sig.stop_price, 6),
        target=round(sig.tp_price, 6),
        confidence=round(max(0.05, min(0.95, sig.confidence)), 4),
        reason=sig.reason,
        metadata={
            "rr_ratio": sig.rr_ratio,
            "size_multiplier": size_mult,
            "signal_direction": sig.direction,
        },
    )


def decide_from_rows(
    rows: list[dict],
    symbol: str,
    timeframe: str,
    mode: str = "research",
) -> DecisionResult:
    reasons: list[str] = []

    regime = detect_regime_for_rows(rows, symbol=symbol, timeframe=timeframe)
    reasons.append(f"Regime: {regime.regime_id} | conf={regime.confidence:.2f} | tradable={regime.tradable}")

    if not regime.tradable:
        result = DecisionResult(
            decision_id=str(uuid4()),
            symbol=symbol,
            regime_result=regime,
            candidate_strategies=[],
            final_action="no_trade",
            reasons=reasons,
            metadata={"timeframe": timeframe, "mode": mode, "gate": "regime_not_tradable", "size_multiplier": 0.0},
        )
        _log(result)
        return result

    spread_pct = float(regime.features.spread_percentile or 0.0)
    if rows:
        spread_pct = float(rows[-1].get("spread_percentile") or spread_pct or 0.0)
    cost_check = check_costs(PresentRiskSnapshot(spread_percentile=spread_pct))
    if not cost_check.approved:
        result = DecisionResult(
            decision_id=str(uuid4()),
            symbol=symbol,
            regime_result=regime,
            candidate_strategies=[],
            final_action="no_trade",
            reasons=reasons + cost_check.reasons,
            metadata={"timeframe": timeframe, "mode": mode, "gate": "cost_guard", "size_multiplier": 0.0},
        )
        _log(result)
        return result

    signal: SignalResult = compute_signal(rows, regime.regime_id)
    reasons.append(f"Signal: {signal.strategy_id} | dir={signal.direction} | RR={signal.rr_ratio:.2f} | reason={signal.reason}")

    base = regime.regime_id[:2]
    size_mult = { "Q1": Q1_SIZE_MULTIPLIER, "Q2": Q2_SIZE_MULTIPLIER, "Q3": Q3_SIZE_MULTIPLIER, "Q4": 0.0}.get(base, 0.5)
    if signal.size_override >= 0:
        size_mult = float(signal.size_override)
    if regime.regime_id in SIZE_OVERRIDES:
        size_mult = float(SIZE_OVERRIDES[regime.regime_id])

    if signal.direction == "NONE":
        result = DecisionResult(
            decision_id=str(uuid4()),
            symbol=symbol,
            regime_result=regime,
            candidate_strategies=[],
            final_action="no_trade",
            reasons=reasons,
            metadata={
                "timeframe": timeframe,
                "mode": mode,
                "signal_direction": "NONE",
                "signal_strategy": signal.strategy_id,
                "gate": "signal_none",
                "size_multiplier": 0.0,
            },
        )
        _log(result)
        return result

    if signal.rr_ratio < 1.5:
        result = DecisionResult(
            decision_id=str(uuid4()),
            symbol=symbol,
            regime_result=regime,
            candidate_strategies=[],
            final_action="no_trade",
            reasons=reasons,
            metadata={
                "timeframe": timeframe,
                "mode": mode,
                "signal_direction": signal.direction,
                "signal_rr": round(signal.rr_ratio, 2),
                "gate": "rr_too_low",
                "size_multiplier": 0.0,
            },
        )
        _log(result)
        return result

    action = "research_only"
    if mode == "paper":
        action = "paper_execute"
    elif mode == "live":
        action = "live_execute"

    selected = _signal_to_core(symbol, signal, size_mult)
    kill_zone = bool(rows[-1].get("kill_zone_active")) if rows else False

    result = DecisionResult(
        decision_id=str(uuid4()),
        symbol=symbol,
        regime_result=regime,
        candidate_strategies=[],
        selected_signal=selected,
        final_action=action,
        reasons=reasons,
        metadata={
            "timeframe": timeframe,
            "mode": mode,
            "signal_direction": signal.direction,
            "signal_strategy": signal.strategy_id,
            "entry_price": signal.entry_price,
            "stop_price": signal.stop_price,
            "tp_price": signal.tp_price,
            "rr_ratio": round(signal.rr_ratio, 2),
            "signal_confidence": signal.confidence,
            "size_multiplier": size_mult,
            "regime_id": regime.regime_id,
            "regime_confidence": regime.confidence,
            "kill_zone_active": kill_zone,
        },
    )
    _log(result)
    return result
