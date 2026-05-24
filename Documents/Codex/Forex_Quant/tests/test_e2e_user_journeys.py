"""End-to-end HTTP checks for primary UI + API flows (TestClient; no browser)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _envelope(resp):
    body = resp.json()
    assert {"ok", "data", "message", "errors", "warnings", "timestamp"} <= set(body)
    return body


def test_e2e_strategy_page_and_playbook_aliases_align():
    r1 = client.get("/strategies?regime_id=Q3_M04")
    assert r1.status_code == 200
    assert "Q3_M04" in r1.text
    for url in ("/api/strategies/by-regime/Q3_M04", "/api/strategies/playbook/Q3_M04"):
        body = _envelope(client.get(url))
        assert body["ok"] is True
        assert body["data"]["regime_id"] == "Q3_M04"
        assert len(body["data"]["candidates"]) == 4


def test_e2e_run_signal_on_bundled_cleaned_data():
    resp = client.post("/api/strategies/run-signal", data={"symbol": "EURUSD", "timeframe": "M15", "mode": "research"})
    body = _envelope(resp)
    assert resp.status_code == 200, body
    assert body["ok"] is True
    d = body["data"]
    assert d["symbol"] == "EURUSD"
    assert "regime" in d
    assert len(d["candidates"]) >= 1
    assert "signal_direction" in d["candidates"][0]


def test_e2e_journal_api_same_canonical_store():
    _envelope(client.get("/api/decisions"))
    hist = _envelope(client.get("/api/journal/history?limit=50&action=all"))
    assert hist["ok"] is True
    assert "entries" in hist["data"]
    assert isinstance(hist["data"]["entries"], list)
    # Shape promised for /api/journal/history consumers
    for entry in hist["data"]["entries"][:5]:
        assert "final_action" in entry
        assert "timestamp" in entry


def test_e2e_backtester_research_alias_same_page():
    a = client.get("/research")
    b = client.get("/backtester")
    assert a.status_code == 200 and b.status_code == 200
    assert len(a.text) == len(b.text)
