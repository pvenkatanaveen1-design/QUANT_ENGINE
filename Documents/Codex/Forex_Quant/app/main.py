from __future__ import annotations

import importlib
import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from core.api_response import envelope
from core.config_manager import ConfigManager


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger("quanta.app")


ROUTER_MODULES = [
    ("monitoring", "systems.monitoring.ui", "/"),
    ("mt5_gateway", "systems.mt5_gateway.ui", "/mt5"),
    ("data", "systems.data.ui", "/data"),
    ("regime", "systems.regime.ui", "/regimes"),
    ("strategy_router", "systems.strategy_router.ui", "/strategies"),
    ("research", "systems.research.ui", "/backtester"),
    ("risk", "systems.risk.ui", "/risk"),
    ("journal", "systems.journal.ui", "/decisions"),
    ("settings", "systems.settings.ui", "/settings"),
]


def _placeholder_router(system_name: str, page_url: str, reason: str) -> APIRouter:
    router = APIRouter(tags=[f"{system_name}-disabled"])

    @router.get(page_url)
    def disabled_system() -> dict[str, object]:
        return envelope(False, data=None, message=f"{system_name} UI is not available.", errors=[{"code": "router_unavailable", "detail": reason}])

    return router


def create_app() -> FastAPI:
    app_config = ConfigManager(PROJECT_ROOT).load_yaml("config/app.yaml")
    app = FastAPI(title=app_config.get("app_name", "Quanta Forex Control Center"))
    app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "app" / "static")), name="static")

    for system_name, module_name, page_url in ROUTER_MODULES:
        try:
            module = importlib.import_module(module_name)
            app.include_router(module.router)
        except Exception as exc:
            LOGGER.warning("Could not register %s router: %s", system_name, exc)
            app.include_router(_placeholder_router(system_name, page_url, str(exc)))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "live_trading": "disabled"}

    return app


app = create_app()
