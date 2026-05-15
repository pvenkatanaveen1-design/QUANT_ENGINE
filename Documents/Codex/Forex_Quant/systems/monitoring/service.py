from __future__ import annotations

from pathlib import Path

from core.api_response import timestamp
from core.config_manager import ConfigManager
from systems.monitoring.schemas import SystemHeartbeat


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def system_grid(data_count: int, latest_regime: dict, registry_summary: dict, risk_summary: dict) -> list[SystemHeartbeat]:
    configured = ConfigManager(PROJECT_ROOT).load_yaml("systems/monitoring/config.yaml").get("systems", [])
    built_status = {
        "Data": ("idle" if data_count else "warning", "No cleaned files yet." if not data_count else f"{data_count} cleaned dataset(s)."),
        "MT5 Gateway": ("idle", "MT5 Gateway routes are registered; connection depends on local terminal/package."),
        "Regime": ("idle", f"Latest regime {latest_regime.get('regime_id', 'unknown')}."),
        "Strategy Router": ("idle", f"{registry_summary.get('total', 0)} registered strategy names."),
        "Strategy Templates": ("idle", "Signal template engine is registered; strategy approval remains evidence-gated."),
        "Research/Backtest": ("idle", "Scenario and batch backtests save to analysis cache."),
        "Analysis Cache": ("idle", "DuckDB/SQLite analysis storage is available."),
        "Risk": ("idle", f"Base risk {risk_summary.get('base_risk_per_trade_percent')}%."),
        "Execution": ("disabled", "Execution is disabled. MT5 is off."),
        "Journal": ("idle", "Decision journal is ready for later decisions."),
        "Monitoring": ("idle", "Heart monitor is running."),
    }
    now = timestamp()
    heartbeats: list[SystemHeartbeat] = []
    for item in configured:
        name = item["name"]
        status, message = built_status.get(name, ("not_built", "System not registered yet."))
        heartbeats.append(SystemHeartbeat(name=name, status=status, last_heartbeat=now, last_message=message, page_url=item.get("page_url", "/")))
    return heartbeats
