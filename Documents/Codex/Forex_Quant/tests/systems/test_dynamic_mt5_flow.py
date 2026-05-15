from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from systems.data import backend as data_backend
from systems.data import service as data_service
from systems.mt5_gateway import service as mt5_service
from systems.regime import backend as regime_backend
from systems.regime import service as regime_service
from systems.research import service as research_service
from systems.strategy import signals as strategy_signals
from systems.strategy_router import backend as strategy_backend


class DynamicMockMT5:
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240
    TIMEFRAME_D1 = 1440

    def initialize(self, **kwargs):
        return True

    def shutdown(self):
        return True

    def last_error(self):
        return (0, "ok")

    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=False)

    def account_info(self):
        return SimpleNamespace(server="Demo", currency="USD", balance=10000.0, equity=10010.0, margin=0.0, margin_free=10010.0)

    def symbols_get(self):
        return [
            SimpleNamespace(name="EURUSD", description="Euro vs Dollar", path="Forex\\Majors", currency_base="EUR", currency_profit="USD", currency_margin="EUR", digits=5, point=0.00001, trade_mode=4, visible=True, spread=2, select=True),
            SimpleNamespace(name="GBPUSD", description="Pound vs Dollar", path="Forex\\Majors", currency_base="GBP", currency_profit="USD", currency_margin="GBP", digits=5, point=0.00001, trade_mode=4, visible=True, spread=3, select=True),
        ]

    def symbol_info(self, symbol):
        if symbol not in {"EURUSD", "GBPUSD"}:
            return None
        return SimpleNamespace(name=symbol, visible=True, point=0.00001)

    def symbol_select(self, symbol, selected):
        return True

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        base_time = datetime(2026, 5, 7, tzinfo=timezone.utc)
        price = 1.1000
        rows = []
        for index in range(count):
            price += 0.00012
            rows.append(
                {
                    "time": int((base_time + timedelta(minutes=15 * index)).timestamp()),
                    "open": price - 0.00004,
                    "high": price + 0.00025,
                    "low": price - 0.00018,
                    "close": price,
                    "tick_volume": 100 + index,
                    "spread": 2,
                    "real_volume": 0,
                }
            )
        return rows

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(time=1778731200, bid=1.12345, ask=1.12357, last=1.1235)


@pytest.fixture(autouse=True)
def reset_mt5_override():
    mt5_service.set_mt5_module_for_tests(DynamicMockMT5())
    yield
    mt5_service.clear_mt5_module_for_tests()


def _synthetic_rows(count=160):
    base_time = datetime(2026, 5, 7, tzinfo=timezone.utc)
    price = 1.1000
    rows = []
    for index in range(count):
        price += 0.00015
        rows.append(
            {
                "time": base_time + timedelta(minutes=15 * index),
                "open": price - 0.00005,
                "high": price + 0.00025,
                "low": price - 0.00015,
                "close": price,
                "tick_volume": 100,
                "spread": 2,
            }
        )
    return rows


def test_data_tab_fetches_and_cleans_mocked_mt5_bars():
    result = data_backend.fetch_mt5_bars("EURUSD", "M15", bars=120)
    assert result.source_path == "mt5_demo"
    assert result.rows_out == 120
    assert result.metadata["safe_for_regime_testing"] is True


def test_data_options_and_template_use_backend_symbols():
    client = TestClient(app)
    response = client.get("/data")
    assert response.status_code == 200
    assert "EURUSD" in response.text
    template = (data_service.PROJECT_ROOT / "systems/data/templates/data.html").read_text(encoding="utf-8")
    assert '["EURUSD"' not in template


def test_data_live_websocket_payload_shape():
    client = TestClient(app)
    with client.websocket_connect("/ws/data/live?symbol=EURUSD") as websocket:
        payload = websocket.receive_json()
    assert payload["type"] == "tick"
    assert payload["symbol"] == "EURUSD"
    assert payload["mt5_connected"] is True


def test_one_week_regime_engine_generates_transitions_and_counts():
    rows = _synthetic_rows()
    snapshot = regime_service.analyze_regime_window(rows, symbol="EURUSD", timeframe="M15")
    assert snapshot["current_regime"]["regime_id"]
    assert snapshot["bars_by_quadrant"]
    assert "regime_transition_table" in snapshot
    assert "institutional_summary" in snapshot
    assert "institutional_trap_score" in snapshot["current_regime"]["features"]["extra"]


def test_regime_backend_uses_mt5_data_for_one_week_snapshot():
    snapshot = regime_backend.run_one_week_test(symbol="EURUSD", timeframe="M15", bars=140)
    assert snapshot["source"] == "mt5_demo"
    assert snapshot["current_regime"]["regime_id"]
    assert len(snapshot["strategy_playbook"]["candidates"]) == 4


def test_full_regime_scan_returns_all_52_rows_and_current_once():
    snapshot = regime_backend.run_regime_scan(symbol="EURUSD", timeframe="M15", bars=140)
    table = snapshot["regime_scan_table"]
    assert len(table) == 52
    assert sum(1 for row in table if row["status"] == "current") == 1
    assert snapshot["active_duration_minutes"] >= 15
    assert "avg_minutes_between_changes" in snapshot["change_stats"]


def test_trade_state_returns_four_strategies_and_no_live_orders():
    state = regime_backend.trade_state_for_regime("EURUSD", "M15", "Q1_M01", bars=140)
    trade_state = state["trade_state"]
    assert len(state["strategy_playbook"]["candidates"]) == 4
    assert state["strategy_playbook"]["research_model"]["expected_ev_r"] > 0
    assert state["strategy_playbook"]["candidates"][0]["research_spec"]["scenario_executable"] is True
    assert trade_state["proposed_trade_context"]["live_trading_enabled"] is False
    assert trade_state["proposed_trade_context"]["real_order_enabled"] is False
    assert "current_market_values" in trade_state
    assert "microstructure_values" in trade_state


def test_regime_scan_api_links_work():
    client = TestClient(app)
    response = client.get("/api/regimes/scan?symbol=EURUSD&timeframe=M15&bars=140")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert len(payload["data"]["regime_scan_table"]) == 52

    current = client.get("/api/regimes/current?symbol=EURUSD&timeframe=M15")
    assert current.status_code == 200
    assert current.json()["data"]["current_regime"]["regime_id"]

    trade_state = client.get("/api/regimes/Q1_M01/trade-state?symbol=EURUSD&timeframe=M15&bars=140")
    assert trade_state.status_code == 200
    assert len(trade_state.json()["data"]["strategy_playbook"]["candidates"]) == 4


def test_scenario_blocks_non_executable_strategy(monkeypatch):
    monkeypatch.setattr(research_service, "_find_strategy", lambda strategy_id: {"id": strategy_id, "name": "Manual idea", "family": "general"})
    result = research_service.run_scenario("EURUSD", "M15", "Q1_M01", "X_MANUAL", source="mt5_demo")
    assert result["blocked"] is True
    assert "logic not implemented" in result["reason"]


def test_scenario_produces_estimate_for_synthetic_trend(monkeypatch):
    monkeypatch.setattr(research_service, "_find_strategy", lambda strategy_id: {"id": strategy_id, "name": "EMA pullback", "family": "trend_momentum"})
    result = research_service.run_scenario(
        "EURUSD",
        "M15",
        "Q1_M01",
        "X_EMA",
        source="mt5_demo",
        regime_scope="all_observed",
        killzone_enabled=False,
        spread_filter_enabled=False,
        save_result=False,
    )
    assert result["blocked"] is False
    assert result["label"] == "scenario estimate"
    assert result["executed_simulated_trades"] > 0
    assert result["target_r_multiple"] >= 1.0
    assert "research_model" in result
    assert "strategy_research" in result
    assert "return_percent" in result
    assert "failure_events" in result
    assert "equity_curve" in result


def test_all_208_strategies_have_signal_template_mapping():
    registry = strategy_backend.get_registry()
    templates = {strategy_signals.template_for_strategy(item) for item in registry}
    assert len(registry) == 208
    assert "ema_pullback" in templates
    assert "sweep_reclaim" in templates
    assert "defensive_guard" in templates
    assert all(strategy_signals.template_for_strategy(item) for item in registry)


def test_regime_live_websocket_payload_shape():
    client = TestClient(app)
    with client.websocket_connect("/ws/regime/live?symbol=EURUSD&tf_minutes=15") as websocket:
        payload = websocket.receive_json()
    assert payload["type"] == "regime"
    assert payload["symbol"] == "EURUSD"
    assert "risk_state" in payload
