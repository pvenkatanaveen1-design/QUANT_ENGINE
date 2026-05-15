from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from core.config_manager import ConfigManager
from core.models.risk import AccountState, HistoricalTrustProfile, PositionSizeResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LOGGER = logging.getLogger(__name__)


def get_pip_value(symbol: str, config_manager: ConfigManager | None = None) -> float:
    """Reads pip_value_per_lot from config/symbols.yaml; warns and uses 10.0 if missing."""
    cm = config_manager or ConfigManager(PROJECT_ROOT)
    symbols_cfg = cm.load_yaml("config/symbols.yaml")
    sym_data = symbols_cfg.get("symbols", {}).get(symbol.upper(), {})
    pip_val = sym_data.get("pip_value_per_lot")
    if pip_val in (None, ""):
        _LOGGER.warning("pip_value_per_lot not configured for %s; using 10.0 (EURUSD-style default).", symbol.upper())
        return 10.0
    return float(pip_val)


def calculate_lot_size(
    equity: float,
    stop_pips: float,
    risk_pct: float,
    size_multiplier: float,
    symbol: str,
    config_manager: ConfigManager | None = None,
) -> float:
    """
    lot_size = (equity × risk_pct × size_multiplier) / (stop_pips × pip_value_per_lot).
    risk_pct: 0.01 = 1% of equity (not basis points). Clamped to symbol min/max/step.
    """
    if size_multiplier <= 0 or stop_pips <= 0 or equity <= 0:
        return 0.0
    pip_value = get_pip_value(symbol, config_manager)
    raw_lot = (equity * risk_pct * size_multiplier) / (stop_pips * pip_value)
    cm = config_manager or ConfigManager(PROJECT_ROOT)
    sym_data = cm.load_yaml("config/symbols.yaml").get("symbols", {}).get(symbol.upper(), {})
    min_lot = float(sym_data.get("min_lot", 0.01))
    max_lot = float(sym_data.get("max_lot", 100.0))
    lot_step = float(sym_data.get("lot_step", 0.01))
    steps = math.floor(raw_lot / lot_step)
    lot = steps * lot_step
    return max(min_lot, min(max_lot, lot))


def symbol_risk_spec(symbol: str) -> dict[str, Any]:
    symbols = ConfigManager(PROJECT_ROOT).load_yaml("config/symbols.yaml").get("symbols", {})
    spec = dict(symbols.get(symbol.upper(), {}))
    if not spec:
        spec = {"pip_size": 0.01 if symbol.upper().endswith("JPY") or "XAU" in symbol.upper() else 0.0001, "pip_value_mode": "unknown"}
    return spec


def broker_or_config_pip_value(symbol: str, broker_tick_value: float | None = None) -> tuple[float, list[str]]:
    if broker_tick_value and broker_tick_value > 0:
        return float(broker_tick_value), ["Using broker tick value for pip value."]
    spec = symbol_risk_spec(symbol)
    configured = spec.get("pip_value_per_lot")
    if configured not in (None, ""):
        return float(configured), ["Using configured symbol pip_value_per_lot."]
    return (
        0.0,
        [
            f"No pip_value_per_lot in config/symbols.yaml for {symbol.upper()} and no broker tick value; "
            "lot size is blocked until you add pip_value_per_lot or pass broker_tick_value.",
        ],
    )


def calculate_position_size(
    account: AccountState,
    entry_price: float,
    stop_price: float,
    pip_size: float,
    pip_value_per_lot: float | None = None,
    base_risk_percent: float = 0.25,
    max_risk_percent: float = 0.5,
    regime_confidence: float = 1.0,
    historical_trust: HistoricalTrustProfile | None = None,
    regime_size_multiplier: float = 1.0,
) -> PositionSizeResult:
    stop_distance_price = abs(entry_price - stop_price)
    stop_distance_pips = stop_distance_price / pip_size if pip_size else 0.0
    if stop_distance_pips <= 0:
        return PositionSizeResult(lot_size=0.0, risk_amount=0.0, final_risk_percent=0.0, reasons=["Invalid stop distance."])

    pip_val = float(pip_value_per_lot) if pip_value_per_lot is not None else 10.0

    if regime_size_multiplier <= 0:
        return PositionSizeResult(
            lot_size=0.0,
            risk_amount=0.0,
            final_risk_percent=0.0,
            reasons=["Regime size multiplier is zero; position blocked."],
        )

    trust_factor = 1.0 if historical_trust and historical_trust.approved else 0.25
    confidence_factor = max(0.25, min(1.0, regime_confidence))
    final_risk_percent = min(max_risk_percent, base_risk_percent * trust_factor * confidence_factor * regime_size_multiplier)
    risk_amount = account.equity * (final_risk_percent / 100.0)
    lot_size = risk_amount / (stop_distance_pips * pip_val)
    return PositionSizeResult(
        lot_size=max(0.0, lot_size),
        risk_amount=risk_amount,
        final_risk_percent=final_risk_percent,
        reasons=[
            f"Base risk {base_risk_percent:.2f}% adjusted by confidence {confidence_factor:.2f}, trust {trust_factor:.2f}, regime size ×{regime_size_multiplier:.2f}.",
        ],
    )


def calculate_position_size_for_symbol(
    symbol: str,
    account: AccountState,
    entry_price: float,
    stop_price: float,
    broker_tick_value: float | None = None,
    base_risk_percent: float = 0.25,
    max_risk_percent: float = 0.5,
    regime_confidence: float = 1.0,
    historical_trust: HistoricalTrustProfile | None = None,
    regime_size_multiplier: float = 1.0,
) -> PositionSizeResult:
    spec = symbol_risk_spec(symbol)
    pip_value, value_reasons = broker_or_config_pip_value(symbol, broker_tick_value=broker_tick_value)
    if pip_value <= 0:
        return PositionSizeResult(lot_size=0.0, risk_amount=0.0, final_risk_percent=0.0, reasons=value_reasons)
    result = calculate_position_size(
        account=account,
        entry_price=entry_price,
        stop_price=stop_price,
        pip_size=float(spec.get("pip_size") or 0.0001),
        pip_value_per_lot=pip_value,
        base_risk_percent=base_risk_percent,
        max_risk_percent=max_risk_percent,
        regime_confidence=regime_confidence,
        historical_trust=historical_trust,
        regime_size_multiplier=regime_size_multiplier,
    )
    result.reasons.extend(value_reasons)
    return result
