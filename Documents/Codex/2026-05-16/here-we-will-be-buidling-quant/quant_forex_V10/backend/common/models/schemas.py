from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Sentiment = Literal["BULLISH", "BEARISH", "NEUTRAL"]
UsdBias = Literal["USD_BULLISH", "USD_BEARISH", "NEUTRAL"]
RiskSentiment = Literal["RISK_ON", "RISK_OFF", "NEUTRAL"]
CbDivergence = Literal["BULLISH_BASE", "BEARISH_BASE", "NEUTRAL"]


class DateRangeRequest(BaseModel):
    symbol: str = "EURUSD"
    timeframe: str = "M15"
    start_date: str
    end_date: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "start_date": "2026-01-01",
                "end_date": "2026-06-01",
            }
        }
    )


class FeatureCalculateRequest(DateRangeRequest):
    sentiment: Sentiment = "NEUTRAL"
    usd_bias: UsdBias = "NEUTRAL"
    risk_sentiment: RiskSentiment = "NEUTRAL"
    cb_divergence: CbDivergence = "NEUTRAL"
    macro_evidence: dict[str, Any] = Field(default_factory=dict)


class DetectLatestRequest(BaseModel):
    symbol: str = "EURUSD"
    timeframe: str = "M15"
    sentiment: Sentiment = "NEUTRAL"
    usd_bias: UsdBias = "NEUTRAL"
    risk_sentiment: RiskSentiment = "NEUTRAL"
    cb_divergence: CbDivergence = "NEUTRAL"
    macro_evidence: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "sentiment": "NEUTRAL",
                "usd_bias": "NEUTRAL",
                "risk_sentiment": "NEUTRAL",
                "cb_divergence": "NEUTRAL",
            }
        }
    )


class FetchCandlesRequest(DateRangeRequest):
    pass


class BacktestRequest(DateRangeRequest):
    research_mode_preset: str = "Strict Validation"
    regime_filter: str = "ALL"
    strategy_filter: str = "ALL"
    risk_percent: float = Field(default=1.0, gt=0)
    rr: float = Field(default=2.0, gt=0)
    initial_equity: float = Field(default=100000.0, gt=0)
    sentiment: Sentiment = "NEUTRAL"
    usd_bias: UsdBias = "NEUTRAL"
    risk_sentiment: RiskSentiment = "NEUTRAL"
    cb_divergence: CbDivergence = "NEUTRAL"
    macro_evidence: dict[str, Any] = Field(default_factory=dict)
    use_killzone: bool = True
    use_spread_filter: bool = True
    use_sweeps: bool = True
    use_alpha: bool = True
    use_feature_cache: bool = True
    pattern_engine: dict[str, Any] = Field(default_factory=dict)
    statistical_regime: dict[str, Any] = Field(default_factory=dict)
    mt5_backtest: dict[str, Any] = Field(default_factory=dict)
    killzone_mode: Literal["score_only", "hard_filter"] = "score_only"
    spread_filter_mode: Literal["score_only", "hard_filter"] = "score_only"
    alpha_mode: Literal["score_only", "hard_minimum"] = "hard_minimum"
    strict_clean_trend: bool = True
    filters: dict[str, Any] = Field(default_factory=dict)
    costs: dict[str, Any] = Field(default_factory=dict)
    calibration: dict[str, Any] = Field(default_factory=dict)
    execution_assumption: dict[str, Any] = Field(default_factory=dict)
    regime_controls: dict[str, Any] = Field(default_factory=dict)
    strategy_controls: dict[str, Any] = Field(default_factory=dict)
    risk_controls: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
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
                "macro_evidence": {
                    "mode": "evidence",
                    "dxy_change_percent": 0.35,
                    "usd_basket_change_percent": 0.25,
                    "fed_rate_expectation_change_bp": 6,
                    "spx_change_percent": -0.7,
                    "vix_change_percent": 5,
                    "base_rate_expectation_change_bp": 12,
                    "quote_rate_expectation_change_bp": 0,
                    "high_impact_news": False
                },
                "use_killzone": True,
                "use_spread_filter": True,
                "use_sweeps": True,
                "use_alpha": True,
                "pattern_engine": {
                    "use_patterns": True,
                    "use_ict": True,
                    "use_fvg": True,
                    "use_order_blocks": True,
                    "use_bos": True,
                    "use_mss": True,
                    "use_liquidity_pools": True,
                    "use_round_numbers": True,
                    "use_vwap": True,
                    "use_mvwap": True,
                    "use_session_vwap": True,
                    "pattern_score_mode": "score_only",
                    "min_pattern_score": 2
                },
                "killzone_mode": "score_only",
                "spread_filter_mode": "score_only",
                "alpha_mode": "hard_minimum",
                "strict_clean_trend": True,
                "filters": {
                    "use_killzone": True,
                    "killzone_mode": "score_only",
                    "allowed_sessions": ["London", "NewYork", "Overlap"],
                    "use_spread_filter": True,
                    "max_spread_percentile": 70,
                    "use_alpha": True,
                    "min_alpha_score": 5,
                    "reject_m08_conflict": True,
                    "reject_m11_exhaustion": True,
                    "reject_rollover": True,
                    "reject_news": True,
                    "allow_news_regime_only": False
                },
                "costs": {
                    "cost_mode": "stress_adjusted",
                    "cost_r_per_trade": 0.05,
                    "commission_R": 0.0,
                    "slippage_points": 1.0,
                    "spread_round_trip_factor": 1.0,
                    "news_cost_multiplier": 2.0,
                    "rollover_block": True
                },
                "execution_assumption": {
                    "entry_price": "signal_close",
                    "same_candle_sl_tp": "sl_first",
                    "one_trade_at_a_time": True
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
                    "use_regime_hysteresis": True,
                    "hysteresis_confirm_bars": 3,
                    "hysteresis_confidence_margin": 0.15,
                    "danger_regime_ids": ["R40", "R10", "R30", "R39", "R09", "R23", "R24", "R38", "R50"]
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
                    "fixing_no_trade_mode": True
                },
                "risk_controls": {
                    "research_risk_percent": 1.0,
                    "funded_min_risk_percent": 0.25,
                    "funded_max_risk_percent": 0.50,
                    "max_trades_per_day": 3,
                    "max_consecutive_losses": 3
                },
            }
        }
    )


class WalkForwardRequest(BacktestRequest):
    train_months: int = Field(default=2, ge=1, le=36)
    test_months: int = Field(default=1, ge=1, le=12)
    step_months: int = Field(default=1, ge=1, le=12)
    min_test_trades: int = Field(default=20, ge=1)
    min_test_profit_factor: float = Field(default=1.1, gt=0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "start_date": "2025-11-01",
                "end_date": "2026-05-01",
                "regime_filter": "R01",
                "strategy_filter": "T1",
                "risk_percent": 1.0,
                "rr": 2.0,
                "initial_equity": 100000,
                "sentiment": "NEUTRAL",
                "usd_bias": "NEUTRAL",
                "risk_sentiment": "NEUTRAL",
                "cb_divergence": "NEUTRAL",
                "train_months": 2,
                "test_months": 1,
                "step_months": 1,
                "min_test_trades": 20,
                "min_test_profit_factor": 1.1,
                "filters": {
                    "use_killzone": True,
                    "killzone_mode": "hard_filter",
                    "allowed_sessions": ["London", "NewYork", "Overlap"],
                    "use_spread_filter": True,
                    "max_spread_percentile": 70,
                    "use_alpha": True,
                    "min_alpha_score": 7,
                },
            }
        }
    )


class ApiError(BaseModel):
    detail: str
    context: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    app: str
    scope: str
    order_execution: bool

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "app": "quant_forex_V10",
                "scope": "40-regime Tab 1 research API only",
                "order_execution": False,
            }
        }
    )


class MT5ConnectResponse(BaseModel):
    connected: bool
    account: dict[str, Any] | None = None
    read_only: bool | None = None
    message: str | None = None
    error: str | None = None
    details: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "connected": True,
                    "account": {"login": 123456, "server": "Demo-Server", "balance": 10000},
                    "read_only": True,
                    "message": "MT5 connected in read-only mode. No order execution endpoints exist.",
                },
                {
                    "connected": False,
                    "error": "MT5 terminal not connected or credentials invalid.",
                    "details": "Initialize failed",
                },
            ]
        }
    )


class SymbolsResponse(BaseModel):
    symbols: list[str]
    error: str | None = None

    model_config = ConfigDict(json_schema_extra={"example": {"symbols": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]}})


class FetchCandlesResponse(BaseModel):
    saved: int
    symbol: str | None = None
    timeframe: str | None = None
    error: str | None = None
    details: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"saved": 5000, "symbol": "EURUSD", "timeframe": "M15"}
        }
    )


class CandlesResponse(BaseModel):
    count: int
    candles: list[dict[str, Any]]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "count": 1,
                "candles": [
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "open": 1.1,
                        "high": 1.101,
                        "low": 1.099,
                        "close": 1.1005,
                        "tick_volume": 120,
                        "spread": 10,
                        "real_volume": 0,
                    }
                ],
            }
        }
    )


class FeatureCalculateResponse(BaseModel):
    saved: int
    cached: bool = False
    cache_status: dict[str, Any] = Field(default_factory=dict)
    latest_features: dict[str, Any]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "saved": 5000,
                "cached": False,
                "cache_status": {"status": "MISS", "cache_hit": False, "reason": "Calculated features and refreshed cache."},
                "latest_features": {
                    "timestamp": "2026-06-01T00:00:00Z",
                    "ema20": 1.1012,
                    "ema50": 1.1002,
                    "adx": 24.5,
                    "er": 0.32,
                    "atr_percentile": 55,
                    "session": "London",
                    "htf_bias": "bullish",
                    "ltf_bias": "bullish",
                },
            }
        }
    )


class ReferenceRegime(BaseModel):
    regime_id: str
    regime_name: str
    meaning: str
    direction: str
    allowed_strategies: list[str]
    blocked_strategies: list[str]
    risk: dict[str, Any]
    conditions: list[str]
    rules: list[str]


class ReferenceStrategy(BaseModel):
    strategy_id: str
    strategy_name: str
    regime: str
    direction: str
    category: str
    default_rr: float


class ReferenceModifier(BaseModel):
    id: str
    name: str
    hard_block: bool


class DetectLatestResponse(BaseModel):
    latest_features: dict[str, Any]
    feature_cache: dict[str, Any] = Field(default_factory=dict)
    active_regime: dict[str, Any]
    modifiers: dict[str, Any]
    hard_block: bool
    allowed_strategies: list[dict[str, Any]]
    explanation: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "latest_features": {"adx": 24.5, "er": 0.32, "session": "London"},
                "active_regime": {
                    "regime_id": "R01",
                    "regime_name": "Clean Bullish Trend",
                    "confidence": 0.82,
                    "is_active": True,
                    "allowed_strategies": ["T1", "T2", "T3"],
                },
                "modifiers": {"modifiers": ["M04", "M12"], "hard_block": False, "hard_block_reasons": [], "reasons": ["London kill zone active."]},
                "hard_block": False,
                "allowed_strategies": [{"strategy_id": "T1", "strategy_name": "EMA20 Pullback Buy"}],
                "explanation": "R01 Clean Bullish Trend was evaluated with confidence 0.82.",
            }
        }
    )


class BacktestRunResponse(BaseModel):
    run_id: str
    mode_preset: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any]
    regime_performance: list[dict[str, Any]]
    strategy_performance: list[dict[str, Any]]
    combination_performance: list[dict[str, Any]]
    unique_combination_performance: list[dict[str, Any]] = Field(default_factory=list)
    modifier_impact: list[dict[str, Any]] = Field(default_factory=list)
    session_performance: list[dict[str, Any]] = Field(default_factory=list)
    monthly_performance: list[dict[str, Any]] = Field(default_factory=list)
    pattern_performance: list[dict[str, Any]] = Field(default_factory=list)
    pattern_summary: dict[str, Any] = Field(default_factory=dict)
    mae_mfe_analysis: dict[str, Any] = Field(default_factory=dict)
    mt5_model_comparison: list[dict[str, Any]] = Field(default_factory=list)
    cost_summary: dict[str, Any] = Field(default_factory=dict)
    calibration_summary: dict[str, Any] = Field(default_factory=dict)
    spread_slippage_diagnostics: dict[str, Any] = Field(default_factory=dict)
    data_health: dict[str, Any] = Field(default_factory=dict)
    feature_summary: dict[str, Any] = Field(default_factory=dict)
    regime_confidence: list[dict[str, Any]] = Field(default_factory=list)
    skipped_setups: list[dict[str, Any]] = Field(default_factory=list)
    equity_curve: list[dict[str, Any]] = Field(default_factory=list)
    drawdown_curve: list[dict[str, Any]] = Field(default_factory=list)
    approval_checklist: list[dict[str, Any]] = Field(default_factory=list)
    trades: list[dict[str, Any]]
    explanation: dict[str, list[str]]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "run_id": "uuid",
                "summary": {
                    "total_trades": 120,
                    "win_rate": 0.43,
                    "profit_factor": 1.32,
                    "expectancy_R": 0.16,
                    "max_drawdown_R": -4.2,
                    "max_losing_streak": 5,
                    "initial_equity": 100000,
                    "ending_equity": 101250,
                    "net_profit": 1250,
                    "gross_profit": 4200,
                    "gross_loss": -2950,
                    "roi_percent": 12.5,
                    "best_regime": "Clean Bullish Trend",
                    "worst_regime": "Balanced Range / Liquidity Sweep",
                },
                "regime_performance": [],
                "strategy_performance": [],
                "combination_performance": [],
                "trades": [],
                "explanation": {"what_worked": [], "what_failed": [], "warnings": []},
            }
        }
    )


class BacktestStoredResponse(BaseModel):
    run_id: str
    summary: dict[str, Any]
    regime_performance: list[dict[str, Any]]
    strategy_performance: list[dict[str, Any]]
    combination_performance: list[dict[str, Any]]
    unique_combination_performance: list[dict[str, Any]] = Field(default_factory=list)
    modifier_impact: list[dict[str, Any]] = Field(default_factory=list)
    session_performance: list[dict[str, Any]] = Field(default_factory=list)
    monthly_performance: list[dict[str, Any]] = Field(default_factory=list)
    pattern_performance: list[dict[str, Any]] = Field(default_factory=list)
    pattern_summary: dict[str, Any] = Field(default_factory=dict)
    mae_mfe_analysis: dict[str, Any] = Field(default_factory=dict)
    mt5_model_comparison: list[dict[str, Any]] = Field(default_factory=list)
    cost_summary: dict[str, Any] = Field(default_factory=dict)
    calibration_summary: dict[str, Any] = Field(default_factory=dict)
    spread_slippage_diagnostics: dict[str, Any] = Field(default_factory=dict)
    data_health: dict[str, Any] = Field(default_factory=dict)
    feature_summary: dict[str, Any] = Field(default_factory=dict)
    regime_confidence: list[dict[str, Any]] = Field(default_factory=list)
    skipped_setups: list[dict[str, Any]] = Field(default_factory=list)
    equity_curve: list[dict[str, Any]] = Field(default_factory=list)
    drawdown_curve: list[dict[str, Any]] = Field(default_factory=list)
    approval_checklist: list[dict[str, Any]] = Field(default_factory=list)
    explanation: dict[str, list[str]]


class WalkForwardResponse(BaseModel):
    summary: dict[str, Any]
    windows: list[dict[str, Any]]
    warnings: list[str] = Field(default_factory=list)
    request: dict[str, Any]


class OutOfSampleRequest(BacktestRequest):
    split_date: str | None = None
    oos_percent: float = Field(default=30.0, ge=5, le=80)
    min_oos_trades: int = Field(default=20, ge=1)
    min_oos_profit_factor: float = Field(default=1.1, gt=0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "start_date": "2025-11-01",
                "end_date": "2026-05-01",
                "regime_filter": "R01",
                "strategy_filter": "T1",
                "risk_percent": 1.0,
                "rr": 2.0,
                "initial_equity": 100000,
                "sentiment": "NEUTRAL",
                "usd_bias": "NEUTRAL",
                "risk_sentiment": "NEUTRAL",
                "cb_divergence": "NEUTRAL",
                "split_date": None,
                "oos_percent": 30,
                "min_oos_trades": 20,
                "min_oos_profit_factor": 1.1,
                "filters": {
                    "use_killzone": True,
                    "killzone_mode": "hard_filter",
                    "allowed_sessions": ["London", "NewYork", "Overlap"],
                    "use_spread_filter": True,
                    "max_spread_percentile": 70,
                    "use_alpha": True,
                    "min_alpha_score": 7,
                },
            }
        }
    )


class OutOfSampleResponse(BaseModel):
    summary: dict[str, Any]
    in_sample: dict[str, Any]
    out_of_sample: dict[str, Any]
    comparison: dict[str, Any]
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    request: dict[str, Any]


class PortfolioBacktestRequest(BacktestRequest):
    symbols: list[str] = Field(default_factory=lambda: ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
    timeframes: list[str] = Field(default_factory=lambda: ["M15", "M5", "H1"])
    max_legs: int = Field(default=60, ge=1, le=200)
    portfolio_risk: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbols": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
                "timeframes": ["M15", "M5", "H1"],
                "symbol": "EURUSD",
                "timeframe": "M15",
                "start_date": "2025-11-01",
                "end_date": "2026-05-01",
                "regime_filter": "ALL",
                "strategy_filter": "ALL",
                "risk_percent": 1.0,
                "rr": 2.0,
                "initial_equity": 100000,
                "max_legs": 12,
                "portfolio_risk": {
                    "max_drawdown_R": 12,
                    "max_symbol_trade_share": 0.5,
                    "max_currency_exposure_share": 0.65,
                    "min_symbols_with_trades": 2,
                },
                "filters": {
                    "use_killzone": True,
                    "killzone_mode": "score_only",
                    "allowed_sessions": ["London", "NewYork", "Overlap"],
                    "use_spread_filter": True,
                    "max_spread_percentile": 70,
                    "use_alpha": True,
                    "min_alpha_score": 5,
                },
            }
        }
    )


class PortfolioBacktestResponse(BaseModel):
    summary: dict[str, Any]
    legs: list[dict[str, Any]]
    symbol_performance: list[dict[str, Any]]
    timeframe_performance: list[dict[str, Any]]
    symbol_timeframe_matrix: list[dict[str, Any]]
    correlation: dict[str, Any]
    concentration_warnings: list[str] = Field(default_factory=list)
    risk_diagnostics: dict[str, Any] = Field(default_factory=dict)
    regime_robustness: list[dict[str, Any]]
    equity_curve: list[dict[str, Any]]
    drawdown_curve: list[dict[str, Any]]
    warnings: list[str] = Field(default_factory=list)
    request: dict[str, Any]


class OptimizerGridRequest(BacktestRequest):
    grid: dict[str, Any] = Field(default_factory=dict)
    max_combinations: int = Field(default=50, ge=1, le=500)
    min_trades: int = Field(default=30, ge=1)
    min_profit_factor: float = Field(default=1.2, gt=0)
    max_drawdown_r: float = Field(default=10.0, gt=0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
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
            }
        }
    )


class OptimizerGridResponse(BaseModel):
    summary: dict[str, Any]
    results: list[dict[str, Any]]
    top_candidates: list[dict[str, Any]]
    warnings: list[str] = Field(default_factory=list)
    request: dict[str, Any]


class ABExperimentVariant(BaseModel):
    label: str
    changes: dict[str, Any] = Field(default_factory=dict)


class ABExperimentRequest(BaseModel):
    name: str = "Regime A/B Experiment"
    hypothesis: str = ""
    baseline_label: str = "Baseline"
    base_payload: dict[str, Any]
    variants: list[ABExperimentVariant]
    decision_rules: dict[str, Any] = Field(default_factory=dict)
    persist: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "R01 T1 strict filter test",
                "hypothesis": "Hard killzone and stricter alpha should reduce drawdown without killing expectancy.",
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
                    {
                        "label": "Hard killzone + alpha 8",
                        "changes": {
                            "killzone_mode": "hard_filter",
                            "filters": {"killzone_mode": "hard_filter", "min_alpha_score": 8},
                        },
                    }
                ],
                "decision_rules": {
                    "min_trades": 30,
                    "min_profit_factor": 1.2,
                    "min_expectancy_R": 0.0,
                    "min_expectancy_improvement_R": 0.02,
                    "max_drawdown_R": 12,
                    "max_drawdown_worsening_R": 2,
                },
            }
        }
    )


class ABExperimentResponse(BaseModel):
    experiment_id: str
    created_at: str
    summary: dict[str, Any]
    baseline: dict[str, Any]
    variants: list[dict[str, Any]]
    comparison: list[dict[str, Any]]
    warnings: list[str] = Field(default_factory=list)
    request: dict[str, Any]


class CalibrationProfilesResponse(BaseModel):
    profiles: list[dict[str, Any]]
    core_regimes: list[str]
    notes: list[str] = Field(default_factory=list)


class MonteCarloRequest(BacktestRequest):
    simulations: int = Field(default=1000, ge=1, le=10000)
    sample_mode: str = Field(default="bootstrap", pattern="^(bootstrap|shuffle)$")
    seed: int | None = 42
    min_trades: int = Field(default=30, ge=1)
    max_total_drawdown_percent: float = Field(default=10.0, gt=0)
    max_losing_streak_limit: int = Field(default=5, ge=1)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
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
            }
        }
    )


class MonteCarloResponse(BaseModel):
    summary: dict[str, Any]
    observed: dict[str, Any]
    distribution: dict[str, Any]
    equity_fan: list[dict[str, Any]]
    risk_of_ruin: dict[str, Any]
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    request: dict[str, Any]


class MacroEvidenceRequest(BaseModel):
    usd_bias: UsdBias = "NEUTRAL"
    risk_sentiment: RiskSentiment = "NEUTRAL"
    cb_divergence: CbDivergence = "NEUTRAL"
    macro_evidence: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "usd_bias": "NEUTRAL",
                "risk_sentiment": "NEUTRAL",
                "cb_divergence": "NEUTRAL",
                "macro_evidence": {
                    "mode": "evidence",
                    "dxy_change_percent": 0.35,
                    "usd_basket_change_percent": 0.25,
                    "fed_rate_expectation_change_bp": 6,
                    "us_yield_change_bp": 4,
                    "spx_change_percent": -0.7,
                    "vix_change_percent": 5,
                    "jpy_strength_score": 1,
                    "base_rate_expectation_change_bp": 12,
                    "quote_rate_expectation_change_bp": 0,
                    "high_impact_news": False,
                    "minutes_to_news": 9999,
                    "minutes_since_news": 9999,
                },
            }
        }
    )


class MacroImportCsvRequest(BaseModel):
    csv_text: str = Field(..., min_length=1)
    source: str = "csv_upload"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source": "macro_research_csv",
                "csv_text": (
                    "timestamp,symbol,dxy_change_percent,usd_basket_change_percent,us_yield_change_bp,"
                    "fed_rate_expectation_change_bp,spx_change_percent,vix_change_percent,gold_change_percent,"
                    "jpy_strength_score,chf_strength_score,base_rate_expectation_change_bp,"
                    "quote_rate_expectation_change_bp,high_impact_news,minutes_to_news,minutes_since_news\n"
                    "2026-01-02T12:00:00Z,EURUSD,0.35,0.25,6,6,-0.7,5,0.8,1,0,12,0,false,9999,9999\n"
                ),
            }
        }
    )


class MacroImportUrlRequest(BaseModel):
    url: str = Field(..., min_length=8)
    source: str = "macro_feed_url"
    feed_type: Literal["macro", "news", "cross_pair"] = "macro"
    feed_format: Literal["auto", "csv", "json"] = "auto"
    timeout_seconds: int = Field(default=15, ge=1, le=60)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://example.com/macro_evidence.csv",
                "source": "broker_or_research_feed",
                "feed_type": "macro",
                "feed_format": "auto",
                "timeout_seconds": 15,
            }
        }
    )


class MacroImportFeedRequest(BaseModel):
    feed_text: str = Field(..., min_length=1)
    source: str = "macro_feed_text"
    feed_type: Literal["macro", "news", "cross_pair"] = "macro"
    feed_format: Literal["csv", "json"] = "csv"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source": "economic_calendar_json",
                "feed_type": "news",
                "feed_format": "json",
                "feed_text": '[{"timestamp":"2026-01-02T13:30:00Z","currency":"USD","event":"NFP","impact":"High","minutes_to_news":15}]',
            }
        }
    )


class CrossPairEvidenceRequest(DateRangeRequest):
    symbols: list[str] = Field(default_factory=lambda: ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD", "EURJPY", "GBPJPY"])
    source: str = "cross_pair_candles"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "start_date": "2026-01-01",
                "end_date": "2026-06-01",
                "symbols": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD", "EURJPY", "GBPJPY"],
                "source": "saved_mt5_candles_cross_pair",
            }
        }
    )


class CotImportRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "EURJPY", "GBPJPY", "AUDJPY"])
    as_of: str | None = None
    source: str = "cftc_tff_cot"
    report_type: Literal["Combined", "FutOnly"] = "Combined"
    timeout_seconds: int = Field(default=20, ge=1, le=60)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbols": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"],
                "as_of": "2026-05-19",
                "source": "cftc_tff_cot",
                "report_type": "Combined",
                "timeout_seconds": 20,
            }
        }
    )


class MacroImportCsvResponse(BaseModel):
    saved: int
    rows_received: int
    source: str
    columns_expected: list[str]
    latest: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class MacroEvidenceResponse(BaseModel):
    mode: str
    source: str
    usd_bias: str
    risk_sentiment: str
    cb_divergence: str
    news_flag: bool
    confidence: dict[str, Any]
    scores: dict[str, Any]
    reasons: list[str]
    warnings: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    activation_allowed: dict[str, bool] = Field(default_factory=dict)
    activation_threshold: float = 0.50
    input_coverage: dict[str, Any] = Field(default_factory=dict)
    activation_table: list[dict[str, Any]] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    quality_status: str = "NO_EVIDENCE"
    recommendations: list[str] = Field(default_factory=list)


class MacroDiagnosticsResponse(BaseModel):
    status: str
    pipeline_ready: bool
    symbol: str
    start_date: str | None = None
    end_date: str | None = None
    as_of: str | None = None
    history_count: int
    latest_row: dict[str, Any] | None = None
    resolved: dict[str, Any]
    input_coverage: dict[str, Any] = Field(default_factory=dict)
    activation_table: list[dict[str, Any]] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class MT5ReportImportRequest(BaseModel):
    report_text: str = Field(..., min_length=1)
    file_name: str = "pasted_mt5_report"
    test_model: Literal["one_min_ohlc", "every_tick", "every_tick_real_ticks", "unknown"] = "every_tick_real_ticks"
    run_id: str | None = None
    symbol: str | None = None
    timeframe: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    initial_equity: float = Field(default=100000.0, gt=0)
    risk_percent: float = Field(default=1.0, gt=0)
    max_deals_returned: int = Field(default=500, ge=1, le=5000)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
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
            }
        }
    )


class MT5ReportImportResponse(BaseModel):
    import_id: str
    run_id: str | None = None
    created_at: str
    file_name: str | None = None
    test_model: str
    symbol: str | None = None
    timeframe: str | None = None
    summary: dict[str, Any]
    model_comparison_row: dict[str, Any]
    deals: list[dict[str, Any]]
    warnings: list[str] = Field(default_factory=list)


class MT5ModelComparisonImportRequest(BaseModel):
    reports: dict[str, str] = Field(default_factory=dict)
    run_id: str | None = None
    symbol: str | None = None
    timeframe: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    initial_equity: float = Field(default=100000.0, gt=0)
    risk_percent: float = Field(default=1.0, gt=0)
    max_deals_returned: int = Field(default=500, ge=1, le=5000)
    thresholds: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "start_date": "2026-01-01",
                "end_date": "2026-06-01",
                "initial_equity": 100000,
                "risk_percent": 1.0,
                "reports": {
                    "one_min_ohlc": "Time,Symbol,Type,Volume,Price,Profit,Balance,Comment\n2026-01-02 10:15,EURUSD,buy,0.10,1.10000,120.50,100120.50,T1\n",
                    "every_tick": "Time,Symbol,Type,Volume,Price,Profit,Balance,Comment\n2026-01-02 10:15,EURUSD,buy,0.10,1.10000,100.50,100100.50,T1\n",
                    "every_tick_real_ticks": "Time,Symbol,Type,Volume,Price,Profit,Balance,Comment\n2026-01-02 10:15,EURUSD,buy,0.10,1.10000,90.50,100090.50,T1\n",
                },
                "thresholds": {"min_trades": 30, "min_profit_factor": 1.10, "max_pf_drift": 0.35},
            }
        }
    )


class MT5ModelComparisonImportResponse(BaseModel):
    comparison_id: str
    created_at: str
    status: str
    symbol: str | None = None
    timeframe: str | None = None
    run_id: str | None = None
    rows: list[dict[str, Any]]
    checks: list[dict[str, Any]]
    missing_models: list[str] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)
    imports: dict[str, Any] = Field(default_factory=dict)
    stability: dict[str, Any]
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    decision: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[str] = Field(default_factory=list)
    thresholds: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class BrokerCostCalibrationRequest(BaseModel):
    symbol: str | None = None
    test_model: str = "every_tick_real_ticks"
    include_all_models: bool = False
    import_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=25, ge=1, le=200)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "EURUSD",
                "test_model": "every_tick_real_ticks",
                "include_all_models": False,
                "import_ids": [],
                "limit": 25,
            }
        }
    )


class BrokerCostCalibrationResponse(BaseModel):
    status: str
    sample_count: int
    report_count: int
    real_tick_report_count: int
    symbol: str
    model_filter: str
    summary: dict[str, Any]
    recommended_costs: dict[str, Any]
    session_curve: list[dict[str, Any]] = Field(default_factory=list)
    reports: list[dict[str, Any]] = Field(default_factory=list)
    sample_preview: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class MT5TesterRunRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    terminal_path: str | None = None
    expert: str = "QuantForexV10_ResearchEA.ex5"
    launch_terminal: bool = True
    wait_for_report: bool = False
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    shutdown_terminal: bool = True
    visual: bool = False
    optimization: bool = False
    execution_mode: int = 0
    forward_mode: int = 0
    model_code: int | None = None
    leverage: int = Field(default=100, ge=1)
    currency: str = "USD"
    python_run_id: str | None = None
    use_python_signals: bool = True
    copy_python_signals_to_common: bool = True
    python_signal_file: str | None = None
    max_deals_returned: int = Field(default=500, ge=1, le=5000)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
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
                    "mt5_backtest": {"test_model": "every_tick_real_ticks", "use_python_signals": True},
                    "pattern_engine": {"use_patterns": True, "use_fvg": True, "use_vwap": True},
                    "filters": {"killzone_mode": "hard_filter", "spread_filter_mode": "hard_filter"},
                },
                "terminal_path": "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
                "expert": "QuantForexV10_ResearchEA.ex5",
                "launch_terminal": True,
                "wait_for_report": False,
                "timeout_seconds": 120,
                "use_python_signals": True,
            }
        }
    )


class MT5TesterRunResponse(BaseModel):
    run_id: str
    created_at: str
    status: str
    order_execution: bool
    payload_received: dict[str, Any]
    bridge: dict[str, Any]
    tester_config: dict[str, Any]
    terminal_path: str | None = None
    command: list[str] = Field(default_factory=list)
    process_id: int | None = None
    report_wait: dict[str, Any] = Field(default_factory=dict)
    report_found_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
    report_import: dict[str, Any] | None = None
    python_signal_source: dict[str, Any] | None = None


class MT5RealTickWorkflowRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    python_run_id: str | None = None
    reports: dict[str, str] = Field(default_factory=dict)
    thresholds: dict[str, Any] = Field(default_factory=dict)
    terminal_path: str | None = None
    expert: str = "QuantForexV10_ResearchEA.ex5"
    launch_terminal: bool = False
    wait_for_report: bool = False
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    shutdown_terminal: bool = True
    visual: bool = False
    use_python_signals: bool = True
    copy_python_signals_to_common: bool = True
    max_deals_returned: int = Field(default=500, ge=1, le=5000)
    parity_tolerances: dict[str, Any] = Field(default_factory=dict)
    max_mismatches_returned: int = Field(default=50, ge=1, le=500)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
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
                    "filters": {"killzone_mode": "hard_filter", "spread_filter_mode": "hard_filter"},
                },
                "launch_terminal": False,
                "reports": {
                    "one_min_ohlc": "Time,Symbol,Type,Volume,Price,Profit,Balance,Comment\n...",
                    "every_tick": "Time,Symbol,Type,Volume,Price,Profit,Balance,Comment\n...",
                    "every_tick_real_ticks": "Time,Symbol,Type,Volume,Price,Profit,Balance,Comment\n...",
                },
                "thresholds": {"min_trades": 30, "min_profit_factor": 1.10, "max_pf_drift": 0.35},
            }
        }
    )


class MT5RealTickWorkflowResponse(BaseModel):
    workflow_id: str
    created_at: str
    status: str
    order_execution: bool
    candidate: dict[str, Any]
    models: list[dict[str, Any]]
    reports_supplied: dict[str, bool]
    generated_report_sources: dict[str, str] = Field(default_factory=dict)
    readiness: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[str] = Field(default_factory=list)
    quick_start: list[dict[str, str]] = Field(default_factory=list)
    model_cards: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[dict[str, Any]]
    tester_runs: dict[str, Any]
    model_comparison: dict[str, Any] | None = None
    parity_check: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class MT5ParityRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    python_run_id: str | None = None
    python_result: dict[str, Any] = Field(default_factory=dict)
    python_trades: list[dict[str, Any]] = Field(default_factory=list)
    mt5_import_id: str | None = None
    mt5_import: dict[str, Any] = Field(default_factory=dict)
    mt5_trades: list[dict[str, Any]] = Field(default_factory=list)
    tolerances: dict[str, Any] = Field(default_factory=dict)
    max_mismatches_returned: int = Field(default=50, ge=1, le=500)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
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
                "python_run_id": "optional-saved-run-id",
                "mt5_import_id": "optional-imported-mt5-report-id",
                "tolerances": {
                    "price_tolerance": 0.00001,
                    "time_tolerance_seconds": 60,
                    "result_R_tolerance": 0.05,
                    "profit_tolerance": 1.0,
                },
            }
        }
    )


class MT5ParityResponse(BaseModel):
    status: str
    created_at: str
    symbol: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any]
    checks: list[dict[str, Any]]
    failed_checks: list[dict[str, Any]]
    mismatches: list[dict[str, Any]]
    warnings: list[str] = Field(default_factory=list)
    python_context: dict[str, Any] = Field(default_factory=dict)
    mt5_context: dict[str, Any] = Field(default_factory=dict)


class MT5ParityCompletionRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    python_run_id: str | None = None
    report_text: str | None = None
    mt5_import_id: str | None = None
    file_name: str = "pasted_mt5_parity_report.csv"
    test_model: Literal["one_min_ohlc", "every_tick", "every_tick_real_ticks", "unknown"] = "every_tick_real_ticks"
    prepare_tester_config: bool = True
    launch_terminal: bool = False
    wait_for_report: bool = False
    terminal_path: str | None = None
    expert: str = "QuantForexV10_ResearchEA.ex5"
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    shutdown_terminal: bool = True
    visual: bool = False
    tolerances: dict[str, Any] = Field(default_factory=dict)
    max_deals_returned: int = Field(default=5000, ge=1, le=20000)
    max_mismatches_returned: int = Field(default=100, ge=1, le=500)
    required_symbol: str = "EURUSD"
    required_timeframe: str = "M15"


class MT5ParityCompletionResponse(BaseModel):
    status: str
    created_at: str
    order_execution: bool = False
    python_run_id: str
    candidate: dict[str, Any]
    institutional_verdict: dict[str, Any]
    checklist: list[dict[str, Any]]
    packet: dict[str, Any]
    tester_run: dict[str, Any] | None = None
    mt5_import: dict[str, Any] | None = None
    parity_check: dict[str, Any] | None = None
    next_actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MT5ParityPacketResponse(BaseModel):
    packet_id: str
    packet_hash: str
    created_at: str
    python_run_id: str
    candidate: dict[str, Any]
    summary: dict[str, Any]
    expected_trade_count: int
    expected_signals: list[dict[str, Any]]
    expected_signals_csv: str
    mt5_ea_requirements: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class MT5ParityRunReportRequest(BaseModel):
    python_run_id: str
    mt5_import_id: str | None = None
    report_text: str | None = None
    file_name: str = "pasted_mt5_signal_or_report.csv"
    test_model: Literal["one_min_ohlc", "every_tick", "every_tick_real_ticks", "unknown"] = "every_tick_real_ticks"
    tolerances: dict[str, Any] = Field(default_factory=dict)
    max_mismatches_returned: int = Field(default=50, ge=1, le=500)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "python_run_id": "saved-python-backtest-run-id",
                "test_model": "every_tick_real_ticks",
                "report_text": "parity_index,parity_hash,entry_time,symbol,regime_id,strategy_id,direction,entry,sl,tp,exit_price,result_R,profit,comment\n0,abc123,2026-01-02 10:15,EURUSD,R01,T1,long,1.10000,1.09900,1.10200,1.10200,1.95,1950,R01|T1|PYIDX:0|PYHASH:abc123\n",
                "tolerances": {"price_tolerance": 0.00001, "time_tolerance_seconds": 60, "result_R_tolerance": 0.05, "profit_tolerance": 1.0},
            }
        }
    )


class OllamaReviewRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    backtest: dict[str, Any] = Field(default_factory=dict)
    mt5_comparison: dict[str, Any] = Field(default_factory=dict)
    mt5_tester: dict[str, Any] = Field(default_factory=dict)
    optimizer: dict[str, Any] = Field(default_factory=dict)
    walk_forward: dict[str, Any] = Field(default_factory=dict)
    monte_carlo: dict[str, Any] = Field(default_factory=dict)
    selected_regime: str | None = None
    model: str = "llama3.1:8b"
    ollama_url: str = "http://127.0.0.1:11434"
    use_ollama: bool = True
    timeout_seconds: int = Field(default=120, ge=5, le=600)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model": "llama3.1:8b",
                "ollama_url": "http://127.0.0.1:11434",
                "use_ollama": True,
                "payload": {"symbol": "EURUSD", "timeframe": "M15", "regime_filter": "R01", "strategy_filter": "T1"},
                "backtest": {"summary": {"total_trades": 120, "profit_factor": 1.22, "expectancy_R": 0.08}},
                "mt5_comparison": {"status": "MODEL_STABLE_APPROVED_FOR_REVIEW", "rows": []},
            }
        }
    )


class OllamaReviewResponse(BaseModel):
    review_id: str
    created_at: str
    model: str
    ollama_url: str
    used_ollama: bool
    status: str
    review: dict[str, Any]
    raw_response: str | None = None
    warnings: list[str] = Field(default_factory=list)
    context_used: dict[str, Any]


class FinalApprovalRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    backtest: dict[str, Any] = Field(default_factory=dict)
    optimizer: dict[str, Any] = Field(default_factory=dict)
    out_of_sample: dict[str, Any] = Field(default_factory=dict)
    walk_forward: dict[str, Any] = Field(default_factory=dict)
    monte_carlo: dict[str, Any] = Field(default_factory=dict)
    mt5_comparison: dict[str, Any] = Field(default_factory=dict)
    thresholds: dict[str, Any] = Field(default_factory=dict)
    auto_run_missing: bool = False

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "auto_run_missing": False,
                "payload": {"symbol": "EURUSD", "timeframe": "M15", "regime_filter": "R01", "strategy_filter": "T1"},
                "backtest": {"summary": {"total_trades": 120, "profit_factor": 1.22, "expectancy_R": 0.08, "max_drawdown_R": -6}},
                "out_of_sample": {"summary": {"status": "PASS", "stable": True}},
                "walk_forward": {"summary": {"stable": True, "pass_rate": 0.7}},
                "monte_carlo": {"summary": {"status": "PASS"}, "risk_of_ruin": {"drawdown_breach_probability": 0.06}},
                "mt5_comparison": {"status": "MODEL_STABLE_APPROVED_FOR_REVIEW", "rows": []},
            }
        }
    )


class FinalApprovalResponse(BaseModel):
    status: str
    decision: str
    passed_required: int
    failed_required: int
    total_required: int
    checks: list[dict[str, Any]]
    failed_checks: list[dict[str, Any]]
    candidate: dict[str, Any]
    thresholds: dict[str, Any]
    anti_overfit_gate: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    inputs_used: dict[str, Any]


class BacktestTradesResponse(BaseModel):
    run_id: str
    count: int
    trades: list[dict[str, Any]]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "run_id": "uuid",
                "count": 1,
                "trades": [
                    {
                        "entry_time": "2026-01-02T10:15:00Z",
                        "exit_time": "2026-01-02T12:00:00Z",
                        "regime_id": "R01",
                        "strategy_id": "T1",
                        "direction": "long",
                        "entry": 1.1,
                        "sl": 1.098,
                        "tp": 1.104,
                        "result_R": 1.95,
                        "profit": 195,
                        "alpha_score": 7,
                    }
                ],
            }
        }
    )


class ApiStructureEndpoint(BaseModel):
    method: str
    path: str
    purpose: str
    request_body: dict[str, Any] | None = None
    query_params: dict[str, Any] | None = None
    response_shape: dict[str, Any]


class ApiStructureResponse(BaseModel):
    base_url: str
    note: str
    endpoints: list[ApiStructureEndpoint]
