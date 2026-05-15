from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from systems.mt5_gateway import backend, service


class MockMT5:
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240
    TIMEFRAME_D1 = 1440

    def __init__(self) -> None:
        self.initialized = False

    def initialize(self) -> bool:
        self.initialized = True
        return True

    def shutdown(self) -> bool:
        self.initialized = False
        return True

    def last_error(self):
        return (0, "ok")

    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=False, path="hidden")

    def account_info(self):
        return SimpleNamespace(
            server="Demo-Server",
            currency="USD",
            balance=10000.0,
            equity=10025.0,
            margin=100.0,
            margin_free=9925.0,
            login=123456,
        )

    def symbols_get(self):
        return [
            SimpleNamespace(
                name="MOCKEURUSD",
                description="Mock EURUSD",
                currency_base="EUR",
                currency_profit="USD",
                currency_margin="EUR",
                digits=5,
                point=0.00001,
                trade_mode=4,
                visible=True,
                spread=10,
                select=True,
            )
        ]

    def symbol_info(self, symbol):
        if symbol != "MOCKEURUSD":
            return None
        return SimpleNamespace(name=symbol, visible=True, point=0.00001)

    def symbol_select(self, symbol, selected):
        return True

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        return [
            {"time": 1710000000, "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "tick_volume": 100, "spread": 10, "real_volume": 0},
            {"time": 1710000900, "open": 1.15, "high": 1.22, "low": 1.12, "close": 1.18, "tick_volume": 120, "spread": 11, "real_volume": 0},
        ][:count]

    def symbol_info_tick(self, symbol):
        if symbol != "MOCKEURUSD":
            return None
        return SimpleNamespace(time=1710000900, bid=1.18001, ask=1.18011, last=1.18008)


@pytest.fixture(autouse=True)
def reset_mt5_override():
    service.clear_mt5_module_for_tests()
    yield
    service.clear_mt5_module_for_tests()


def test_app_starts_when_metatrader5_package_missing():
    service.set_mt5_module_for_tests(None)
    client = TestClient(app)
    response = client.get("/api/mt5/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["available"] is False
    assert payload["data"]["connected"] is False


def test_status_connected_response_using_mock():
    service.set_mt5_module_for_tests(MockMT5())
    payload = backend.get_status()
    assert payload["available"] is True
    assert payload["connected"] is True
    assert payload["server"] == "Demo-Server"
    assert payload["currency"] == "USD"
    assert "login" not in (payload["account_info"] or {})


def test_symbols_response_using_mock():
    service.set_mt5_module_for_tests(MockMT5())
    payload = backend.get_symbols()
    assert payload["available"] is True
    assert payload["symbols"][0]["symbol"] == "MOCKEURUSD"


def test_rates_response_returns_normalized_ohlcv_rows():
    service.set_mt5_module_for_tests(MockMT5())
    payload = backend.get_rates("MOCKEURUSD", "M15", 2)
    assert payload["metadata"]["source"] == "mt5"
    assert payload["metadata"]["bars_returned"] == 2
    assert set(payload["rows"][0]) == {"time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"}


def test_invalid_timeframe_rejected():
    service.set_mt5_module_for_tests(MockMT5())
    with pytest.raises(service.MT5GatewayError) as error:
        backend.get_rates("MOCKEURUSD", "M99", 2)
    assert error.value.code == "invalid_timeframe"


def test_bars_limit_enforced():
    service.set_mt5_module_for_tests(MockMT5())
    with pytest.raises(service.MT5GatewayError) as error:
        backend.get_rates("MOCKEURUSD", "M15", 20001)
    assert error.value.code == "bars_limit_exceeded"


def test_tick_response_using_mock():
    service.set_mt5_module_for_tests(MockMT5())
    payload = backend.get_tick("MOCKEURUSD")
    assert payload["symbol"] == "MOCKEURUSD"
    assert payload["spread_price"] > 0
    assert payload["source"] == "mt5"


def test_no_order_send_function_or_route_exists():
    assert not hasattr(backend, "order_send")
    assert not hasattr(service, "order_send")
    paths = {route.path for route in app.routes}
    assert not any("order_send" in path or "order" in path for path in paths if path.startswith("/api/mt5"))


def test_tick_websocket_unavailable_payload_when_mt5_missing():
    service.set_mt5_module_for_tests(None)
    client = TestClient(app)
    with client.websocket_connect("/ws/mt5/tick?symbol=MOCKEURUSD") as websocket:
        payload = websocket.receive_json()
    assert payload["type"] == "tick"
    assert payload["ok"] is False
    assert payload["mt5_connected"] is False
