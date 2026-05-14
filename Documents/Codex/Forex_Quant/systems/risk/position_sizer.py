from __future__ import annotations

from core.models.risk import AccountState, HistoricalTrustProfile, PositionSizeResult


def calculate_position_size(
    account: AccountState,
    entry_price: float,
    stop_price: float,
    pip_size: float,
    pip_value_per_lot: float = 10.0,
    base_risk_percent: float = 0.25,
    max_risk_percent: float = 0.5,
    regime_confidence: float = 1.0,
    historical_trust: HistoricalTrustProfile | None = None,
) -> PositionSizeResult:
    stop_distance_price = abs(entry_price - stop_price)
    stop_distance_pips = stop_distance_price / pip_size if pip_size else 0.0
    if stop_distance_pips <= 0:
        return PositionSizeResult(lot_size=0.0, risk_amount=0.0, final_risk_percent=0.0, reasons=["Invalid stop distance."])

    trust_factor = 1.0 if historical_trust and historical_trust.approved else 0.25
    confidence_factor = max(0.25, min(1.0, regime_confidence))
    final_risk_percent = min(max_risk_percent, base_risk_percent * trust_factor * confidence_factor)
    risk_amount = account.equity * (final_risk_percent / 100.0)
    lot_size = risk_amount / (stop_distance_pips * pip_value_per_lot)
    return PositionSizeResult(
        lot_size=max(0.0, lot_size),
        risk_amount=risk_amount,
        final_risk_percent=final_risk_percent,
        reasons=[
            f"Base risk {base_risk_percent:.2f}% adjusted by confidence {confidence_factor:.2f} and trust {trust_factor:.2f}.",
        ],
    )

