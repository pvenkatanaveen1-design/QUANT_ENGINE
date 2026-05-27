from __future__ import annotations

from typing import Any

import pandas as pd


INSTITUTIONAL_SOURCES = {
    "institutional_order_flow",
    "prime_broker_ticks",
    "ecn_l2_order_book",
    "reuters_ebs_tick",
    "bloomberg_bpipe_tick",
}
BROKER_TICK_SOURCES = {"mt5_real_ticks", "mt5_every_tick"}
EXTERNAL_CANDLE_SOURCES = {"dukascopy_ticks", "alpha_vantage_fx", "twelve_data_fx", "polygon_fx", "csv_import", "cme_fx_futures_proxy"}
RETAIL_SOURCES = {"mt5_retail_candles", "sqlite_mt5_candles", "retail_broker_candles", *EXTERNAL_CANDLE_SOURCES}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _coverage(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame:
        return 0.0
    series = pd.to_numeric(frame[column], errors="coerce")
    return float(series.notna().mean()) if len(series) else 0.0


def _positive_coverage(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame:
        return 0.0
    series = pd.to_numeric(frame[column], errors="coerce")
    return float((series.fillna(0) > 0).mean()) if len(series) else 0.0


def _source_base_score(source: str) -> int:
    if source in INSTITUTIONAL_SOURCES:
        return 78
    if source in BROKER_TICK_SOURCES:
        return 58
    if source in EXTERNAL_CANDLE_SOURCES:
        return 48
    if source in RETAIL_SOURCES:
        return 35
    return 30


def _grade(score: int, true_order_flow: bool, broker_tick: bool) -> tuple[str, str]:
    if true_order_flow and score >= 85:
        return "INSTITUTIONAL_ORDER_FLOW_READY", "Institutional research grade"
    if broker_tick and score >= 65:
        return "BROKER_REAL_TICK_VALIDATED", "Broker execution-validation grade"
    if score >= 45:
        return "RETAIL_PROXY_RESEARCH", "Retail/proxy research grade"
    return "DATA_INSUFFICIENT", "Insufficient data grade"


def evaluate_institutional_data_quality(
    candles: pd.DataFrame,
    features: pd.DataFrame,
    trades: list[dict[str, Any]],
    request: dict[str, Any],
    mt5_model_comparison: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score whether the dataset is candle-only, broker-tick validated, or institutional/order-flow ready.

    This does not fabricate institutional data. It makes the data gap explicit and gives the UI a
    gateable readiness model for research versus semi-manual review.
    """
    controls = request.get("data_source_controls") if isinstance(request.get("data_source_controls"), dict) else {}
    source = str(controls.get("data_source") or "mt5_retail_candles")
    declared_provider = str(controls.get("provider") or "MT5 / SQLite")
    has_l2 = _bool(controls.get("has_l2_order_book"))
    has_true_order_flow = _bool(controls.get("has_true_order_flow")) or source in INSTITUTIONAL_SOURCES or has_l2
    has_external_tick = _bool(controls.get("has_external_tick_data")) or source in INSTITUTIONAL_SOURCES
    has_broker_real_ticks = source in BROKER_TICK_SOURCES or any(
        row.get("model") == "every_tick_real_ticks" and row.get("status") in {"PASS", "IMPORTED"}
        for row in (mt5_model_comparison or [])
    )
    require_institutional = _bool(controls.get("require_institutional_order_flow"))
    require_real_tick = _bool(controls.get("require_real_tick_validation"), True) and not has_true_order_flow

    spread_coverage = _positive_coverage(candles, "spread")
    tick_volume_coverage = _positive_coverage(candles, "tick_volume")
    real_volume_coverage = _positive_coverage(candles, "real_volume")
    ohlc_coverage = min(_coverage(candles, col) for col in ["open", "high", "low", "close"]) if not candles.empty else 0.0
    bad_data_rows = int(pd.to_numeric(features.get("data_quality_bad_data_flag"), errors="coerce").fillna(0).sum()) if not features.empty else 0
    warmup_rows = int(pd.to_numeric(features.get("data_quality_warmup_flag"), errors="coerce").fillna(0).sum()) if not features.empty else 0
    trade_count = len(trades)

    score = _source_base_score(source)
    score += 12 if has_true_order_flow else 0
    score += 8 if has_external_tick else 0
    score += 8 if has_broker_real_ticks else 0
    score += 6 if spread_coverage >= 0.95 else 2 if spread_coverage >= 0.50 else -8
    score += 4 if tick_volume_coverage >= 0.95 else 1 if tick_volume_coverage >= 0.50 else -4
    score += 6 if real_volume_coverage >= 0.80 else 0
    score += 4 if ohlc_coverage >= 0.999 else -12
    score -= 12 if bad_data_rows else 0
    score = max(0, min(100, int(score)))
    data_grade, grade_label = _grade(score, has_true_order_flow, has_broker_real_ticks)

    limitations: list[str] = []
    warnings: list[str] = []
    if not has_true_order_flow:
        limitations.append("No true institutional order-flow, ECN depth, or dealer/prime-broker liquidity data is present.")
    if not has_l2:
        limitations.append("No level-2/order-book depth is present; liquidity sweeps are inferred from OHLC/tick-volume proxies.")
    if not has_broker_real_ticks:
        limitations.append("MT5 real-tick Strategy Tester evidence is not attached to this local candle run.")
    if real_volume_coverage == 0:
        limitations.append("Real exchange/venue volume is unavailable; MT5 tick_volume is only an activity proxy.")
    if spread_coverage < 0.95:
        warnings.append("Spread coverage is incomplete; cost/slippage diagnostics are weaker.")
    if bad_data_rows:
        warnings.append(f"{bad_data_rows} bad-data rows are present; institutional gate should reject affected setups.")
    if trade_count == 0:
        warnings.append("No trades were produced, so execution-quality conclusions are limited.")
    if source in RETAIL_SOURCES:
        warnings.append("This is retail-broker candle research. Treat signals as hypotheses until MT5 real-tick and/or external tick validation passes.")
    if require_real_tick and not has_broker_real_ticks:
        warnings.append("Real-tick validation is required by controls but not present.")
    if require_institutional and not has_true_order_flow:
        warnings.append("Institutional order-flow is required by controls but not present.")

    if require_institutional and not has_true_order_flow:
        validation_status = "BLOCKED_INSTITUTIONAL_DATA_REQUIRED"
    elif require_real_tick and not has_broker_real_ticks:
        validation_status = "BLOCKED_REAL_TICK_REQUIRED"
    elif data_grade == "INSTITUTIONAL_ORDER_FLOW_READY":
        validation_status = "INSTITUTIONAL_RESEARCH_READY"
    elif data_grade == "BROKER_REAL_TICK_VALIDATED":
        validation_status = "SEMI_MANUAL_DEMO_REVIEW_READY"
    elif data_grade == "RETAIL_PROXY_RESEARCH":
        validation_status = "RESEARCH_ONLY"
    else:
        validation_status = "DATA_NOT_TRUSTWORTHY"

    upgrade_path = [
        "Import MT5 Every Tick Based On Real Ticks reports for the same setup and compare model drift.",
        "Add broker cost calibration from real-tick reports before semi-manual review.",
        "For true institutional research, import external tick/order-flow or level-2 liquidity data and mark the source accordingly.",
        "Keep MT5 candle-only results as discovery hypotheses, not final approval evidence.",
    ]
    fields = [
        {"field": "timestamp", "required": True, "description": "UTC timestamp for tick/order-flow event."},
        {"field": "symbol", "required": True, "description": "Instrument such as EURUSD."},
        {"field": "bid", "required": False, "description": "Best bid for tick data."},
        {"field": "ask", "required": False, "description": "Best ask for tick data."},
        {"field": "last", "required": False, "description": "Last traded/mid price if available."},
        {"field": "bid_size", "required": False, "description": "Top-of-book bid size if available."},
        {"field": "ask_size", "required": False, "description": "Top-of-book ask size if available."},
        {"field": "aggressor_side", "required": False, "description": "buy/sell if venue provides trade aggressor."},
        {"field": "venue", "required": False, "description": "ECN/prime broker/data provider identifier."},
    ]
    return {
        "source_type": source,
        "provider": declared_provider,
        "data_score": score,
        "data_grade": data_grade,
        "grade_label": grade_label,
        "validation_status": validation_status,
        "semi_manual_readiness": validation_status in {"SEMI_MANUAL_DEMO_REVIEW_READY", "INSTITUTIONAL_RESEARCH_READY"},
        "institutional_order_flow_available": has_true_order_flow,
        "level2_order_book_available": has_l2,
        "external_tick_available": has_external_tick,
        "mt5_real_tick_validated": has_broker_real_ticks,
        "coverage": {
            "ohlc": round(ohlc_coverage, 4),
            "spread": round(spread_coverage, 4),
            "tick_volume": round(tick_volume_coverage, 4),
            "real_volume": round(real_volume_coverage, 4),
        },
        "proxy_quality": {
            "tick_volume_proxy": "usable_activity_proxy" if tick_volume_coverage >= 0.95 else "weak_or_missing",
            "liquidity_sweep_proxy": "ohlc_wick_based_not_order_flow",
            "spread_proxy": "available" if spread_coverage >= 0.95 else "incomplete",
            "volume_type": "real_volume" if real_volume_coverage >= 0.80 else "tick_volume_proxy",
        },
        "rows": {
            "candles": int(len(candles)),
            "features": int(len(features)),
            "trades": int(trade_count),
            "warmup_rows": warmup_rows,
            "bad_data_rows": bad_data_rows,
        },
        "limitations": limitations,
        "warnings": warnings,
        "upgrade_path": upgrade_path,
        "institutional_import_schema": fields,
        "note": "This layer grades data provenance. It does not create order-flow from retail candles.",
    }
