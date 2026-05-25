from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

from backend.database import save_candles


TIMEFRAME_MAP = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}

MT5_MODEL_ROWS = [
    ("one_min_ohlc", "1-Min OHLC"),
    ("every_tick", "Every Tick"),
    ("every_tick_real_ticks", "Real Ticks"),
]

NON_TESTER_SAFETY_CONFIRM = "I_UNDERSTAND_THIS_CAN_TRADE_LIVE"


PATTERN_INPUT_MAP = {
    "use_ict": "UseICT",
    "use_fvg": "UseFVG",
    "use_order_blocks": "UseOrderBlocks",
    "use_bos": "UseBOS",
    "use_mss": "UseMSS",
    "use_liquidity_pools": "UseLiquidityPools",
    "use_round_numbers": "UseRoundNumbers",
    "use_vwap": "UseVWAP",
    "use_moving_vwap": "UseMVWAP",
    "use_mvwap": "UseMVWAP",
    "use_session_vwap": "UseSessionVWAP",
    "min_pattern_score": "MinPatternScore",
    "pattern_score_mode": "PatternScoreMode",
    "fvg_min_size_atr": "FVGMinSizeATR",
    "fvg_max_age_bars": "FVGMaxAgeBars",
    "ob_displacement_body_ratio_min": "OBDisplacementBodyRatioMin",
    "ob_displacement_candle_range_atr_min": "OBDisplacementCandleRangeATRMin",
    "ob_max_age_bars": "OBMaxAgeBars",
    "vwap_reversion_distance_atr": "VWAPReversionDistanceATR",
    "bos_atr_buffer": "BOSATRBuffer",
    "near_round_number_tolerance_atr": "RoundNumberToleranceATR",
}


FILTER_INPUT_MAP = {
    "use_killzone": "UseKillzone",
    "killzone_mode": "KillzoneMode",
    "allowed_sessions": "AllowedSessions",
    "use_spread_filter": "UseSpreadFilter",
    "spread_filter_mode": "SpreadFilterMode",
    "max_spread_percentile": "MaxSpreadPercentile",
    "use_sweeps": "UseSweeps",
    "use_alpha": "UseAlpha",
    "alpha_mode": "AlphaMode",
    "min_alpha_score": "MinAlphaScore",
    "strict_clean_trend": "StrictCleanTrend",
    "strict_regime_validation": "StrictRegimeValidation",
    "reject_trend_weakening": "RejectTrendWeakening",
    "reject_low_er_clean_trend": "RejectLowERCleanTrend",
    "reject_adx_outside_clean_trend": "RejectADXOutsideCleanTrendBand",
    "reject_mtf_conflict_score": "RejectMTFConflictScore",
    "min_clean_trend_er": "MinCleanTrendER",
    "max_mtf_conflict_score": "MaxMTFConflictScore",
    "reject_m08_conflict": "RejectM08Conflict",
    "reject_m11_exhaustion": "RejectM11Exhaustion",
    "reject_news": "RejectNews",
    "reject_rollover": "RejectRollover",
}


def _load_mt5():
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError as exc:
        raise RuntimeError("MetaTrader5 package is not installed. Install requirements first.") from exc
    return mt5


def connect_mt5() -> dict[str, Any]:
    load_dotenv()
    mt5 = _load_mt5()
    path = os.getenv("MT5_PATH") or None
    initialized = mt5.initialize(path=path) if path else mt5.initialize()
    if not initialized:
        return {
            "connected": False,
            "error": "MT5 terminal not connected or credentials invalid.",
            "details": str(mt5.last_error()),
        }

    login = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    if login and password and server:
        if not mt5.login(int(login), password=password, server=server):
            return {
                "connected": False,
                "error": "MT5 terminal not connected or credentials invalid.",
                "details": str(mt5.last_error()),
            }

    account = mt5.account_info()
    return {
        "connected": True,
        "account": account._asdict() if account else None,
        "read_only": True,
        "message": "MT5 connected in read-only mode. No order execution endpoints exist.",
    }


def get_symbols() -> dict[str, Any]:
    mt5 = _load_mt5()
    if not mt5.initialize():
        return {"symbols": [], "error": "MT5 terminal not connected or credentials invalid."}
    symbols = mt5.symbols_get()
    return {"symbols": [s.name for s in symbols] if symbols else []}


def _mt5_timeframe(mt5, timeframe: str):
    attr = TIMEFRAME_MAP.get(timeframe.upper())
    if not attr:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return getattr(mt5, attr)


def _row_to_candle(row) -> dict[str, Any]:
    return {
        "timestamp": datetime.fromtimestamp(int(row["time"]), tz=timezone.utc).isoformat(),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "tick_volume": float(row["tick_volume"]),
        "spread": float(row["spread"]),
        "real_volume": float(row["real_volume"]),
    }


def fetch_candles(symbol: str, timeframe: str, start_date: str, end_date: str) -> dict[str, Any]:
    mt5 = _load_mt5()
    if not mt5.initialize():
        return {"saved": 0, "error": "MT5 terminal not connected or credentials invalid."}
    tf = _mt5_timeframe(mt5, timeframe)
    start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
    rates = mt5.copy_rates_range(symbol, tf, start, end)
    if rates is None:
        return {"saved": 0, "error": "MT5 terminal not connected or credentials invalid.", "details": str(mt5.last_error())}
    candles = [_row_to_candle(row) for row in rates]
    return {"saved": save_candles(symbol, timeframe, candles), "symbol": symbol, "timeframe": timeframe}


def fetch_recent_bars(symbol: str, timeframe: str, bars: int) -> dict[str, Any]:
    mt5 = _load_mt5()
    if not mt5.initialize():
        return {"saved": 0, "error": "MT5 terminal not connected or credentials invalid."}
    tf = _mt5_timeframe(mt5, timeframe)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
    if rates is None:
        return {"saved": 0, "error": "MT5 terminal not connected or credentials invalid.", "details": str(mt5.last_error())}
    candles = [_row_to_candle(row) for row in rates]
    return {"saved": save_candles(symbol, timeframe, candles), "symbol": symbol, "timeframe": timeframe}


def _flat_join(value: Any) -> Any:
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return value


def _ea_input_name(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _model_comparison_plan(payload: dict[str, Any], mt5_backtest: dict[str, Any]) -> list[dict[str, Any]]:
    requested = mt5_backtest.get("test_model") or payload.get("mt5_test_model")
    return [
        {
            "model": model,
            "model_name": label,
            "same_regime": payload.get("regime_filter"),
            "same_strategy": payload.get("strategy_filter"),
            "same_symbol": payload.get("symbol"),
            "same_timeframe": payload.get("timeframe"),
            "status": "CONFIG REQUESTED" if requested == model else "READY_TO_RUN",
            "trade_count": 0,
            "win_rate": 0,
            "profit_factor": 0,
            "expectancy_R": 0,
            "net_profit": 0,
            "note": "Run/import this MT5 Strategy Tester model to fill metrics.",
        }
        for model, label in MT5_MODEL_ROWS
    ]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _safety_requested(*sources: dict[str, Any]) -> tuple[bool, str]:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ("AllowNonTesterExecution", "allow_non_tester_execution"):
            if key in source and _truthy(source.get(key)):
                return True, key
    return False, ""


def build_mt5_backtest_bridge_response(request: dict[str, Any]) -> dict[str, Any]:
    payload = request.get("payload") if isinstance(request.get("payload"), dict) else request
    mt5_backtest = payload.get("mt5_backtest", {}) if isinstance(payload.get("mt5_backtest"), dict) else {}
    pattern_engine = payload.get("pattern_engine", {}) if isinstance(payload.get("pattern_engine"), dict) else {}
    statistical_regime = payload.get("statistical_regime", {}) if isinstance(payload.get("statistical_regime"), dict) else {}
    filters = payload.get("filters", {}) if isinstance(payload.get("filters"), dict) else {}
    strategy_execution = payload.get("strategy_execution", {}) if isinstance(payload.get("strategy_execution"), dict) else {}
    output_options = payload.get("output_options", {}) if isinstance(payload.get("output_options"), dict) else {}

    mt5_connection: dict[str, Any]
    symbol_info: dict[str, Any] | None = None
    try:
        mt5 = _load_mt5()
        initialized = mt5.initialize()
        mt5_connection = {
            "connected": bool(initialized),
            "last_error": str(mt5.last_error()) if not initialized else None,
        }
        if initialized:
            account = mt5.account_info()
            mt5_connection["account"] = account._asdict() if account else None
            info = mt5.symbol_info(str(payload.get("symbol", "")))
            symbol_info = info._asdict() if info else None
    except Exception as exc:
        mt5_connection = {"connected": False, "error": str(exc)}

    ea_inputs: dict[str, Any] = {
        "Symbol": payload.get("symbol"),
        "Timeframe": payload.get("timeframe"),
        "StartDate": payload.get("start_date"),
        "EndDate": payload.get("end_date"),
        "RegimeFilter": payload.get("regime_filter"),
        "StrategyFilter": payload.get("strategy_filter"),
        "RiskPercent": payload.get("risk_percent"),
        "RR": payload.get("rr"),
        "InitialEquity": payload.get("initial_equity"),
        "Sentiment": payload.get("sentiment"),
        "UsdBias": payload.get("usd_bias"),
        "RiskSentiment": payload.get("risk_sentiment"),
        "CbDivergence": payload.get("cb_divergence"),
        "AllowNonTesterExecution": False,
        "NonTesterSafetyConfirm": "",
    }
    for source in (pattern_engine, pattern_engine.get("ict_settings", {}) if isinstance(pattern_engine.get("ict_settings"), dict) else {}):
        for key, value in source.items():
            ea_inputs[PATTERN_INPUT_MAP.get(key, _ea_input_name(key))] = _flat_join(value)
    for key, value in statistical_regime.items():
        ea_inputs[_ea_input_name(key)] = _flat_join(value)
    for key, value in filters.items():
        ea_inputs[FILTER_INPUT_MAP.get(key, _ea_input_name(key))] = _flat_join(value)
    if mt5_backtest.get("use_python_signals") is not None:
        ea_inputs["UsePythonSignalCsv"] = _flat_join(mt5_backtest.get("use_python_signals"))
    if mt5_backtest.get("python_signal_file"):
        ea_inputs["PythonSignalCsvFile"] = _flat_join(mt5_backtest.get("python_signal_file"))
    if mt5_backtest.get("require_python_signal_csv") is not None:
        ea_inputs["RequirePythonSignalCsv"] = _flat_join(mt5_backtest.get("require_python_signal_csv"))
    for key, value in strategy_execution.items():
        ea_inputs[_ea_input_name(key)] = _flat_join(value)
    allow_non_tester, allow_source = _safety_requested(payload, mt5_backtest, filters, strategy_execution, ea_inputs)
    safety_warnings = [
        "MT5 safety: generated EA inputs keep AllowNonTesterExecution=false by default. The research EA is intended for Strategy Tester only.",
        f"MT5 safety: non-tester execution requires AllowNonTesterExecution=true and NonTesterSafetyConfirm={NON_TESTER_SAFETY_CONFIRM}.",
    ]
    if allow_non_tester:
        safety_warnings.append(
            f"DANGER: {allow_source}=true was requested. Outside Strategy Tester the EA can send demo/live orders. Use only a controlled demo environment and never funded/live accounts."
        )

    return {
        "status": "ok",
        "endpoint": "POST /api/mt5/backtest/run",
        "engine_requested": "mt5_strategy_tester",
        "engine_status": "bridge_response_config_prepared",
        "order_execution": False,
        "safety": {
            "tester_only_default": True,
            "allow_non_tester_execution": bool(allow_non_tester),
            "non_tester_confirmation_required": NON_TESTER_SAFETY_CONFIRM,
            "warnings": safety_warnings,
        },
        "mt5_connection": mt5_connection,
        "mt5_symbol_info": symbol_info,
        "mt5_strategy_tester": {
            "requested": True,
            "actual_tester_run_started": False,
            "reason": "The MetaTrader5 Python package can connect, read symbols, and fetch data, but it does not directly expose a Strategy Tester run API. This response prepares/validates the full MT5/EA input payload for the next tester-runner layer.",
            "test_model_requested": mt5_backtest.get("test_model") or payload.get("mt5_test_model"),
            "available_test_models": mt5_backtest.get("available_test_models", ["candle_close", "one_min_ohlc", "every_tick", "every_tick_real_ticks"]),
            "execution_quality": mt5_backtest.get("execution_quality"),
            "spread_mode": mt5_backtest.get("spread_mode"),
            "slippage_mode": mt5_backtest.get("slippage_mode"),
            "commission_mode": mt5_backtest.get("commission_mode"),
        },
        "mt5_model_comparison": _model_comparison_plan(payload, mt5_backtest),
        "payload_received": payload,
        "ea_inputs_prepared": ea_inputs,
        "pattern_engine_requested": pattern_engine,
        "statistical_regime_requested": statistical_regime,
        "filters_requested": filters,
        "strategy_execution_requested": strategy_execution,
        "output_options_requested": output_options,
        "unknown_fields_preserved": sorted(set(payload.keys()) - {
            "symbol", "timeframe", "start_date", "end_date", "regime_filter", "strategy_filter",
            "risk_percent", "rr", "initial_equity", "sentiment", "usd_bias", "risk_sentiment",
            "cb_divergence", "mt5_backtest", "pattern_engine", "statistical_regime", "filters", "strategy_execution",
            "output_options",
        }),
        "next_required_layer": {
            "mt5_ea_required": True,
            "ea_must_define_inputs": sorted(ea_inputs.keys()),
            "runner_required": "Use /api/mt5/tester/run with the compiled QuantForexV10_ResearchEA.ex5, or import an existing MT5 tester report through /api/mt5/report/import.",
            "expected_future_response": [
                "mt5_report",
                "mt5_model_used",
                "patterns_detected_per_trade",
                "pattern_score",
                "final_score",
                "strategy_tester_deals",
                "what_worked_failed",
            ],
        },
    }
