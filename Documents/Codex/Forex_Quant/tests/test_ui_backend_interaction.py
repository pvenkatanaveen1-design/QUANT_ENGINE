from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _assert_envelope(response):
    payload = response.json()
    assert {"ok", "data", "message", "warnings", "errors", "timestamp"} <= set(payload)
    return payload


def test_api_routes_use_response_envelope():
    routes = [
        "/api/system/status",
        "/api/health",
        "/api/data/status",
        "/api/regimes/definitions",
        "/api/strategies",
        "/api/risk/rules",
        "/api/risk/kelly-demo",
        "/api/backtests/results",
        "/api/decisions",
        "/api/journal/history",
        "/api/analytics/data",
        "/api/analytics/runs",
        "/api/settings/files",
    ]
    for route in routes:
        response = client.get(route)
        assert response.status_code == 200, route
        assert _assert_envelope(response)["ok"] is True


def test_htmx_partials_return_fragments():
    routes = [
        "/partials/system-summary",
        "/partials/system-grid",
        "/partials/data-files",
        "/partials/data-quality",
        "/partials/latest-regime",
        "/partials/regime-feature-table",
        "/partials/regime-reasons",
        "/partials/regime-playbook",
        "/partials/risk-summary",
        "/partials/funded-rules",
        "/partials/kill-switch",
        "/partials/backtest-status",
        "/partials/backtest-metrics",
        "/partials/regime-heatmap",
        "/partials/decision-log",
        "/partials/decision-detail",
        "/partials/settings-editor",
    ]
    for route in routes:
        response = client.get(route)
        assert response.status_code == 200, route
        assert "<html" not in response.text.lower()


def test_data_load_csv_api_is_disabled_in_runtime():
    response = client.post("/api/data/load-csv", data={"symbol": "EURUSD", "timeframe": "M15"})
    payload = _assert_envelope(response)
    assert response.status_code == 410
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "mt5_only"


def test_strategy_playbook_has_four_slots():
    for url in ("/api/strategies/by-regime/Q1_M01", "/api/strategies/playbook/Q1_M01"):
        response = client.get(url)
        payload = _assert_envelope(response)
        assert response.status_code == 200
        assert len(payload["data"]["candidates"]) == 4


def test_dangerous_live_flags_are_blocked_from_settings_ui():
    response = client.post("/api/settings/app/preview", data={"content": "live_trading_enabled: true\n"})
    payload = _assert_envelope(response)
    assert response.status_code == 400
    assert payload["ok"] is False
    assert "live_trading_enabled" in payload["errors"][0]["detail"]
