from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config_manager import ConfigManager
from systems.data.backend import get_dataset_status, get_market_options
from systems.monitoring.service import system_grid
from systems.regime.backend import latest_regime_as_dict
from systems.risk.backend import get_risk_summary
from systems.strategy_router.backend import get_registry_summary


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def system_status() -> dict[str, Any]:
    config = ConfigManager(PROJECT_ROOT).load_yaml("config/app.yaml")
    options = get_market_options()
    symbol_items = (options.get("symbols") or {}).get("symbols") or []
    symbol = str(symbol_items[0]["symbol"]) if symbol_items else ""
    timeframe = str(config.get("default_timeframe", "M15"))
    data = get_dataset_status()
    latest_regime = latest_regime_as_dict(symbol, timeframe) if symbol else {
        "base_regime": "Q4",
        "modifier": "M01",
        "regime_id": "Q4_M01",
        "confidence": 0.0,
        "tradable": False,
        "risk_posture": "mt5_unavailable",
        "reasons": [{"code": "mt5_unavailable", "message": "MT5 symbol list is unavailable.", "severity": "warning"}],
        "features": {},
    }
    risk = get_risk_summary()
    strategy_registry = get_registry_summary()
    return {
        "app_name": config.get("app_name"),
        "environment": config.get("environment"),
        "default_symbol": symbol,
        "default_timeframe": timeframe,
        "live_trading_enabled": bool(config.get("live_trading_enabled", False)),
        "paper_trading_enabled": bool(config.get("paper_trading_enabled", False)),
        "execution_mode": "disabled",
        "kill_switch_status": "clear" if not risk.get("manual_kill_switch") else "manual_kill",
        "data": data,
        "latest_regime": latest_regime,
        "risk": risk,
        "strategy_registry": strategy_registry,
        "systems": [item.__dict__ for item in system_grid(data.get("count", 0), latest_regime, strategy_registry, risk)],
    }
