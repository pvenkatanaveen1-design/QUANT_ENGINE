from fastapi.testclient import TestClient
import pandas as pd

from backend.app import app
from backend.backtest_engine import _apply_regime_hysteresis, _apply_research_mode_preset, _mae_mfe_analysis, _mae_mfe_for_trade
from backend.database import save_backtest_result, save_candles
from backend.institutional_data_engine import evaluate_institutional_data_quality


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["order_execution"] is False


def test_favorites_endpoint_round_trips():
    client = TestClient(app)
    payload = {"item_type": "validation", "item_id": "pytest-favorite-validation", "is_favorite": True}

    response = client.post("/api/favorites", json=payload)
    assert response.status_code == 200
    assert response.json()["is_favorite"] is True

    listed = client.get("/api/favorites", params={"item_type": "validation"})
    assert listed.status_code == 200
    assert any(row["item_id"] == payload["item_id"] for row in listed.json()["favorites"])

    response = client.post("/api/favorites", json={**payload, "is_favorite": False})
    assert response.status_code == 200
    assert response.json()["is_favorite"] is False

    listed = client.get("/api/favorites", params={"item_type": "validation"})
    assert listed.status_code == 200
    assert all(row["item_id"] != payload["item_id"] for row in listed.json()["favorites"])


def test_mode_presets_reference_endpoint_exposes_three_modes():
    client = TestClient(app)
    response = client.get("/api/reference/mode-presets", params={"name": "Final Approval"})
    assert response.status_code == 200
    body = response.json()
    assert body["default_mode_preset"] == "Strict Validation"
    assert body["mode_presets"] == ["Discovery", "Strict Validation", "Final Approval"]
    assert body["resolved"]["selected"] == "Final Approval"
    assert body["resolved"]["preset"]["mt5_tester_model"] == "every_tick_real_ticks"
    assert body["resolved"]["preset"]["min_alpha_score"] == 8


def test_mode_preset_merges_backend_defaults_without_overriding_manual_values():
    payload = {
        "research_mode_preset": "Final Approval",
        "symbol": "EURUSD",
        "timeframe": "M15",
        "start_date": "2026-01-01",
        "end_date": "2026-01-10",
        "filters": {"min_alpha_score": 9},
        "pattern_engine": {},
        "mt5_backtest": {},
    }
    merged = _apply_research_mode_preset(payload)
    assert merged["research_mode_preset"] == "Final Approval"
    assert merged["filters"]["min_alpha_score"] == 9
    assert merged["filters"]["max_spread_percentile"] == 65
    assert merged["filters"]["strict_regime_max_failed_conditions"] == 0
    assert merged["pattern_engine"]["pattern_score_mode"] == "hard_minimum"
    assert merged["mt5_backtest"]["test_model"] == "every_tick_real_ticks"
    assert merged["mt5_backtest"]["execution_quality"] == "strict_final_validation"
    assert merged["_resolved_mode_preset"]["selected"] == "Final Approval"


def test_mae_mfe_for_long_trade_measures_stop_pressure_and_favorable_path():
    frame = pd.DataFrame(
        {
            "high": [1.1000, 1.1010, 1.1030],
            "low": [1.1000, 1.0985, 1.1005],
        }
    )
    signal = {"direction": "long", "entry": 1.1000, "sl": 1.0990, "tp": 1.1020, "risk_distance": 0.0010}

    result = _mae_mfe_for_trade(frame, 0, 2, signal)

    assert result["mae_R"] == 1.5
    assert result["mfe_R"] == 3.0
    assert result["mae_percent_of_stop"] == 150.0
    assert result["bars_held"] == 2


def test_mae_mfe_analysis_flags_tight_stops_when_winners_nearly_stop_first():
    trades = [
        {
            "regime_id": "R01",
            "regime_name": "Clean Bullish Trend",
            "strategy_id": "T1",
            "strategy_name": "EMA20 Pullback Buy",
            "result_R": 1.5,
            "gross_result_R": 1.6,
            "exit_reason": "Take profit hit.",
            "mae_R": 0.9,
            "mfe_R": 2.0,
        }
        for _ in range(20)
    ]

    result = _mae_mfe_analysis(trades)

    assert result["summary"]["decision"] == "STOP TOO TIGHT REVIEW"
    assert result["by_regime"][0]["regime_id"] == "R01"
    assert result["by_strategy"][0]["strategy_id"] == "T1"
    assert result["by_regime_strategy"][0]["regime_strategy"] == "R01_T1"


def test_institutional_data_quality_marks_mt5_candles_as_retail_proxy():
    candles = pd.DataFrame(
        {
            "open": [1.1, 1.2],
            "high": [1.11, 1.21],
            "low": [1.09, 1.19],
            "close": [1.105, 1.205],
            "tick_volume": [100, 120],
            "spread": [10, 12],
            "real_volume": [0, 0],
        }
    )
    features = pd.DataFrame({"data_quality_bad_data_flag": [0, 0], "data_quality_warmup_flag": [0, 0]})

    result = evaluate_institutional_data_quality(candles, features, [], {"data_source_controls": {"data_source": "mt5_retail_candles"}})

    assert result["data_grade"] == "RETAIL_PROXY_RESEARCH"
    assert result["institutional_order_flow_available"] is False
    assert any("No true institutional order-flow" in item for item in result["limitations"])


def test_institutional_data_quality_accepts_declared_l2_order_flow_source():
    candles = pd.DataFrame(
        {
            "open": [1.1, 1.2],
            "high": [1.11, 1.21],
            "low": [1.09, 1.19],
            "close": [1.105, 1.205],
            "tick_volume": [100, 120],
            "spread": [10, 12],
            "real_volume": [1000, 1200],
        }
    )
    features = pd.DataFrame({"data_quality_bad_data_flag": [0, 0], "data_quality_warmup_flag": [0, 0]})

    result = evaluate_institutional_data_quality(
        candles,
        features,
        [{"result_R": 1.2}],
        {"data_source_controls": {"data_source": "ecn_l2_order_book", "has_l2_order_book": True, "has_true_order_flow": True}},
    )

    assert result["data_grade"] == "INSTITUTIONAL_ORDER_FLOW_READY"
    assert result["validation_status"] == "INSTITUTIONAL_RESEARCH_READY"


def test_optimizer_grid_endpoint_returns_ui_ready_no_data_result():
    client = TestClient(app)
    payload = {
        "symbol": "NO_SUCH_SYMBOL",
        "timeframe": "M15",
        "start_date": "2026-01-01",
        "end_date": "2026-01-10",
        "regime_filter": "R01",
        "strategy_filter": "T1",
        "risk_percent": 1.0,
        "rr": 2.0,
        "initial_equity": 100000,
        "max_combinations": 1,
        "min_trades": 1,
        "grid": {
            "regime_filters": ["R01"],
            "strategy_filters": ["T1"],
            "rr_values": [2.0],
            "min_alpha_scores": [5],
            "max_spread_percentiles": [70],
            "killzone_modes": ["score_only"],
            "pattern_score_modes": ["score_only"],
            "min_pattern_scores": [0],
        },
    }
    response = client.post("/api/optimizer/grid", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["combinations_run"] == 1
    assert body["results"][0]["status"] == "NO_DATA"
    assert body["results"][0]["regime_filter"] == "R01"
    assert body["results"][0]["strategy_filter"] == "T1"


def test_monte_carlo_endpoint_returns_ui_ready_no_data_result():
    client = TestClient(app)
    payload = {
        "symbol": "NO_SUCH_SYMBOL",
        "timeframe": "M15",
        "start_date": "2026-01-01",
        "end_date": "2026-01-10",
        "regime_filter": "R01",
        "strategy_filter": "T1",
        "risk_percent": 1.0,
        "rr": 2.0,
        "initial_equity": 100000,
        "simulations": 10,
        "sample_mode": "bootstrap",
        "seed": 42,
        "min_trades": 1,
        "max_total_drawdown_percent": 10,
        "max_losing_streak_limit": 5,
    }
    response = client.post("/api/monte-carlo/run", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["status"] == "NO_DATA"
    assert body["summary"]["source_trades"] == 0
    assert body["equity_fan"] == []
    assert body["validation_saved"] is True
    assert body["validation_run_id"]

    saved = client.get(f"/api/validation/runs/{body['validation_run_id']}")
    assert saved.status_code == 200
    saved_body = saved.json()
    assert saved_body["validation_type"] == "monte_carlo"
    assert saved_body["status"] == "NO_DATA"
    assert saved_body["summary"]["source_trades"] == 0


def test_validation_cockpit_endpoint_returns_scorecard_for_no_data_result():
    client = TestClient(app)
    payload = {
        "payload": {
            "symbol": "NO_SUCH_SYMBOL",
            "timeframe": "M15",
            "start_date": "2026-01-01",
            "end_date": "2026-01-10",
            "regime_filter": "R01",
            "strategy_filter": "T1",
            "risk_percent": 1.0,
            "rr": 2.0,
            "initial_equity": 100000,
        },
        "run_backtest": True,
        "run_oos": False,
        "run_walk_forward": False,
        "run_monte_carlo": True,
        "run_portfolio": False,
        "require_mt5_comparison": False,
        "monte_carlo": {"simulations": 10, "min_trades": 1},
        "thresholds": {"min_backtest_trades": 1},
    }
    response = client.post("/api/validation/cockpit", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["status"] in {"VALIDATION_REJECTED", "VALIDATION_WATCHLIST", "RESEARCH_ONLY"}
    assert body["summary"]["validation_score"] >= 0
    assert len(body["scorecard"]) >= 10
    assert body["failed_required"]


def test_portfolio_backtest_endpoint_returns_ui_ready_no_data_result():
    client = TestClient(app)
    payload = {
        "symbols": ["NO_SUCH_A", "NO_SUCH_B"],
        "timeframes": ["M15", "H1"],
        "symbol": "NO_SUCH_A",
        "timeframe": "M15",
        "start_date": "2026-01-01",
        "end_date": "2026-01-10",
        "regime_filter": "ALL",
        "strategy_filter": "ALL",
        "risk_percent": 1.0,
        "rr": 2.0,
        "initial_equity": 100000,
        "max_legs": 4,
    }
    response = client.post("/api/portfolio/backtest", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["status"] == "NO_DATA"
    assert body["summary"]["legs_requested"] == 4
    assert body["summary"]["legs_no_data"] == 4
    assert body["summary"]["portfolio_risk_status"] == "NO_TRADES"
    assert body["risk_diagnostics"]["status"] == "NO_TRADES"
    assert body["risk_diagnostics"]["checks"][0]["check"] == "portfolio_has_trades"
    assert len(body["symbol_timeframe_matrix"]) == 4
    assert body["symbol_performance"] == []


def test_macro_evidence_endpoint_resolves_macro_biases():
    client = TestClient(app)
    response = client.post(
        "/api/macro/evidence",
        json={
            "usd_bias": "NEUTRAL",
            "risk_sentiment": "NEUTRAL",
            "cb_divergence": "NEUTRAL",
            "macro_evidence": {
                "mode": "evidence",
                "dxy_change_percent": 0.35,
                "usd_basket_change_percent": 0.25,
                "fed_rate_expectation_change_bp": 6,
                "spx_change_percent": -0.7,
                "vix_change_percent": 5,
                "base_rate_expectation_change_bp": 12,
                "quote_rate_expectation_change_bp": 0,
                "high_impact_news": False,
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "evidence"
    assert body["usd_bias"] == "USD_BULLISH"
    assert body["risk_sentiment"] == "RISK_OFF"
    assert body["cb_divergence"] == "BULLISH_BASE"
    assert body["news_flag"] is False
    assert body["confidence"]["usd_bias"] > 0
    assert body["reasons"]
    assert body["activation_allowed"]["R25"] is True


def test_macro_import_csv_and_database_evidence_endpoint():
    client = TestClient(app)
    csv_text = (
        "timestamp,symbol,dxy_change_percent,usd_basket_change_percent,us_yield_change_bp,"
        "fed_rate_expectation_change_bp,spx_change_percent,vix_change_percent,gold_change_percent,"
        "base_rate_expectation_change_bp,quote_rate_expectation_change_bp,high_impact_news,minutes_to_news,minutes_since_news\n"
        "2026-01-03T12:00:00Z,EURUSD,0.35,0.25,6,6,-0.7,5,0.8,12,0,false,9999,9999\n"
    )
    import_response = client.post("/api/macro/import-csv", json={"source": "pytest_macro", "csv_text": csv_text})
    assert import_response.status_code == 200
    imported = import_response.json()
    assert imported["saved"] == 1
    assert imported["latest"]["resolved"]["activation_allowed"]["R25"] is True

    evidence_response = client.post(
        "/api/macro/evidence",
        json={
            "usd_bias": "NEUTRAL",
            "risk_sentiment": "NEUTRAL",
            "cb_divergence": "NEUTRAL",
            "macro_evidence": {"mode": "database", "symbol": "EURUSD", "as_of": "2026-01-04"},
        },
    )
    assert evidence_response.status_code == 200
    evidence = evidence_response.json()
    assert evidence["source"] == "macro_data"
    assert evidence["usd_bias"] == "USD_BULLISH"
    assert evidence["activation_allowed"]["R25"] is True


def test_macro_diagnostics_explains_activation_and_missing_inputs():
    client = TestClient(app)
    csv_text = (
        "timestamp,symbol,dxy_change_percent,usd_basket_change_percent,us_yield_change_bp,"
        "fed_rate_expectation_change_bp,spx_change_percent,vix_change_percent,gold_change_percent,"
        "base_rate_expectation_change_bp,quote_rate_expectation_change_bp,cb_divergence_bp,high_impact_news,minutes_to_news,minutes_since_news\n"
        "2026-02-03T12:00:00Z,MCRUSD,0.40,0.30,7,8,-0.8,6,0.7,30,0,30,false,9999,9999\n"
    )
    import_response = client.post("/api/macro/import-csv", json={"source": "pytest_macro_diag", "csv_text": csv_text})
    assert import_response.status_code == 200

    response = client.get("/api/macro/diagnostics?symbol=MCRUSD&as_of=2026-02-04&limit=10")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "EVIDENCE_READY"
    assert body["pipeline_ready"] is True
    assert body["history_count"] >= 1
    assert body["input_coverage"]["groups"]["usd"]["available_count"] >= 2
    activation = {row["regime_id"]: row for row in body["activation_table"]}
    assert activation["R25"]["allowed"] is True
    assert activation["R29"]["allowed"] is True
    assert activation["R26"]["allowed"] is False
    assert body["latest_row"]["symbol"] == "MCRUSD"


def test_macro_import_feed_endpoint_accepts_news_json():
    client = TestClient(app)
    response = client.post(
        "/api/macro/import-feed",
        json={
            "source": "pytest_calendar",
            "feed_type": "news",
            "feed_format": "json",
            "feed_text": '[{"timestamp":"2026-01-05T13:30:00Z","currency":"USD","event":"NFP","impact":"High","minutes_to_news":15}]',
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["saved"] == 1
    assert body["latest"]["symbol"] == "USD"
    assert body["latest"]["scope"] == "NEWS"
    assert body["latest"]["resolved"]["news_flag"] is True


def test_cross_pair_import_endpoint_builds_evidence_from_saved_candles():
    client = TestClient(app)
    candles = [
        {"timestamp": "2026-01-01T00:00:00Z", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "tick_volume": 1, "spread": 1, "real_volume": 0},
        {"timestamp": "2026-01-02T00:00:00Z", "open": 1.0, "high": 1.1, "low": 1.0, "close": 1.1, "tick_volume": 1, "spread": 1, "real_volume": 0},
    ]
    save_candles("PYTUSD", "M15", candles)
    save_candles("USDPYT", "M15", candles)
    response = client.post(
        "/api/macro/cross-pair/import",
        json={
            "symbol": "EURUSD",
            "timeframe": "M15",
            "start_date": "2026-01-01",
            "end_date": "2026-01-03",
            "symbols": ["PYTUSD", "USDPYT"],
            "source": "pytest_cross_pair",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["saved"] == 1
    assert body["cross_pair_summary"]["symbols_used"] == 2
    assert len(body["cross_pair_components"]) == 2


def test_mt5_report_import_endpoint_parses_csv_report():
    client = TestClient(app)
    payload = {
        "file_name": "sample_real_ticks.csv",
        "test_model": "every_tick_real_ticks",
        "symbol": "EURUSD",
        "timeframe": "M15",
        "initial_equity": 100000,
        "risk_percent": 1.0,
        "report_text": (
            "Time,Symbol,Type,Volume,Price,Profit,Balance,Comment\n"
            "2026-01-02 10:15,EURUSD,buy,0.10,1.10000,120.50,100120.50,T1\n"
            "2026-01-02 11:00,EURUSD,sell,0.10,1.09800,-60.25,100060.25,T1\n"
        ),
    }
    response = client.post("/api/mt5/report/import", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["test_model"] == "every_tick_real_ticks"
    assert body["summary"]["trade_count"] == 2
    assert body["summary"]["net_profit"] == 60.25
    assert body["model_comparison_row"]["status"] == "IMPORTED"
    assert len(body["deals"]) == 2


def test_broker_cost_calibration_uses_imported_mt5_report_costs():
    client = TestClient(app)
    report = (
        "Time,Symbol,Type,Volume,Price,Profit,Balance,Commission,Swap,Initial Risk,Spread,Slippage Points,Comment\n"
        "2026-03-02 10:15,BCALUSD,buy,0.10,1.10000,120,100120,-4,-1,1000,12,1.5,T1\n"
        "2026-03-02 11:00,BCALUSD,sell,0.10,1.09800,-60,100060,-4,-1,1000,15,2.0,T1\n"
    )
    imported = client.post(
        "/api/mt5/report/import",
        json={
            "file_name": "broker_cost_calibration.csv",
            "test_model": "every_tick_real_ticks",
            "symbol": "BCALUSD",
            "timeframe": "M15",
            "initial_equity": 100000,
            "risk_percent": 1.0,
            "report_text": report,
        },
    )
    assert imported.status_code == 200
    response = client.post("/api/cost/calibration", json={"symbol": "BCALUSD", "import_ids": [imported.json()["import_id"]], "limit": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"LOW_SAMPLE_REVIEW", "BROKER_COST_READY"}
    assert body["sample_count"] == 2
    assert body["real_tick_report_count"] >= 1
    assert body["recommended_costs"]["cost_mode"] == "mt5_imported"
    assert body["recommended_costs"]["mt5_imported_cost_R"] > 0
    assert body["summary"]["avg_commission_R"] > 0
    assert body["summary"]["avg_spread_points"] > 0


def test_real_tick_workflow_prepares_three_model_configs_without_launching():
    client = TestClient(app)
    response = client.post(
        "/api/mt5/real-tick-workflow",
        json={
            "payload": {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "start_date": "2026-01-01",
                "end_date": "2026-02-01",
                "regime_filter": "R01",
                "strategy_filter": "T1",
                "risk_percent": 1.0,
                "rr": 2.0,
                "initial_equity": 100000,
            },
            "launch_terminal": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CONFIGS_READY"
    assert body["order_execution"] is False
    assert set(body["tester_runs"]) == {"one_min_ohlc", "every_tick", "every_tick_real_ticks"}
    assert all(run["status"] == "CONFIG_READY_NOT_LAUNCHED" for run in body["tester_runs"].values())
    assert body["model_comparison"] is None
    assert any("generated configs" in warning for warning in body["warnings"])


def test_real_tick_workflow_imports_three_reports_and_compares():
    client = TestClient(app)
    header = "Time,Symbol,Type,Volume,Price,Profit,Balance,Comment\n"
    response = client.post(
        "/api/mt5/real-tick-workflow",
        json={
            "payload": {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "start_date": "2026-01-01",
                "end_date": "2026-02-01",
                "regime_filter": "R01",
                "strategy_filter": "T1",
                "risk_percent": 1.0,
                "rr": 2.0,
                "initial_equity": 100000,
            },
            "launch_terminal": False,
            "reports": {
                "one_min_ohlc": header
                + "2026-01-02 10:15,EURUSD,buy,0.10,1.10000,120,100120,T1\n"
                + "2026-01-02 11:00,EURUSD,sell,0.10,1.09800,-60,100060,T1\n",
                "every_tick": header
                + "2026-01-02 10:15,EURUSD,buy,0.10,1.10000,110,100110,T1\n"
                + "2026-01-02 11:00,EURUSD,sell,0.10,1.09800,-60,100050,T1\n",
                "every_tick_real_ticks": header
                + "2026-01-02 10:15,EURUSD,buy,0.10,1.10000,100,100100,T1\n"
                + "2026-01-02 11:00,EURUSD,sell,0.10,1.09800,-60,100040,T1\n",
            },
            "thresholds": {"min_trades": 2, "min_profit_factor": 1.1, "max_pf_drift": 0.35},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REPORTS_IMPORTED"
    assert body["model_comparison"]["status"] == "MODEL_STABLE_APPROVED_FOR_REVIEW"
    assert len(body["model_comparison"]["rows"]) == 3
    assert body["reports_supplied"]["every_tick_real_ticks"] is True
    assert body["model_comparison"]["decision"]["status"] == "EXECUTION_STABLE_REVIEW_READY"
    assert body["model_comparison"]["decision"]["can_promote_to_final_review"] is True
    assert len(body["model_comparison"]["diagnostics"]["drift_checks"]) == 3
    assert body["model_comparison"]["rows"][2]["model_role"] == "final_execution_validation"


def test_real_tick_workflow_runs_parity_when_python_run_and_real_tick_report_exist():
    client = TestClient(app)
    run_id = "pytest-real-tick-parity-run"
    _save_sample_python_run(run_id)
    packet = client.get(f"/api/backtest/{run_id}/mt5-parity-packet").json()
    response = client.post(
        "/api/mt5/real-tick-workflow",
        json={
            "python_run_id": run_id,
            "payload": {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "start_date": "2026-01-01",
                "end_date": "2026-01-03",
                "regime_filter": "R01",
                "strategy_filter": "T1",
                "risk_percent": 1.0,
                "rr": 2.0,
                "initial_equity": 100000,
            },
            "launch_terminal": False,
            "reports": {
                "one_min_ohlc": packet["expected_signals_csv"],
                "every_tick": packet["expected_signals_csv"],
                "every_tick_real_ticks": packet["expected_signals_csv"],
            },
            "thresholds": {"min_trades": 1, "min_profit_factor": 1.1, "max_pf_drift": 0.35},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REPORTS_IMPORTED"
    assert body["model_comparison"]["status"] == "MODEL_STABLE_APPROVED_FOR_REVIEW"
    assert body["parity_check"]["status"] == "PASS"
    assert any(step["name"] == "Python versus MT5 parity" for step in body["steps"])


def test_mt5_parity_endpoint_passes_matching_python_and_mt5_trades():
    client = TestClient(app)
    trade = {
        "entry_time": "2026-01-02T10:15:00Z",
        "exit_time": "2026-01-02T11:00:00Z",
        "regime_id": "R01",
        "regime_name": "Clean Bullish Trend",
        "strategy_id": "T1",
        "strategy_name": "EMA20 Pullback Buy",
        "direction": "long",
        "entry": 1.10000,
        "sl": 1.09900,
        "tp": 1.10200,
        "exit_price": 1.10200,
        "result_R": 1.95,
        "profit": 1950.0,
    }
    response = client.post(
        "/api/mt5/parity/check",
        json={
            "payload": {"symbol": "EURUSD", "timeframe": "M15", "regime_filter": "R01", "strategy_filter": "T1"},
            "python_trades": [trade],
            "mt5_trades": [{**trade, "comment": "R01|T1|A8|P3"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PASS"
    assert body["summary"]["python_trade_count"] == 1
    assert body["summary"]["mt5_trade_count"] == 1
    assert body["summary"]["mismatch_count"] == 0


def test_mt5_parity_endpoint_fails_on_direction_mismatch():
    client = TestClient(app)
    python_trade = {
        "entry_time": "2026-01-02T10:15:00Z",
        "regime_id": "R01",
        "strategy_id": "T1",
        "direction": "long",
        "entry": 1.10000,
        "sl": 1.09900,
        "tp": 1.10200,
        "result_R": 1.95,
        "profit": 1950.0,
    }
    mt5_trade = {**python_trade, "direction": "short", "comment": "R01|T1|A8|P3"}
    response = client.post(
        "/api/mt5/parity/check",
        json={
            "payload": {"symbol": "EURUSD", "timeframe": "M15", "regime_filter": "R01", "strategy_filter": "T1"},
            "python_trades": [python_trade],
            "mt5_trades": [mt5_trade],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"WARN", "FAIL"}
    assert body["summary"]["mismatch_count"] == 1
    assert body["mismatches"][0]["failed_fields"][0]["field"] == "direction"


def _save_sample_python_run(run_id: str) -> None:
    trade = {
        "symbol": "EURUSD",
        "timeframe": "M15",
        "entry_time": "2026-01-02T10:15:00Z",
        "exit_time": "2026-01-02T11:00:00Z",
        "regime_id": "R01",
        "regime_name": "Clean Bullish Trend",
        "modifiers": ["M12"],
        "strategy_id": "T1",
        "strategy_name": "EMA20 Pullback Buy",
        "direction": "long",
        "entry": 1.10000,
        "sl": 1.09900,
        "tp": 1.10200,
        "exit_price": 1.10200,
        "initial_risk": 1000,
        "result_R": 1.95,
        "profit": 1950.0,
        "alpha_score": 8,
        "alpha_components": {"direction": 3},
        "alpha_reason": "Sample parity trade.",
        "patterns_detected": [],
        "pattern_score": 0,
        "pattern_decision": "OFF",
        "pattern_summary": "",
        "final_score": 8,
        "setup_context": {},
        "entry_reason": "Sample entry.",
        "exit_reason": "Sample exit.",
    }
    save_backtest_result(
        {
            "run_id": run_id,
            "created_at": "2026-01-02T12:00:00Z",
            "request": {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "start_date": "2026-01-01",
                "end_date": "2026-01-03",
                "regime_filter": "R01",
                "strategy_filter": "T1",
                "risk_percent": 1.0,
                "rr": 2.0,
                "initial_equity": 100000,
            },
            "summary": {"total_trades": 1, "profit_factor": 999, "expectancy_R": 1.95},
            "regime_performance": [],
            "strategy_performance": [],
            "combination_performance": [],
            "unique_combination_performance": [],
            "modifier_impact": [],
            "session_performance": [],
            "monthly_performance": [],
            "pattern_performance": [],
            "pattern_summary": {},
            "mt5_model_comparison": [],
            "data_health": {},
            "feature_summary": {},
            "regime_confidence": [],
            "skipped_setups": [],
            "equity_curve": [],
            "drawdown_curve": [],
            "approval_checklist": [],
            "explanation": {"what_worked": [], "what_failed": [], "warnings": []},
            "trades": [trade],
        }
    )


def test_mt5_parity_packet_and_run_report_match_by_hash():
    client = TestClient(app)
    run_id = "pytest-parity-run"
    _save_sample_python_run(run_id)
    packet_response = client.get(f"/api/backtest/{run_id}/mt5-parity-packet")
    assert packet_response.status_code == 200
    packet = packet_response.json()
    assert packet["expected_trade_count"] == 1
    assert "PYHASH" in packet["expected_signals_csv"]

    response = client.post(
        "/api/mt5/parity/check-run-report",
        json={
            "python_run_id": run_id,
            "test_model": "every_tick_real_ticks",
            "report_text": packet["expected_signals_csv"],
            "tolerances": {"price_tolerance": 0.00001, "time_tolerance_seconds": 60, "result_R_tolerance": 0.05, "profit_tolerance": 1.0},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PASS"
    assert body["summary"]["python_trade_count"] == 1
    assert body["summary"]["mt5_trade_count"] == 1


def test_mt5_parity_completion_proves_keyed_python_mt5_match():
    client = TestClient(app)
    run_id = "pytest-parity-complete-run"
    _save_sample_python_run(run_id)
    packet = client.get(f"/api/backtest/{run_id}/mt5-parity-packet").json()

    response = client.post(
        "/api/mt5/parity/complete",
        json={
            "python_run_id": run_id,
            "report_text": packet["expected_signals_csv"],
            "file_name": "pytest_parity_signal.csv",
            "test_model": "every_tick_real_ticks",
            "prepare_tester_config": True,
            "launch_terminal": False,
            "required_symbol": "EURUSD",
            "required_timeframe": "M15",
            "tolerances": {"price_tolerance": 0.00001, "time_tolerance_seconds": 60, "result_R_tolerance": 0.05, "profit_tolerance": 1.0},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PARITY_PROVEN"
    assert body["institutional_verdict"]["proved"] is True
    assert body["parity_check"]["status"] == "PASS"
    assert all(row["passed"] for row in body["checklist"] if row["check"] != "MT5 config uses Python signal CSV" or body["tester_run"])


def test_mt5_parity_completion_waits_without_mt5_report():
    client = TestClient(app)
    run_id = "pytest-parity-wait-run"
    _save_sample_python_run(run_id)
    response = client.post(
        "/api/mt5/parity/complete",
        json={
            "python_run_id": run_id,
            "prepare_tester_config": True,
            "launch_terminal": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "WAITING_FOR_MT5_REPORT"
    assert body["packet"]["expected_trade_count"] == 1
    assert body["parity_check"] is None
    assert any("PYHASH" in action or "PYIDX" in action for action in body["next_actions"])


def test_mt5_backtest_bridge_keeps_non_tester_execution_disabled_by_default():
    client = TestClient(app)
    response = client.post(
        "/api/mt5/backtest/run",
        json={
            "payload": {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "regime_filter": "R01",
                "strategy_filter": "T1",
            }
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["order_execution"] is False
    assert body["ea_inputs_prepared"]["AllowNonTesterExecution"] is False
    assert body["safety"]["tester_only_default"] is True
    assert body["safety"]["allow_non_tester_execution"] is False


def test_mt5_backtest_bridge_warns_when_non_tester_execution_requested():
    client = TestClient(app)
    response = client.post(
        "/api/mt5/backtest/run",
        json={
            "payload": {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "regime_filter": "R01",
                "strategy_filter": "T1",
                "strategy_execution": {"allow_non_tester_execution": True},
            }
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ea_inputs_prepared"]["AllowNonTesterExecution"] is True
    assert body["safety"]["allow_non_tester_execution"] is True
    assert any("DANGER" in warning for warning in body["safety"]["warnings"])


def test_final_approval_rejects_low_trade_count_even_with_good_metrics():
    client = TestClient(app)
    payload = {
        "payload": {"symbol": "EURUSD", "timeframe": "M15", "regime_filter": "R01", "strategy_filter": "T1"},
        "backtest": {"summary": {"total_trades": 5, "profit_factor": 2.0, "expectancy_R": 0.3, "max_drawdown_R": -1}},
        "out_of_sample": {
            "summary": {"status": "PASS", "stable": True, "performance_retention": 0.8},
            "out_of_sample": {"total_trades": 25, "profit_factor": 1.3},
        },
        "walk_forward": {"summary": {"stable": True, "pass_rate": 0.8, "average_walk_forward_efficiency": 0.7}},
        "monte_carlo": {
            "summary": {"status": "PASS"},
            "risk_of_ruin": {"drawdown_breach_probability": 0.02, "loss_probability": 0.05, "losing_streak_breach_probability": 0.04},
        },
        "mt5_comparison": {
            "status": "MODEL_STABLE_APPROVED_FOR_REVIEW",
            "rows": [{"model": "every_tick_real_ticks", "trade_count": 50, "profit_factor": 1.3, "expectancy_R": 0.1}],
            "stability": {"profit_factor_drift_1m_to_real_ticks": 0.1, "trade_count_drift_pct_1m_to_real_ticks": 0.1, "net_profit_drift_pct_1m_to_real_ticks": -0.1},
        },
    }
    response = client.post("/api/final-approval/review", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "FINAL_REJECTED"
    assert body["anti_overfit_gate"]["status"] == "FAIL"
    assert any(row["check"] == "anti_overfit_min_trades" for row in body["anti_overfit_gate"]["failed_checks"])


def test_optimizer_grid_applies_multiple_test_penalty_to_thresholds():
    client = TestClient(app)
    payload = {
        "symbol": "NO_SUCH_SYMBOL",
        "timeframe": "M15",
        "start_date": "2026-01-01",
        "end_date": "2026-01-10",
        "regime_filter": "R01",
        "strategy_filter": "T1",
        "risk_percent": 1.0,
        "rr": 2.0,
        "initial_equity": 100000,
        "max_combinations": 2,
        "min_trades": 30,
        "min_profit_factor": 1.2,
        "grid": {
            "regime_filters": ["R01", "R02", "R03", "R04", "R05", "R06"],
            "strategy_filters": ["T1", "T2", "T3", "T4", "T5", "T6"],
            "rr_values": [1.5, 2.0],
            "min_alpha_scores": [5, 7],
            "max_spread_percentiles": [65, 70],
        },
    }
    response = client.post("/api/optimizer/grid", json=payload)
    assert response.status_code == 200
    body = response.json()
    penalty = body["summary"]["anti_overfit_penalty"]
    assert penalty["level"] in {"HIGH", "EXTREME"}
    assert body["summary"]["adjusted_min_trades"] > 30
    assert body["summary"]["adjusted_min_profit_factor"] > 1.2


def test_regime_hysteresis_suppresses_one_bar_flickers():
    raw = [
        {"regime_id": "R01", "regime_name": "Clean Bullish Trend", "confidence": 0.82, "conditions_failed": []},
        {"regime_id": "R31", "regime_name": "Transition / Uncertain Regime", "confidence": 0.70, "conditions_failed": []},
        {"regime_id": "R01", "regime_name": "Clean Bullish Trend", "confidence": 0.80, "conditions_failed": []},
        {"regime_id": "R37", "regime_name": "Multi-Timeframe Conflict Trap", "confidence": 0.73, "conditions_failed": []},
        {"regime_id": "R01", "regime_name": "Clean Bullish Trend", "confidence": 0.81, "conditions_failed": []},
    ]
    stable = _apply_regime_hysteresis(raw, {"use_regime_hysteresis": True, "hysteresis_confirm_bars": 3, "hysteresis_confidence_margin": 0.15})
    assert [row["stable_regime_id"] for row in stable] == ["R01", "R01", "R01", "R01", "R01"]
    assert sum(row["regime_hysteresis_applied"] for row in stable) == 2


def test_regime_hysteresis_allows_danger_regime_immediate_override():
    raw = [
        {"regime_id": "R01", "regime_name": "Clean Bullish Trend", "confidence": 0.82, "conditions_failed": []},
        {"regime_id": "R40", "regime_name": "Data Quality / Manual Review Regime", "confidence": 1.0, "conditions_failed": []},
    ]
    stable = _apply_regime_hysteresis(raw, {"use_regime_hysteresis": True, "hysteresis_confirm_bars": 3})
    assert stable[1]["stable_regime_id"] == "R40"
    assert stable[1]["regime_hysteresis_applied"] == 0
    assert "overrode" in stable[1]["regime_hysteresis_reason"]
