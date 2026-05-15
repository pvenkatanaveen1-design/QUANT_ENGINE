from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_base_page_renders():
    response = client.get("/")
    assert response.status_code == 200
    assert "Quanta Forex" in response.text
    assert "Live trading disabled" in response.text


def test_static_files_mount():
    response = client.get("/static/css/app.css")
    assert response.status_code == 200
    assert "status-pill" in response.text


def test_main_pages_do_not_crash_without_live_data():
    for path in [
        "/monitor",
        "/workflow",
        "/project-phases",
        "/data",
        "/regimes",
        "/strategies",
        "/priority-setups",
        "/strategy-gate",
        "/research",
        "/backtester",
        "/analysis",
        "/analytics",
        "/evaluation-metrics",
        "/risk",
        "/position-sizing",
        "/journal",
        "/decisions",
        "/settings",
        "/testing-standard",
        "/config-reference",
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
