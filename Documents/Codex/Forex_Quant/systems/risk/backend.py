from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config_manager import ConfigManager
from core.models.risk import AccountState, HistoricalTrustProfile
from systems.risk.position_sizer import calculate_position_size


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_risk_rules() -> dict[str, Any]:
    return ConfigManager(PROJECT_ROOT).load_yaml("config/risk_rules.yaml")


def get_funded_rules() -> dict[str, Any]:
    return ConfigManager(PROJECT_ROOT).load_yaml("config/funded_rules.yaml")


def get_risk_summary() -> dict[str, Any]:
    rules = get_risk_rules()
    return {
        "live_trading_enabled": False,
        "base_risk_per_trade_percent": rules.get("base_risk_per_trade_percent"),
        "max_daily_loss_percent": rules.get("max_daily_loss_percent"),
        "max_total_drawdown_percent": rules.get("max_total_drawdown_percent"),
        "max_allowed_spread_percentile": rules.get("max_allowed_spread_percentile"),
        "manual_kill_switch": rules.get("manual_kill_switch", False),
    }


def preview_position_size(
    account_balance: float,
    stop_distance_pips: float,
    regime_confidence: float,
    historical_trust_factor: float,
    present_risk_factor: float,
) -> dict[str, Any]:
    rules = get_risk_rules()
    stop_distance_pips = max(stop_distance_pips, 0.0)
    entry = 1.1000
    stop = entry - (stop_distance_pips * 0.0001)
    approved_trust = historical_trust_factor >= 0.75
    result = calculate_position_size(
        account=AccountState(equity=account_balance),
        entry_price=entry,
        stop_price=stop,
        pip_size=0.0001,
        base_risk_percent=float(rules.get("base_risk_per_trade_percent", 0.25)) * max(0.1, min(1.0, present_risk_factor)),
        max_risk_percent=float(rules.get("max_risk_per_trade_percent", 0.5)),
        regime_confidence=regime_confidence,
        historical_trust=HistoricalTrustProfile(approved=approved_trust),
    )
    approval = "approved_preview" if result.lot_size > 0 else "rejected_preview"
    return {
        "approval": approval,
        "lot_size": round(result.lot_size, 4),
        "risk_amount": round(result.risk_amount, 2),
        "final_risk_percent": round(result.final_risk_percent, 4),
        "reasons": result.reasons,
    }
