from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.config_manager import ConfigManager
from systems.data.service import load_cleaned_rows
from systems.regime import service


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def detect_latest_regime(symbol: str = "EURUSD", timeframe: str = "M15") -> Any:
    rows = load_cleaned_rows(symbol, timeframe)
    return service.detect_regime_for_rows(rows, symbol=symbol, timeframe=timeframe)


def detect_regime_for_dataframe(dataframe: Any, symbol: str = "UNKNOWN", timeframe: str = "UNKNOWN") -> Any:
    rows = service.dataframe_to_rows(dataframe)
    return service.detect_regime_for_rows(rows, symbol=symbol, timeframe=timeframe)


def calculate_feature_snapshot(dataframe: Any) -> Any:
    rows = service.dataframe_to_rows(dataframe)
    return service.calculate_feature_snapshot(rows)


def explain_regime(regime_id: str) -> dict[str, Any]:
    config = ConfigManager(PROJECT_ROOT).load_yaml("config/regimes.yaml")
    base, _, modifier = regime_id.partition("_")
    return {
        "regime_id": regime_id,
        "base": config.get("base_regimes", {}).get(base, {}),
        "modifier": config.get("modifiers", {}).get(modifier, {}),
    }


def latest_regime_as_dict(symbol: str = "EURUSD", timeframe: str = "M15") -> dict[str, Any]:
    try:
        result = detect_latest_regime(symbol, timeframe)
        return asdict(result)
    except Exception as exc:
        return {
            "base_regime": "Q4",
            "modifier": "M01",
            "regime_id": "Q4_M01",
            "confidence": 0.0,
            "tradable": False,
            "risk_posture": "missing_data",
            "reasons": [{"code": "missing_data", "message": str(exc), "severity": "warning"}],
            "features": {},
        }

