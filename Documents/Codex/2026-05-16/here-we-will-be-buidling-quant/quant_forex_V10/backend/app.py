from __future__ import annotations

import math
from urllib.error import URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.backtest_engine import research_mode_presets, resolve_research_mode_preset, run_backtest
from backend.calibration_engine import list_calibration_profiles
from backend.cost_model_engine import calibrate_broker_costs
from backend.experiment_engine import run_ab_experiment
from backend.final_approval_engine import final_approval_review
from backend.monte_carlo_engine import run_monte_carlo
from backend.macro_data_engine import import_cot_evidence, import_cross_pair_evidence, import_macro_csv, import_macro_feed_text, list_macro_evidence, macro_pipeline_diagnostics, resolve_macro_context
from backend.monthly_regime_research_engine import run_monthly_regime_research
from backend.ollama_reviewer import run_ollama_review
from backend.out_of_sample_engine import run_out_of_sample
from backend.optimizer_engine import run_optimizer_grid
from backend.portfolio_engine import run_portfolio_backtest
from backend.validation_cockpit_engine import run_validation_cockpit
from backend.walk_forward_engine import run_walk_forward
from backend.mt5_report_importer import compare_mt5_model_reports, import_mt5_report
from backend.mt5_parity_engine import run_mt5_parity_check
from backend.mt5_parity_completion import run_mt5_parity_completion
from backend.mt5_parity_packet import build_python_parity_packet
from backend.mt5_real_tick_workflow import run_real_tick_workflow
from backend.mt5_tester_runner import run_mt5_strategy_tester
from backend.common.config_loader import load_formulas, load_market_defaults, load_modifiers, load_regimes, load_strategies
from backend.common.engines.explanation_engine import explain_regime_detection
from backend.common.engines.regime_engine import detect_regime
from backend.common.engines.strategy_engine import STRATEGIES
from backend.data_provider_engine import data_source_catalog, fetch_candles_from_selected_source
from backend.common.models.schemas import (
    ApiStructureResponse,
    ABExperimentRequest,
    ABExperimentResponse,
    BacktestRequest,
    BacktestRunResponse,
    BacktestStoredResponse,
    BacktestTradesResponse,
    BrokerCostCalibrationRequest,
    BrokerCostCalibrationResponse,
    CalibrationProfilesResponse,
    CandlesResponse,
    CrossPairEvidenceRequest,
    CotImportRequest,
    DetectLatestRequest,
    DetectLatestResponse,
    FinalApprovalRequest,
    FinalApprovalResponse,
    FeatureCalculateRequest,
    FeatureCalculateResponse,
    FetchCandlesRequest,
    FetchCandlesResponse,
    HealthResponse,
    MT5ConnectResponse,
    MT5ModelComparisonImportRequest,
    MT5ModelComparisonImportResponse,
    MT5ParityRequest,
    MT5ParityCompletionRequest,
    MT5ParityCompletionResponse,
    MT5ParityPacketResponse,
    MT5ParityRunReportRequest,
    MT5ParityResponse,
    MT5RealTickWorkflowRequest,
    MT5RealTickWorkflowResponse,
    MT5ReportImportRequest,
    MT5ReportImportResponse,
    MT5TesterRunRequest,
    MT5TesterRunResponse,
    MonthlyRegimeResearchRequest,
    MonthlyRegimeResearchResponse,
    MacroDiagnosticsResponse,
    MacroEvidenceRequest,
    MacroEvidenceResponse,
    MacroImportCsvRequest,
    MacroImportCsvResponse,
    MacroImportFeedRequest,
    MacroImportUrlRequest,
    MonteCarloRequest,
    MonteCarloResponse,
    OllamaReviewRequest,
    OllamaReviewResponse,
    OptimizerGridRequest,
    OptimizerGridResponse,
    OutOfSampleRequest,
    OutOfSampleResponse,
    PortfolioBacktestRequest,
    PortfolioBacktestResponse,
    ReferenceModifier,
    ReferenceRegime,
    ReferenceStrategy,
    SymbolsResponse,
    WalkForwardRequest,
    WalkForwardResponse,
)
from backend.common.modifiers.modifier_engine import detect_modifiers
from backend.database import (
    init_db,
    list_ab_experiments,
    list_backtest_runs,
    list_favorites,
    list_monthly_regime_sweep_runs,
    list_mt5_report_imports,
    list_research_value_profiles,
    list_validation_runs,
    load_ab_experiment,
    load_backtest,
    load_backtest_trades,
    load_candles,
    load_features,
    load_monthly_regime_sweep_run,
    load_research_value_profile,
    load_validation_run,
    set_favorite,
    save_monthly_regime_sweep_result,
    save_research_value_profile,
    save_validation_result,
)
from backend.feature_cache_engine import feature_cache_status, feature_params, load_or_calculate_features
from backend.mt5.mt5_client import build_mt5_backtest_bridge_response, connect_mt5, get_symbols


app = FastAPI(title="quant_forex_V10 API", version="0.1.0")
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.on_event("startup")
def _startup() -> None:
    init_db()


def _body(model) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, tuple):
        return [_clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _feature_favorite_id(record: dict[str, Any]) -> str:
    symbol = record.get("display_symbol") or record.get("symbol") or ""
    timeframe = record.get("timeframe") or ""
    timestamp = record.get("timestamp") or ""
    data_source = record.get("data_source") or ""
    return "|".join(str(part) for part in [symbol, timeframe, timestamp, data_source])


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found.")
    return FileResponse(index_path)


@app.get("/api/health", response_model=HealthResponse)
def health() -> dict[str, Any]:
    return {"status": "ok", "app": "quant_forex_V10", "scope": "50-regime Tab 1 research API only", "order_execution": False}


@app.post("/api/mt5/connect", response_model=MT5ConnectResponse)
def api_mt5_connect() -> dict[str, Any]:
    return _clean(connect_mt5())


@app.get("/api/mt5/symbols", response_model=SymbolsResponse)
def api_mt5_symbols() -> dict[str, Any]:
    return _clean(get_symbols())


@app.post("/api/mt5/backtest/run")
def api_mt5_backtest_run(request: dict[str, Any]) -> dict[str, Any]:
    return _clean(build_mt5_backtest_bridge_response(request))


@app.post("/api/mt5/tester/run", response_model=MT5TesterRunResponse)
def api_mt5_tester_run(request: MT5TesterRunRequest) -> dict[str, Any]:
    body = _body(request)
    result = run_mt5_strategy_tester(body)
    save_validation_result("mt5_tester", result, body)
    return _clean(result)


@app.post("/api/candles/fetch", response_model=FetchCandlesResponse)
def api_fetch_candles(request: FetchCandlesRequest) -> dict[str, Any]:
    result = fetch_candles_from_selected_source(request.symbol, request.timeframe, request.start_date, request.end_date, request.data_source_controls)
    return _clean(result)


@app.get("/api/candles", response_model=CandlesResponse)
def api_get_candles(
    symbol: str = Query(...),
    timeframe: str = Query(...),
    start_date: str | None = None,
    end_date: str | None = None,
    data_source: str | None = None,
) -> dict[str, Any]:
    df = load_candles(symbol, timeframe, start_date, end_date, data_source=data_source)
    records = df.to_dict(orient="records") if not df.empty else []
    return _clean({"count": len(records), "candles": records})


@app.get("/api/features")
def api_get_features(
    symbol: str = Query(...),
    timeframe: str = Query(...),
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = Query(250, ge=1, le=5000),
    data_source: str | None = None,
) -> dict[str, Any]:
    df = load_features(symbol, timeframe, start_date, end_date, limit, data_source=data_source)
    records = df.to_dict(orient="records") if not df.empty else []
    favorite_feature_ids = {item["item_id"] for item in list_favorites("feature")}
    for record in records:
        favorite_id = _feature_favorite_id(record)
        record["favorite_id"] = favorite_id
        record["is_favorite"] = 1 if favorite_id in favorite_feature_ids else 0
    records.sort(key=lambda item: (int(item.get("is_favorite") or 0), str(item.get("timestamp") or "")), reverse=True)
    return _clean({"count": len(records), "features": records})


@app.get("/api/features/cache-status")
def api_feature_cache_status(
    symbol: str = Query(...),
    timeframe: str = Query(...),
    start_date: str = Query(...),
    end_date: str = Query(...),
    sentiment: str = "NEUTRAL",
    usd_bias: str = "NEUTRAL",
    risk_sentiment: str = "NEUTRAL",
    cb_divergence: str = "NEUTRAL",
    data_source: str | None = None,
) -> dict[str, Any]:
    params = feature_params(
        timeframe=timeframe,
        sentiment=sentiment,
        usd_bias=usd_bias,
        risk_sentiment=risk_sentiment,
        cb_divergence=cb_divergence,
        macro_evidence={"symbol": symbol, "start_date": start_date, "end_date": end_date, "as_of": end_date},
        data_source=data_source,
    )
    return _clean(feature_cache_status(symbol, timeframe, start_date, end_date, params, data_source=data_source))


@app.post("/api/features/calculate", response_model=FeatureCalculateResponse)
def api_calculate_features(request: FeatureCalculateRequest) -> dict[str, Any]:
    macro_evidence = dict(request.macro_evidence or {})
    macro_evidence.setdefault("symbol", request.symbol)
    macro_evidence.setdefault("start_date", request.start_date)
    macro_evidence.setdefault("end_date", request.end_date)
    macro_evidence.setdefault("as_of", request.end_date)
    try:
        _, features, cache_meta = load_or_calculate_features(
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_date=request.start_date,
            end_date=request.end_date,
            sentiment=request.sentiment,
            usd_bias=request.usd_bias,
            risk_sentiment=request.risk_sentiment,
            cb_divergence=request.cb_divergence,
            macro_evidence=macro_evidence,
            data_source_controls=request.data_source_controls,
            use_cache=True,
            persist_cache=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    saved = int(cache_meta.get("saved") or 0)
    latest = features.iloc[-1].to_dict() if not features.empty else {}
    return _clean({"saved": saved, "cached": bool(cache_meta.get("cache_hit")), "cache_status": cache_meta, "latest_features": latest})


@app.get("/api/reference/regimes", response_model=list[ReferenceRegime])
def api_reference_regimes() -> list[dict[str, Any]]:
    return load_regimes()


@app.get("/api/reference/strategies", response_model=list[ReferenceStrategy])
def api_reference_strategies() -> list[dict[str, Any]]:
    return load_strategies()


@app.get("/api/reference/modifiers", response_model=list[ReferenceModifier])
def api_reference_modifiers() -> list[dict[str, Any]]:
    return load_modifiers()


@app.get("/api/reference/formulas")
def api_reference_formulas() -> dict[str, str]:
    return load_formulas()


@app.get("/api/data-sources")
def api_data_sources() -> dict[str, Any]:
    return data_source_catalog()


@app.get("/api/reference/institutional-data")
def api_reference_institutional_data() -> dict[str, Any]:
    return {
        "principle": "MT5 candles are retail-broker OHLC research data, not institutional order-flow.",
        "grades": [
            {"grade": "RETAIL_PROXY_RESEARCH", "meaning": "Usable for hypothesis discovery only; liquidity and order-flow are inferred from OHLC/tick-volume proxies."},
            {"grade": "BROKER_REAL_TICK_VALIDATED", "meaning": "Same setup survived MT5 real-tick tester evidence; acceptable for demo/semi-manual review, not proof of institutional flow."},
            {"grade": "INSTITUTIONAL_ORDER_FLOW_READY", "meaning": "External tick/order-flow/depth data is present and explicitly declared in data-source controls."},
        ],
        "supported_data_sources": [
            "mt5_retail_candles",
            "mt5_every_tick",
            "mt5_real_ticks",
            "dukascopy_ticks",
            "alpha_vantage_fx",
            "twelve_data_fx",
            "polygon_fx",
            "csv_import",
            "cme_fx_futures_proxy",
            "prime_broker_ticks",
            "ecn_l2_order_book",
            "reuters_ebs_tick",
            "bloomberg_bpipe_tick",
            "institutional_order_flow",
        ],
        "data_source_controls": {
            "data_source": "mt5_retail_candles",
            "provider": "MT5 / SQLite",
            "require_real_tick_validation": True,
            "require_institutional_order_flow": False,
            "has_true_order_flow": False,
            "has_l2_order_book": False,
            "has_external_tick_data": False,
        },
        "institutional_import_schema": [
            "timestamp",
            "symbol",
            "bid",
            "ask",
            "last",
            "bid_size",
            "ask_size",
            "aggressor_side",
            "venue",
        ],
    }


@app.get("/api/reference/market")
def api_reference_market() -> dict[str, Any]:
    return load_market_defaults()


@app.get("/api/reference/mode-presets")
def api_reference_mode_presets(name: str | None = None) -> dict[str, Any]:
    payload = research_mode_presets()
    if name:
        payload["resolved"] = resolve_research_mode_preset(name)
    return payload


@app.get("/api/reference/api-structure", response_model=ApiStructureResponse)
def api_reference_api_structure() -> dict[str, Any]:
    return {
        "base_url": "http://127.0.0.1:8000",
        "note": "Port 8000 is the default in run.py. If occupied, run uvicorn on another port and keep the same paths.",
        "endpoints": [
            {
                "method": "GET",
                "path": "/api/health",
                "purpose": "Check API status and confirm no order execution exists.",
                "request_body": None,
                "query_params": None,
                "response_shape": {"status": "ok", "app": "quant_forex_V10", "scope": "...", "order_execution": False},
            },
            {
                "method": "GET",
                "path": "/api/reference/mode-presets",
                "purpose": "Read Discovery, Strict Validation, and Final Approval preset definitions. Optional name query resolves one selected preset.",
                "request_body": None,
                "query_params": {"name": "Final Approval"},
                "response_shape": {"mode_presets": ["Discovery", "Strict Validation", "Final Approval"], "default_mode_preset": "Strict Validation", "research_mode_presets": {}, "resolved": {}},
            },
            {
                "method": "POST",
                "path": "/api/mt5/connect",
                "purpose": "Connect to MT5 in read-only mode.",
                "request_body": None,
                "query_params": None,
                "response_shape": {"connected": True, "account": {}, "read_only": True, "message": "..."},
            },
            {
                "method": "GET",
                "path": "/api/mt5/symbols",
                "purpose": "Read symbol names from MT5.",
                "request_body": None,
                "query_params": None,
                "response_shape": {"symbols": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]},
            },
            {
                "method": "POST",
                "path": "/api/candles/fetch",
                "purpose": "Fetch candles from MT5 and save to SQLite.",
                "request_body": {"symbol": "EURUSD", "timeframe": "M15", "start_date": "2026-01-01", "end_date": "2026-06-01"},
                "query_params": None,
                "response_shape": {"saved": 5000, "symbol": "EURUSD", "timeframe": "M15"},
            },
            {
                "method": "GET",
                "path": "/api/candles",
                "purpose": "Read candles already saved in SQLite.",
                "request_body": None,
                "query_params": {"symbol": "EURUSD", "timeframe": "M15", "start_date": "2026-01-01", "end_date": "2026-06-01"},
                "response_shape": {"count": 1, "candles": [{"timestamp": "...", "open": 1.1, "high": 1.101, "low": 1.099, "close": 1.1005}]},
            },
            {
                "method": "POST",
                "path": "/api/features/calculate",
                "purpose": "Calculate features and save them to SQLite.",
                "request_body": {"symbol": "EURUSD", "timeframe": "M15", "start_date": "2026-01-01", "end_date": "2026-06-01", "sentiment": "NEUTRAL"},
                "query_params": None,
                "response_shape": {"saved": 5000, "latest_features": {"adx": 24.5, "er": 0.32, "session": "London"}},
            },
            {
                "method": "GET",
                "path": "/api/features",
                "purpose": "Read saved feature rows so hidden feature calculations can be audited.",
                "request_body": None,
                "query_params": {"symbol": "EURUSD", "timeframe": "M15", "start_date": "2026-01-01", "end_date": "2026-06-01", "limit": 250},
                "response_shape": {"count": 1, "features": [{"timestamp": "...", "adx": 24.5, "session_vwap": 1.1, "data_quality_reasons": ""}]},
            },
            {
                "method": "POST",
                "path": "/api/regime/detect-latest",
                "purpose": "Detect latest active regime from saved candles.",
                "request_body": {"symbol": "EURUSD", "timeframe": "M15", "sentiment": "NEUTRAL"},
                "query_params": None,
                "response_shape": {"latest_features": {}, "active_regime": {}, "modifiers": {}, "hard_block": False, "allowed_strategies": [], "explanation": "..."},
            },
            {
                "method": "POST",
                "path": "/api/backtest/run",
                "purpose": "Run a 50-regime research backtest.",
                "request_body": {
                    "symbol": "EURUSD",
                    "timeframe": "M15",
                    "start_date": "2026-01-01",
                    "end_date": "2026-06-01",
                    "regime_filter": "ALL",
                    "strategy_filter": "ALL",
                    "risk_percent": 1.0,
                    "rr": 2.0,
                    "initial_equity": 100000,
                    "sentiment": "NEUTRAL",
                    "usd_bias": "NEUTRAL",
                    "risk_sentiment": "NEUTRAL",
                    "cb_divergence": "NEUTRAL",
                    "use_killzone": True,
                    "use_spread_filter": True,
                    "use_sweeps": True,
                    "use_alpha": True,
                    "killzone_mode": "score_only",
                    "spread_filter_mode": "score_only",
                    "alpha_mode": "hard_minimum",
                    "strict_clean_trend": True,
                    "filters": {
                        "use_killzone": True,
                        "killzone_mode": "score",
                        "allowed_sessions": ["London", "NewYork", "Overlap"],
                        "use_spread_filter": True,
                        "max_spread_percentile": 70,
                        "use_alpha": True,
                        "min_alpha_score": 5,
                        "reject_m08_conflict": True,
                        "reject_m11_exhaustion": True,
                        "reject_rollover": True,
                        "reject_news": True,
                        "allow_news_regime_only": False,
                    },
                    "costs": {
                        "cost_mode": "stress_adjusted",
                        "cost_r_per_trade": 0.05,
                        "commission_R": 0.0,
                        "slippage_points": 1.0,
                        "spread_round_trip_factor": 1.0,
                        "news_cost_multiplier": 2.0,
                        "rollover_block": True,
                    },
                    "execution_assumption": {
                        "entry_price": "signal_close",
                        "same_candle_sl_tp": "sl_first",
                        "one_trade_at_a_time": True,
                    },
                    "regime_controls": {
                        "min_regime_confidence": 0.75,
                        "allow_placeholder_news": False,
                        "strict_mtf_for_trends": True,
                        "allow_exhaustion_reversal": True,
                        "allow_post_news_trading": False,
                        "post_news_wait_bars": 3,
                        "low_vol_drift_atr_min": 15,
                        "low_vol_drift_atr_max": 35,
                        "low_vol_drift_adx_min": 14,
                        "low_vol_drift_adx_max": 25,
                        "low_vol_drift_er_min": 0.20,
                        "channel_lookback": 50,
                        "channel_slope_min": 0.02,
                        "channel_touch_tolerance_atr": 0.25,
                        "range_rejection_wick_min": 0.35,
                        "false_breakout_wick_min": 0.35,
                        "false_breakout_reclaim_bars": 3,
                        "opening_range_minutes": 30,
                        "opening_range_breakout_buffer_atr": 0.10,
                        "opening_range_retest_tolerance_atr": 0.25,
                        "overlap_start_utc": "12:00",
                        "overlap_end_utc": "16:00",
                        "asia_start_utc": "00:00",
                        "asia_end_utc": "07:00",
                        "chop_adx_max": 18,
                        "chop_er_max": 0.20,
                        "chop_atr_percentile_min": 75,
                        "chop_ema_cross_min": 4,
                        "dead_atr_percentile_max": 15,
                        "dead_bb_width_percentile_max": 15,
                        "dead_adx_max": 15,
                        "month_end_start_day": 25,
                        "fixing_start_utc": "15:00",
                        "fixing_end_utc": "16:15",
                        "macro_bias_mode": "manual",
                        "allow_macro_regime_without_manual_bias": False,
                    },
                    "strategy_controls": {
                        "breakout_retest_valid_bars": 5,
                        "compression_lookback": 20,
                        "ema_pullback_zone_atr": 0.35,
                        "breakout_retest_tolerance_atr": 0.25,
                        "default_sl_buffer_atr": 0.30,
                        "breakout_sl_buffer_atr": 0.50,
                        "sweep_sl_buffer_atr": 0.25,
                        "drift_pullback_zone_atr": 0.25,
                        "drift_sl_buffer_atr": 0.25,
                        "channel_sl_buffer_atr": 0.35,
                        "range_sl_buffer_atr": 0.25,
                        "false_breakout_sl_buffer_atr": 0.30,
                        "orb_retest_valid_bars": 5,
                        "orb_sl_buffer_atr": 0.50,
                        "overlap_pullback_zone_atr": 0.35,
                        "overlap_breakout_buffer_atr": 0.10,
                        "asia_range_edge_tolerance_atr": 0.20,
                        "asia_range_sl_buffer_atr": 0.25,
                        "macro_pullback_zone_atr": 0.35,
                        "macro_breakout_sl_buffer_atr": 0.50,
                        "fixing_no_trade_mode": True,
                    },
                    "risk_controls": {
                        "research_risk_percent": 1.0,
                        "funded_min_risk_percent": 0.25,
                        "funded_max_risk_percent": 0.50,
                        "max_trades_per_day": 3,
                        "max_consecutive_losses": 3,
                    },
                },
                "query_params": None,
                "response_shape": {"run_id": "uuid", "summary": {}, "cost_summary": {}, "spread_slippage_diagnostics": {"session": [], "regime": [], "symbol": []}, "data_health": {}, "feature_summary": {}, "regime_confidence": [], "regime_performance": [], "strategy_performance": [], "unique_combination_performance": [], "modifier_impact": [], "session_performance": [], "monthly_performance": [], "skipped_setups": [], "equity_curve": [], "drawdown_curve": [], "trades": [], "explanation": {}},
            },
            {
                "method": "POST",
                "path": "/api/walk-forward/run",
                "purpose": "Run repeated train/test windows using the existing backtest engine without saving internal window runs.",
                "request_body": {
                    "symbol": "EURUSD",
                    "timeframe": "M15",
                    "start_date": "2025-11-01",
                    "end_date": "2026-05-01",
                    "regime_filter": "R01",
                    "strategy_filter": "T1",
                    "risk_percent": 1.0,
                    "rr": 2.0,
                    "initial_equity": 100000,
                    "train_months": 2,
                    "test_months": 1,
                    "step_months": 1,
                    "min_test_trades": 20,
                    "min_test_profit_factor": 1.1,
                },
                "query_params": None,
                "response_shape": {"summary": {"windows": 3, "passed_windows": 2, "stable": True}, "windows": [], "warnings": []},
            },
            {
                "method": "POST",
                "path": "/api/out-of-sample/run",
                "purpose": "Run one in-sample period and one future out-of-sample period using the same research controls.",
                "request_body": {
                    "symbol": "EURUSD",
                    "timeframe": "M15",
                    "start_date": "2025-11-01",
                    "end_date": "2026-05-01",
                    "regime_filter": "R01",
                    "strategy_filter": "T1",
                    "risk_percent": 1.0,
                    "rr": 2.0,
                    "initial_equity": 100000,
                    "split_date": None,
                    "oos_percent": 30,
                    "min_oos_trades": 20,
                    "min_oos_profit_factor": 1.1,
                },
                "query_params": None,
                "response_shape": {"summary": {"status": "PASS", "stable": True, "performance_retention": 0.72}, "in_sample": {}, "out_of_sample": {}, "comparison": {}, "warnings": []},
            },
            {
                "method": "POST",
                "path": "/api/portfolio/backtest",
                "purpose": "Run the selected setup across multiple symbols and timeframes, then aggregate symbol, timeframe, correlation, concentration, portfolio drawdown, and regime robustness metrics.",
                "request_body": {
                    "symbols": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
                    "timeframes": ["M15", "M5", "H1"],
                    "start_date": "2025-11-01",
                    "end_date": "2026-05-01",
                    "regime_filter": "ALL",
                    "strategy_filter": "ALL",
                    "risk_percent": 1.0,
                    "rr": 2.0,
                    "initial_equity": 100000,
                    "portfolio_risk": {"max_drawdown_R": 12, "max_symbol_trade_share": 0.5, "max_currency_exposure_share": 0.65, "min_symbols_with_trades": 2},
                    "filters": {"use_killzone": True, "killzone_mode": "score_only", "use_spread_filter": True, "max_spread_percentile": 70},
                },
                "query_params": None,
                "response_shape": {"summary": {}, "legs": [], "symbol_performance": [], "timeframe_performance": [], "symbol_timeframe_matrix": [], "correlation": {}, "concentration_warnings": [], "risk_diagnostics": {}, "regime_robustness": [], "equity_curve": [], "drawdown_curve": []},
            },
            {
                "method": "POST",
                "path": "/api/optimizer/grid",
                "purpose": "Run controlled regime/strategy/filter/pattern permutations, rank candidates, optionally validate top rows with OOS/WF/MC, and save only candidates that pass the anti-overfit gate.",
                "request_body": {
                    "symbol": "EURUSD",
                    "timeframe": "M15",
                    "start_date": "2025-11-01",
                    "end_date": "2026-05-01",
                    "regime_filter": "R01",
                    "strategy_filter": "T1",
                    "risk_percent": 1.0,
                    "rr": 2.0,
                    "initial_equity": 100000,
                    "max_combinations": 50,
                    "min_trades": 30,
                    "min_profit_factor": 1.2,
                    "max_drawdown_r": 10,
                    "validate_top_n": 3,
                    "persist_validated_candidates": True,
                    "validation": {
                        "out_of_sample": {"oos_percent": 30, "min_oos_trades": 20, "min_oos_profit_factor": 1.1},
                        "walk_forward": {"train_months": 2, "test_months": 1, "step_months": 1, "min_test_trades": 20},
                        "monte_carlo": {"simulations": 1000, "min_trades": 30, "max_total_drawdown_percent": 10},
                    },
                    "grid": {
                        "regime_filters": ["R01"],
                        "strategy_filters": ["T1", "T2"],
                        "rr_values": [1.5, 2.0],
                        "min_alpha_scores": [5, 7, 9],
                        "max_spread_percentiles": [65, 70],
                        "killzone_modes": ["score_only", "hard_filter"],
                        "alpha_modes": ["hard_minimum"],
                        "spread_filter_modes": ["score_only"],
                        "pattern_score_modes": ["score_only", "hard_minimum"],
                        "min_pattern_scores": [0, 2],
                    },
                },
                "query_params": None,
                "response_shape": {"summary": {"combinations_run": 16, "approved_candidates": 2, "validated_candidates": 1, "saved_validated_candidates": 1}, "results": [], "top_candidates": [], "validated_candidates": [], "warnings": []},
            },
            {
                "method": "POST",
                "path": "/api/experiments/ab/run",
                "purpose": "Compare a named baseline backtest against named variants, calculate deltas, apply decision gates, and save the experiment.",
                "request_body": {
                    "name": "R01 T1 strict filter test",
                    "hypothesis": "Hard killzone and higher alpha should improve expectancy without unacceptable drawdown.",
                    "baseline_label": "Current controls",
                    "base_payload": {
                        "symbol": "EURUSD",
                        "timeframe": "M15",
                        "start_date": "2025-11-01",
                        "end_date": "2026-05-01",
                        "regime_filter": "R01",
                        "strategy_filter": "T1",
                        "risk_percent": 1.0,
                        "rr": 2.0,
                        "initial_equity": 100000,
                    },
                    "variants": [
                        {"label": "Hard killzone + alpha 8", "changes": {"killzone_mode": "hard_filter", "filters": {"killzone_mode": "hard_filter", "min_alpha_score": 8}}}
                    ],
                    "decision_rules": {"min_trades": 30, "min_profit_factor": 1.2, "min_expectancy_improvement_R": 0.02, "max_drawdown_R": 12},
                },
                "query_params": None,
                "response_shape": {"summary": {"status": "VARIANT_ACCEPTED"}, "baseline": {}, "variants": [], "comparison": [], "warnings": []},
            },
            {
                "method": "POST",
                "path": "/api/monte-carlo/run",
                "purpose": "Stress-test a selected backtest setup by reshuffling or bootstrapping trade R outcomes to estimate drawdown, losing-streak, and loss probabilities.",
                "request_body": {
                    "symbol": "EURUSD",
                    "timeframe": "M15",
                    "start_date": "2025-11-01",
                    "end_date": "2026-05-01",
                    "regime_filter": "R01",
                    "strategy_filter": "T1",
                    "risk_percent": 1.0,
                    "rr": 2.0,
                    "initial_equity": 100000,
                    "simulations": 1000,
                    "sample_mode": "bootstrap",
                    "seed": 42,
                    "min_trades": 30,
                    "max_total_drawdown_percent": 10,
                    "max_losing_streak_limit": 5,
                },
                "query_params": None,
                "response_shape": {"summary": {"status": "PASS", "source_trades": 120, "probability_drawdown_breach": 0.08}, "observed": {}, "distribution": {}, "equity_fan": [], "risk_of_ruin": {}, "warnings": []},
            },
            {
                "method": "POST",
                "path": "/api/macro/evidence",
                "purpose": "Resolve manual, direct evidence, or database macro inputs into USD bias, risk sentiment, central-bank divergence, news flag, confidence, and R25-R29 activation gates.",
                "request_body": {
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
                "query_params": None,
                "response_shape": {"usd_bias": "USD_BULLISH", "risk_sentiment": "RISK_OFF", "cb_divergence": "BULLISH_BASE", "confidence": {}, "activation_allowed": {"R25": True, "R26": False, "R27": False, "R28": True, "R29": True}, "scores": {}, "reasons": [], "warnings": []},
            },
            {
                "method": "POST",
                "path": "/api/macro/import-csv",
                "purpose": "Import macro evidence rows into SQLite. Use Macro Mode = database to apply the latest imported row to R25-R29.",
                "request_body": {
                    "source": "macro_research_csv",
                    "csv_text": "timestamp,symbol,dxy_change_percent,usd_basket_change_percent,us_yield_change_bp,fed_rate_expectation_change_bp,spx_change_percent,vix_change_percent,gold_change_percent,jpy_strength_score,chf_strength_score,base_rate_expectation_change_bp,quote_rate_expectation_change_bp,high_impact_news,minutes_to_news,minutes_since_news\n2026-01-02T12:00:00Z,EURUSD,0.35,0.25,6,6,-0.7,5,0.8,1,0,12,0,false,9999,9999\n",
                },
                "query_params": None,
                "response_shape": {"saved": 1, "rows_received": 1, "latest": {"timestamp": "...", "symbol": "EURUSD", "resolved": {}}, "warnings": []},
            },
            {
                "method": "POST",
                "path": "/api/macro/import-url",
                "purpose": "Download a UTF-8 CSV or JSON macro/news/cross-market evidence feed and import it into SQLite using normalized macro columns.",
                "request_body": {
                    "url": "https://example.com/macro_evidence.csv",
                    "source": "research_feed",
                    "feed_type": "macro",
                    "feed_format": "auto",
                    "timeout_seconds": 15,
                },
                "query_params": None,
                "response_shape": {"saved": 1, "rows_received": 1, "latest": {"timestamp": "...", "symbol": "EURUSD", "resolved": {}}, "warnings": []},
            },
            {
                "method": "POST",
                "path": "/api/macro/import-feed",
                "purpose": "Import pasted CSV or JSON macro/news feed text, including economic-calendar style fields like currency, event, impact, and minutes_to_news.",
                "request_body": {
                    "source": "economic_calendar_json",
                    "feed_type": "news",
                    "feed_format": "json",
                    "feed_text": '[{"timestamp":"2026-01-02T13:30:00Z","currency":"USD","event":"NFP","impact":"High","minutes_to_news":15}]',
                },
                "query_params": None,
                "response_shape": {"saved": 1, "rows_received": 1, "latest": {"timestamp": "...", "symbol": "USD", "resolved": {}}, "warnings": []},
            },
            {
                "method": "POST",
                "path": "/api/macro/cross-pair/import",
                "purpose": "Build USD, safe-haven, and risk-proxy evidence from saved MT5 candles across major FX pairs, then save it to macro_data for database macro mode.",
                "request_body": {
                    "symbol": "EURUSD",
                    "timeframe": "M15",
                    "start_date": "2026-01-01",
                    "end_date": "2026-06-01",
                    "symbols": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD", "EURJPY", "GBPJPY"],
                    "source": "saved_mt5_candles_cross_pair",
                },
                "query_params": None,
                "response_shape": {"saved": 1, "cross_pair_summary": {}, "cross_pair_components": []},
            },
            {
                "method": "GET",
                "path": "/api/macro/data",
                "purpose": "Read imported macro evidence rows and their resolved R25-R29 confidence gates.",
                "request_body": None,
                "query_params": {"symbol": "EURUSD", "start_date": "2026-01-01", "end_date": "2026-06-01", "limit": 100},
                "response_shape": {"count": 1, "rows": [{"timestamp": "...", "symbol": "EURUSD", "evidence": {}, "resolved": {}}]},
            },
            {
                "method": "POST",
                "path": "/api/mt5/report/import",
                "purpose": "Import a pasted MT5 Strategy Tester CSV/TSV/HTML report and convert it into UI-ready real-tick/model-comparison metrics. This does not run MT5 or place orders.",
                "request_body": {
                    "file_name": "EURUSD_M15_real_ticks_report.csv",
                    "test_model": "every_tick_real_ticks",
                    "run_id": None,
                    "symbol": "EURUSD",
                    "timeframe": "M15",
                    "start_date": "2026-01-01",
                    "end_date": "2026-06-01",
                    "initial_equity": 100000,
                    "risk_percent": 1.0,
                    "report_text": "Time,Symbol,Type,Volume,Price,Profit,Balance,Comment\n2026-01-02 10:15,EURUSD,buy,0.10,1.10000,120.50,100120.50,T1\n",
                },
                "query_params": None,
                "response_shape": {"import_id": "uuid", "summary": {}, "model_comparison_row": {}, "deals": [], "warnings": []},
            },
            {
                "method": "POST",
                "path": "/api/mt5/model-comparison/import",
                "purpose": "Import 1-Min OHLC, Every Tick, and Real Ticks MT5 reports for the same setup and return model-stability approval checks.",
                "request_body": {
                    "symbol": "EURUSD",
                    "timeframe": "M15",
                    "start_date": "2026-01-01",
                    "end_date": "2026-06-01",
                    "initial_equity": 100000,
                    "risk_percent": 1.0,
                    "reports": {
                        "one_min_ohlc": "Time,Symbol,Type,Volume,Price,Profit,Balance,Comment\n...",
                        "every_tick": "Time,Symbol,Type,Volume,Price,Profit,Balance,Comment\n...",
                        "every_tick_real_ticks": "Time,Symbol,Type,Volume,Price,Profit,Balance,Comment\n...",
                    },
                    "thresholds": {"min_trades": 30, "min_profit_factor": 1.10, "max_pf_drift": 0.35},
                },
                "query_params": None,
                "response_shape": {"status": "MODEL_STABLE_APPROVED_FOR_REVIEW", "rows": [], "checks": [], "stability": {}, "warnings": []},
            },
            {
                "method": "POST",
                "path": "/api/mt5/tester/run",
                "purpose": "Create MT5 tester .ini/.set files, optionally launch terminal64.exe with the selected regime/strategy/pattern controls, and optionally import the generated MT5 report. No live order execution is performed.",
                "request_body": {
                    "payload": {
                        "symbol": "EURUSD",
                        "timeframe": "M15",
                        "start_date": "2026-01-01",
                        "end_date": "2026-06-01",
                        "regime_filter": "R01",
                        "strategy_filter": "T1",
                        "risk_percent": 1.0,
                        "rr": 2.0,
                        "initial_equity": 100000,
                        "mt5_backtest": {"test_model": "every_tick_real_ticks"},
                    },
                    "terminal_path": "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
                    "expert": "QuantForexV10_ResearchEA.ex5",
                    "launch_terminal": True,
                    "wait_for_report": False,
                    "timeout_seconds": 120,
                },
                "query_params": None,
                "response_shape": {"run_id": "uuid", "status": "TERMINAL_LAUNCHED", "tester_config": {}, "bridge": {}, "report_import": None, "warnings": []},
            },
            {
                "method": "POST",
                "path": "/api/mt5/real-tick-workflow",
                "purpose": "Prepare the same candidate setup for 1-Min OHLC, Every Tick, and Real Ticks MT5 Strategy Tester runs, then optionally import/compare all three reports. Launching MT5 is opt-in and no live order execution is performed.",
                "request_body": {
                    "payload": {
                        "symbol": "EURUSD",
                        "timeframe": "M15",
                        "start_date": "2026-01-01",
                        "end_date": "2026-06-01",
                        "regime_filter": "R01",
                        "strategy_filter": "T1",
                        "risk_percent": 1.0,
                        "rr": 2.0,
                        "initial_equity": 100000,
                    },
                    "launch_terminal": False,
                    "reports": {
                        "one_min_ohlc": "Time,Symbol,Type,Volume,Price,Profit,Balance,Comment\n...",
                        "every_tick": "Time,Symbol,Type,Volume,Price,Profit,Balance,Comment\n...",
                        "every_tick_real_ticks": "Time,Symbol,Type,Volume,Price,Profit,Balance,Comment\n...",
                    },
                    "thresholds": {"min_trades": 30, "min_profit_factor": 1.10, "max_pf_drift": 0.35},
                },
                "query_params": None,
                "response_shape": {"workflow_id": "uuid", "status": "REPORTS_IMPORTED", "steps": [], "tester_runs": {}, "model_comparison": {}, "warnings": []},
            },
            {
                "method": "POST",
                "path": "/api/mt5/parity/check",
                "purpose": "Compare Python research trades against MT5 Strategy Tester trades/signals for the same symbol, timeframe, date range, regime, strategy, filters, RR, and risk controls.",
                "request_body": {
                    "payload": {"symbol": "EURUSD", "timeframe": "M15", "start_date": "2026-01-01", "end_date": "2026-06-01", "regime_filter": "R01", "strategy_filter": "T1", "risk_percent": 1.0, "rr": 2.0, "initial_equity": 100000},
                    "python_run_id": "optional-saved-python-run-id",
                    "mt5_import_id": "optional-imported-mt5-report-id",
                    "tolerances": {"price_tolerance": 0.00001, "time_tolerance_seconds": 60, "result_R_tolerance": 0.05, "profit_tolerance": 1.0},
                },
                "query_params": None,
                "response_shape": {"status": "PASS", "summary": {"python_trade_count": 50, "mt5_trade_count": 50, "mismatch_count": 0}, "checks": [], "mismatches": [], "warnings": []},
            },
            {
                "method": "GET",
                "path": "/api/backtest/{run_id}/mt5-parity-packet",
                "purpose": "Export deterministic Python expected-trade rows with PYIDX/PYHASH comments so the MT5 tester EA/report can be matched by key instead of row order.",
                "request_body": None,
                "query_params": None,
                "response_shape": {"packet_id": "hash", "python_run_id": "uuid", "expected_trade_count": 50, "expected_signals_csv": "csv text", "mt5_ea_requirements": {}},
            },
            {
                "method": "POST",
                "path": "/api/mt5/parity/complete",
                "purpose": "Institutional parity proof lane: create/resolve a saved Python run, build PYIDX/PYHASH packet, prepare tester config, optionally import MT5 report rows, and grade whether Python and MT5 decisions are proven to match.",
                "request_body": {
                    "payload": {"symbol": "EURUSD", "timeframe": "M15", "start_date": "2026-01-01", "end_date": "2026-06-01", "regime_filter": "R01", "strategy_filter": "T1", "risk_percent": 1.0, "rr": 2.0, "initial_equity": 100000},
                    "python_run_id": "optional-saved-python-run-id",
                    "report_text": "optional pasted MT5 signal/report csv with PYIDX/PYHASH",
                    "test_model": "every_tick_real_ticks",
                    "prepare_tester_config": True,
                    "launch_terminal": False,
                    "tolerances": {"price_tolerance": 0.00001, "time_tolerance_seconds": 60, "result_R_tolerance": 0.05, "profit_tolerance": 1.0},
                },
                "query_params": None,
                "response_shape": {"status": "PARITY_PROVEN", "institutional_verdict": {}, "checklist": [], "packet": {}, "tester_run": {}, "parity_check": {}, "next_actions": []},
            },
            {
                "method": "POST",
                "path": "/api/mt5/parity/check-run-report",
                "purpose": "Closed-loop parity check: take a saved Python run_id plus pasted/imported MT5 tester signal/report rows, import if needed, and compare by PYHASH/PYIDX keys.",
                "request_body": {
                    "python_run_id": "saved-python-backtest-run-id",
                    "mt5_import_id": "optional-existing-import-id",
                    "report_text": "optional pasted parity signal/report csv",
                    "test_model": "every_tick_real_ticks",
                    "tolerances": {"price_tolerance": 0.00001, "time_tolerance_seconds": 60, "result_R_tolerance": 0.05, "profit_tolerance": 1.0},
                },
                "query_params": None,
                "response_shape": {"status": "PASS", "summary": {}, "checks": [], "mismatches": [], "warnings": []},
            },
            {
                "method": "POST",
                "path": "/api/llm/review",
                "purpose": "Review the latest local backtest, MT5 model comparison, optimizer, walk-forward, and Monte Carlo context using local Ollama when available, with a deterministic rule-based fallback when Ollama is offline.",
                "request_body": {
                    "model": "llama3.1:8b",
                    "ollama_url": "http://127.0.0.1:11434",
                    "use_ollama": True,
                    "payload": {"symbol": "EURUSD", "timeframe": "M15", "regime_filter": "R01", "strategy_filter": "T1"},
                    "backtest": {"summary": {"total_trades": 120, "profit_factor": 1.22, "expectancy_R": 0.08}},
                    "mt5_comparison": {"status": "MODEL_STABLE_APPROVED_FOR_REVIEW", "rows": []},
                },
                "query_params": None,
                "response_shape": {"status": "OLLAMA_REVIEW_COMPLETE", "used_ollama": True, "review": {"verdict": "WATCHLIST_ONLY", "strengths": [], "weaknesses": [], "blockers": [], "next_tests": []}, "warnings": []},
            },
            {
                "method": "POST",
                "path": "/api/final-approval/review",
                "purpose": "Apply the final validation gate. Optimizer ranking is optional, but approval requires local backtest, out-of-sample, walk-forward, Monte Carlo, MT5 real-tick model comparison, and anti-overfit gates to pass.",
                "request_body": {
                    "auto_run_missing": False,
                    "payload": {"symbol": "EURUSD", "timeframe": "M15", "regime_filter": "R01", "strategy_filter": "T1"},
                    "backtest": {"summary": {"total_trades": 120, "profit_factor": 1.22, "expectancy_R": 0.08, "max_drawdown_R": -6}},
                    "out_of_sample": {"summary": {"status": "PASS", "stable": True}},
                    "walk_forward": {"summary": {"stable": True, "pass_rate": 0.7}},
                    "monte_carlo": {"summary": {"status": "PASS"}, "risk_of_ruin": {"drawdown_breach_probability": 0.06}},
                    "mt5_comparison": {"status": "MODEL_STABLE_APPROVED_FOR_REVIEW", "rows": []},
                },
                "query_params": None,
                "response_shape": {"status": "FINAL_APPROVED_FOR_DEMO_REVIEW", "decision": "...", "checks": [], "failed_checks": [], "anti_overfit_gate": {"status": "PASS", "checks": [], "thresholds": {}}, "warnings": []},
            },
            {
                "method": "GET",
                "path": "/api/mt5/report/imports",
                "purpose": "List saved MT5 Strategy Tester report imports.",
                "request_body": None,
                "query_params": {"limit": 25},
                "response_shape": {"count": 1, "imports": [{"import_id": "uuid", "test_model": "every_tick_real_ticks", "summary": {}}]},
            },
            {
                "method": "GET",
                "path": "/api/backtests",
                "purpose": "List saved backtest runs for local review and UI reload.",
                "request_body": None,
                "query_params": {"limit": 25},
                "response_shape": {"count": 1, "runs": [{"run_id": "uuid", "symbol": "EURUSD", "total_trades": 120, "profit_factor": 1.2}]},
            },
            {
                "method": "GET",
                "path": "/api/backtest/{run_id}",
                "purpose": "Read saved backtest summary by run_id.",
                "request_body": None,
                "query_params": None,
                "response_shape": {"run_id": "uuid", "summary": {}, "regime_performance": [], "strategy_performance": [], "combination_performance": [], "explanation": {}},
            },
            {
                "method": "GET",
                "path": "/api/backtest/{run_id}/trades",
                "purpose": "Read saved backtest trades by run_id.",
                "request_body": None,
                "query_params": None,
                "response_shape": {"run_id": "uuid", "count": 0, "trades": []},
            },
        ],
    }


@app.post("/api/regime/detect-latest", response_model=DetectLatestResponse)
def api_detect_latest(request: DetectLatestRequest) -> dict[str, Any]:
    data_source = (request.data_source_controls or {}).get("data_source")
    candles = load_candles(request.symbol, request.timeframe, data_source=data_source)
    if candles.empty:
        raise HTTPException(status_code=404, detail="No candles found for the selected data source. Fetch/import that source first.")
    tail = candles.tail(400)
    macro_evidence = dict(request.macro_evidence or {})
    macro_evidence.setdefault("symbol", request.symbol)
    macro_evidence.setdefault("start_date", tail["timestamp"].iloc[0].isoformat())
    macro_evidence.setdefault("end_date", tail["timestamp"].iloc[-1].isoformat())
    macro_evidence.setdefault("as_of", tail["timestamp"].iloc[-1].isoformat())
    _, features, cache_meta = load_or_calculate_features(
        symbol=request.symbol,
        timeframe=request.timeframe,
        start_date=tail["timestamp"].iloc[0].isoformat(),
        end_date=tail["timestamp"].iloc[-1].isoformat(),
        sentiment=request.sentiment,
        usd_bias=request.usd_bias,
        risk_sentiment=request.risk_sentiment,
        cb_divergence=request.cb_divergence,
        macro_evidence=macro_evidence,
        data_source_controls=request.data_source_controls,
        use_cache=True,
        persist_cache=True,
    )
    latest = features.iloc[-1].to_dict()
    modifiers = detect_modifiers(latest)
    regime = detect_regime(latest)
    explanation = explain_regime_detection(latest, regime, modifiers)
    return _clean(
        {
            "latest_features": latest,
            "feature_cache": cache_meta,
            "active_regime": regime,
            "modifiers": modifiers,
            "hard_block": modifiers["hard_block"],
            "allowed_strategies": [STRATEGIES[s] for s in regime.get("allowed_strategies", []) if s in STRATEGIES],
            "explanation": explanation,
        }
    )


@app.post("/api/backtest/run", response_model=BacktestRunResponse)
def api_run_backtest(request: BacktestRequest) -> dict[str, Any]:
    try:
        result = run_backtest(_body(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _clean(result)


@app.post("/api/walk-forward/run", response_model=WalkForwardResponse)
def api_run_walk_forward(request: WalkForwardRequest) -> dict[str, Any]:
    body = _body(request)
    try:
        result = run_walk_forward(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_validation_result("walk_forward", result, body)
    return _clean(result)


@app.post("/api/out-of-sample/run", response_model=OutOfSampleResponse)
def api_run_out_of_sample(request: OutOfSampleRequest) -> dict[str, Any]:
    body = _body(request)
    try:
        result = run_out_of_sample(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_validation_result("out_of_sample", result, body)
    return _clean(result)


@app.post("/api/portfolio/backtest", response_model=PortfolioBacktestResponse)
def api_run_portfolio_backtest(request: PortfolioBacktestRequest) -> dict[str, Any]:
    body = _body(request)
    result = run_portfolio_backtest(body)
    save_validation_result("portfolio", result, body)
    return _clean(result)


@app.post("/api/optimizer/grid", response_model=OptimizerGridResponse)
def api_run_optimizer_grid(request: OptimizerGridRequest) -> dict[str, Any]:
    try:
        result = run_optimizer_grid(_body(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _clean(result)


@app.post("/api/research/monthly-regime-sweep", response_model=MonthlyRegimeResearchResponse)
def api_monthly_regime_research(request: MonthlyRegimeResearchRequest) -> dict[str, Any]:
    body = _body(request)
    try:
        result = run_monthly_regime_research(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_validation_result("monthly_regime_research", result, body)
    save_monthly_regime_sweep_result(result, body)
    return _clean(result)


@app.get("/api/research/monthly-regime-sweeps")
def api_list_monthly_regime_sweeps(limit: int = Query(25, ge=1, le=200)) -> dict[str, Any]:
    return {"monthly_sweeps": list_monthly_regime_sweep_runs(limit)}


@app.get("/api/research/monthly-regime-sweeps/{monthly_sweep_run_id}", response_model=MonthlyRegimeResearchResponse)
def api_get_monthly_regime_sweep(monthly_sweep_run_id: str) -> dict[str, Any]:
    result = load_monthly_regime_sweep_run(monthly_sweep_run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Monthly regime sweep run not found.")
    return _clean(result)


@app.post("/api/research/value-profiles")
def api_save_research_value_profile(profile: dict[str, Any]) -> dict[str, Any]:
    payload = profile.get("payload")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be an object containing the research values to reuse.")
    saved = save_research_value_profile(profile)
    return _clean({"status": "SAVED", "profile": saved})


@app.get("/api/research/value-profiles")
def api_list_research_value_profiles(limit: int = Query(25, ge=1, le=200)) -> dict[str, Any]:
    return {"profiles": list_research_value_profiles(limit)}


@app.get("/api/research/value-profiles/{profile_id}")
def api_get_research_value_profile(profile_id: str) -> dict[str, Any]:
    profile = load_research_value_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Research value profile not found.")
    return {"profile": profile}


@app.post("/api/experiments/ab/run", response_model=ABExperimentResponse)
def api_run_ab_experiment(request: ABExperimentRequest) -> dict[str, Any]:
    try:
        result = run_ab_experiment(_body(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _clean(result)


@app.get("/api/experiments")
def api_list_ab_experiments(limit: int = Query(25, ge=1, le=200)) -> dict[str, Any]:
    return {"experiments": _clean(list_ab_experiments(limit))}


@app.get("/api/experiments/{experiment_id}", response_model=ABExperimentResponse)
def api_load_ab_experiment(experiment_id: str) -> dict[str, Any]:
    experiment = load_ab_experiment(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found.")
    return _clean(experiment)


@app.get("/api/calibration/profiles", response_model=CalibrationProfilesResponse)
def api_calibration_profiles() -> dict[str, Any]:
    return _clean(list_calibration_profiles())


@app.post("/api/monte-carlo/run", response_model=MonteCarloResponse)
def api_run_monte_carlo(request: MonteCarloRequest) -> dict[str, Any]:
    body = _body(request)
    result = run_monte_carlo(body)
    save_validation_result("monte_carlo", result, body)
    return _clean(result)


@app.post("/api/validation/cockpit")
def api_validation_cockpit(request: dict[str, Any]) -> dict[str, Any]:
    try:
        result = run_validation_cockpit(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_validation_result("validation_cockpit", result, request)
    return _clean(result)


@app.post("/api/macro/evidence", response_model=MacroEvidenceResponse)
def api_macro_evidence(request: MacroEvidenceRequest) -> dict[str, Any]:
    body = _body(request)
    result = resolve_macro_context(body.get("usd_bias", "NEUTRAL"), body.get("risk_sentiment", "NEUTRAL"), body.get("cb_divergence", "NEUTRAL"), body.get("macro_evidence", {}))
    return _clean(result)


@app.post("/api/macro/import-csv", response_model=MacroImportCsvResponse)
def api_macro_import_csv(request: MacroImportCsvRequest) -> dict[str, Any]:
    try:
        result = import_macro_csv(request.csv_text, request.source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _clean(result)


@app.post("/api/macro/import-feed", response_model=MacroImportCsvResponse)
def api_macro_import_feed(request: MacroImportFeedRequest) -> dict[str, Any]:
    try:
        result = import_macro_feed_text(request.feed_text, request.source, request.feed_type, request.feed_format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _clean(result)


@app.post("/api/macro/import-url", response_model=MacroImportCsvResponse)
def api_macro_import_url(request: MacroImportUrlRequest) -> dict[str, Any]:
    if not request.url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Only http:// and https:// macro/news feed URLs are supported.")
    try:
        url_request = UrlRequest(request.url, headers={"User-Agent": "quant_forex_V10/1.0"})
        with urlopen(url_request, timeout=request.timeout_seconds) as response:
            raw = response.read(5_000_000 + 1)
            content_type = response.headers.get("content-type", "")
    except (OSError, URLError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not download macro/news feed: {exc}") from exc
    if len(raw) > 5_000_000:
        raise HTTPException(status_code=400, detail="Macro/news feed is too large. Limit is 5 MB.")
    try:
        feed_text = raw.decode("utf-8-sig")
        feed_format = request.feed_format
        if feed_format == "auto":
            feed_format = "json" if "json" in content_type.lower() or request.url.lower().split("?")[0].endswith(".json") else "csv"
        result = import_macro_feed_text(feed_text, request.source or request.url, request.feed_type, feed_format)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Macro/news feed must be UTF-8 text.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _clean(result)


@app.post("/api/macro/cross-pair/import")
def api_macro_cross_pair_import(request: CrossPairEvidenceRequest) -> dict[str, Any]:
    try:
        result = import_cross_pair_evidence(
            request.symbol,
            request.timeframe,
            request.start_date,
            request.end_date,
            request.symbols,
            request.source,
            request.data_source_controls,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _clean(result)


@app.post("/api/macro/cot/import")
def api_macro_cot_import(request: CotImportRequest) -> dict[str, Any]:
    try:
        result = import_cot_evidence(
            symbols=request.symbols,
            as_of=request.as_of,
            source=request.source,
            report_type=request.report_type,
            timeout_seconds=request.timeout_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _clean(result)


@app.get("/api/macro/data")
def api_macro_data(
    symbol: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = Query(100, ge=1, le=5000),
) -> dict[str, Any]:
    return _clean(list_macro_evidence(symbol, start_date, end_date, limit))


@app.get("/api/macro/diagnostics", response_model=MacroDiagnosticsResponse)
def api_macro_diagnostics(
    symbol: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    as_of: str | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    return _clean(macro_pipeline_diagnostics(symbol, start_date, end_date, as_of, limit))


@app.post("/api/mt5/report/import", response_model=MT5ReportImportResponse)
def api_import_mt5_report(request: MT5ReportImportRequest) -> dict[str, Any]:
    body = _body(request)
    try:
        result = import_mt5_report(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_validation_result("mt5_report_import", result, body)
    return _clean(result)


@app.post("/api/mt5/model-comparison/import", response_model=MT5ModelComparisonImportResponse)
def api_import_mt5_model_comparison(request: MT5ModelComparisonImportRequest) -> dict[str, Any]:
    body = _body(request)
    result = compare_mt5_model_reports(body)
    save_validation_result("mt5_model_comparison", result, body)
    return _clean(result)


@app.post("/api/cost/calibration", response_model=BrokerCostCalibrationResponse)
def api_broker_cost_calibration(request: BrokerCostCalibrationRequest) -> dict[str, Any]:
    result = calibrate_broker_costs(_body(request))
    return _clean(result)


@app.post("/api/mt5/real-tick-workflow", response_model=MT5RealTickWorkflowResponse)
def api_mt5_real_tick_workflow(request: MT5RealTickWorkflowRequest) -> dict[str, Any]:
    body = _body(request)
    result = run_real_tick_workflow(body)
    save_validation_result("mt5_real_tick_workflow", result, body)
    return _clean(result)


@app.post("/api/mt5/parity/check", response_model=MT5ParityResponse)
def api_mt5_parity_check(request: MT5ParityRequest) -> dict[str, Any]:
    result = run_mt5_parity_check(_body(request))
    return _clean(result)


@app.post("/api/mt5/parity/complete", response_model=MT5ParityCompletionResponse)
def api_mt5_parity_complete(request: MT5ParityCompletionRequest) -> dict[str, Any]:
    try:
        result = run_mt5_parity_completion(_body(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _clean(result)


@app.get("/api/backtest/{run_id}/mt5-parity-packet", response_model=MT5ParityPacketResponse)
def api_backtest_mt5_parity_packet(run_id: str) -> dict[str, Any]:
    try:
        result = build_python_parity_packet(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _clean(result)


@app.post("/api/mt5/parity/check-run-report", response_model=MT5ParityResponse)
def api_mt5_parity_check_run_report(request: MT5ParityRunReportRequest) -> dict[str, Any]:
    body = _body(request)
    run_id = body["python_run_id"]
    import_id = body.get("mt5_import_id")
    imported = None
    if body.get("report_text"):
        packet = build_python_parity_packet(run_id)
        imported = import_mt5_report(
            {
                "run_id": run_id,
                "report_text": body["report_text"],
                "file_name": body.get("file_name"),
                "test_model": body.get("test_model"),
                "symbol": packet["candidate"].get("symbol"),
                "timeframe": packet["candidate"].get("timeframe"),
                "start_date": packet["candidate"].get("start_date"),
                "end_date": packet["candidate"].get("end_date"),
                "initial_equity": packet["candidate"].get("initial_equity") or 100000,
                "risk_percent": packet["candidate"].get("risk_percent") or 1.0,
                "max_deals_returned": 5000,
            }
        )
        import_id = imported["import_id"]
    if not import_id and imported is None:
        raise HTTPException(status_code=400, detail="Provide mt5_import_id or report_text.")
    return _clean(
        run_mt5_parity_check(
            {
                "python_run_id": run_id,
                "mt5_import_id": import_id,
                "mt5_import": imported or {},
                "tolerances": body.get("tolerances", {}),
                "max_mismatches_returned": body.get("max_mismatches_returned", 50),
            }
        )
    )


@app.post("/api/llm/review", response_model=OllamaReviewResponse)
def api_llm_review(request: OllamaReviewRequest) -> dict[str, Any]:
    result = run_ollama_review(_body(request))
    return _clean(result)


@app.post("/api/final-approval/review", response_model=FinalApprovalResponse)
def api_final_approval_review(request: FinalApprovalRequest) -> dict[str, Any]:
    result = final_approval_review(_body(request))
    return _clean(result)


@app.get("/api/mt5/report/imports")
def api_list_mt5_report_imports(limit: int = Query(25, ge=1, le=200)) -> dict[str, Any]:
    imports = list_mt5_report_imports(limit)
    return _clean({"count": len(imports), "imports": imports})


@app.get("/api/favorites")
def api_list_favorites(item_type: str | None = None) -> dict[str, Any]:
    items = list_favorites(item_type)
    return _clean({"count": len(items), "favorites": items})


@app.post("/api/favorites")
def api_set_favorite(request: dict[str, Any]) -> dict[str, Any]:
    try:
        result = set_favorite(request.get("item_type", ""), request.get("item_id", ""), bool(request.get("is_favorite", True)))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _clean(result)


@app.get("/api/validation/runs")
def api_list_validation_runs(
    limit: int = Query(25, ge=1, le=200),
    validation_type: str | None = None,
) -> dict[str, Any]:
    runs = list_validation_runs(limit=limit, validation_type=validation_type)
    return _clean({"count": len(runs), "runs": runs})


@app.get("/api/validation/runs/{validation_run_id}")
def api_get_validation_run(validation_run_id: str) -> dict[str, Any]:
    result = load_validation_run(validation_run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Validation run not found.")
    return _clean(result)


@app.get("/api/backtests")
def api_list_backtests(limit: int = Query(25, ge=1, le=200)) -> dict[str, Any]:
    runs = list_backtest_runs(limit)
    return _clean({"count": len(runs), "runs": runs})


@app.get("/api/backtest/{run_id}", response_model=BacktestStoredResponse)
def api_get_backtest(run_id: str) -> dict[str, Any]:
    result = load_backtest(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Backtest run not found.")
    return _clean(result)


@app.get("/api/backtest/{run_id}/trades", response_model=BacktestTradesResponse)
def api_get_backtest_trades(run_id: str) -> dict[str, Any]:
    trades = load_backtest_trades(run_id)
    return _clean({"run_id": run_id, "count": len(trades), "trades": trades})
