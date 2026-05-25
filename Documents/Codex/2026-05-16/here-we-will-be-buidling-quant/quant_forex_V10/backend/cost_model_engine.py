from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from backend.database import list_mt5_report_imports, load_mt5_report_import


DEFAULT_FIXED_COST_R = 0.05


POINT_SIZE_BY_SYMBOL = {
    "EURUSD": 0.00001,
    "GBPUSD": 0.00001,
    "AUDUSD": 0.00001,
    "NZDUSD": 0.00001,
    "USDCHF": 0.00001,
    "USDCAD": 0.00001,
    "USDJPY": 0.001,
    "EURJPY": 0.001,
    "GBPJPY": 0.001,
    "AUDJPY": 0.001,
    "NZDJPY": 0.001,
    "XAUUSD": 0.01,
}


SESSION_COST_MULTIPLIERS = {
    "Asia": 1.15,
    "London": 1.00,
    "NewYork": 1.05,
    "Overlap": 0.90,
    "Rollover": 3.00,
    "OffSession": 1.25,
}


VOLATILITY_COST_MULTIPLIERS = {
    "normal": 1.00,
    "compression": 0.95,
    "high_vol": 1.25,
    "stress": 1.75,
}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _session_from_time(value: Any) -> str:
    try:
        ts = pd.to_datetime(value, utc=True)
        if pd.isna(ts):
            return "UNKNOWN"
        hour = int(ts.hour)
        minute = int(ts.minute)
        minutes = hour * 60 + minute
        if 12 * 60 <= minutes < 16 * 60:
            return "Overlap"
        if 0 <= minutes < 7 * 60:
            return "Asia"
        if 7 * 60 <= minutes < 12 * 60:
            return "London"
        if 12 * 60 <= minutes < 17 * 60:
            return "NewYork"
        if 21 * 60 <= minutes < 22 * 60:
            return "Rollover"
        return "OffSession"
    except Exception:
        return "UNKNOWN"


def _point_size(symbol: str, costs: dict[str, Any]) -> float:
    overrides = costs.get("symbol_point_size") if isinstance(costs.get("symbol_point_size"), dict) else {}
    symbol_u = str(symbol or "").upper()
    if symbol_u in overrides:
        return _float(overrides[symbol_u], POINT_SIZE_BY_SYMBOL.get(symbol_u, 0.00001))
    for key, size in POINT_SIZE_BY_SYMBOL.items():
        if symbol_u.startswith(key):
            return size
    if "JPY" in symbol_u:
        return 0.001
    if "XAU" in symbol_u or "GOLD" in symbol_u:
        return 0.01
    return 0.00001


def _session_multiplier(session: str, costs: dict[str, Any]) -> float:
    custom = costs.get("session_cost_multiplier") or costs.get("session_multipliers")
    if isinstance(custom, dict) and session in custom:
        return max(0.0, _float(custom[session], 1.0))
    return SESSION_COST_MULTIPLIERS.get(session, 1.10)


def _volatility_bucket(row: pd.Series | dict[str, Any]) -> str:
    atr_pct = _float(row.get("atr_percentile"))
    candle_range_atr = _float(row.get("candle_range_atr"))
    if atr_pct >= 90 or candle_range_atr >= 2.5:
        return "stress"
    if atr_pct >= 75 or candle_range_atr >= 1.2 or _bool(row.get("volatility_expansion_flag")):
        return "high_vol"
    if _bool(row.get("compression_flag")) or atr_pct < 25:
        return "compression"
    return "normal"


def _volatility_multiplier(row: pd.Series | dict[str, Any], costs: dict[str, Any]) -> float:
    bucket = _volatility_bucket(row)
    custom = costs.get("volatility_cost_multiplier") or costs.get("volatility_multipliers")
    if isinstance(custom, dict) and bucket in custom:
        return max(0.0, _float(custom[bucket], 1.0))
    return VOLATILITY_COST_MULTIPLIERS[bucket]


def _news_multiplier(row: pd.Series | dict[str, Any], costs: dict[str, Any]) -> float:
    if not _bool(row.get("news_flag")):
        return 1.0
    return max(1.0, _float(costs.get("news_cost_multiplier"), 2.0))


def _spread_stress_multiplier(row: pd.Series | dict[str, Any]) -> float:
    spread_pct = _float(row.get("spread_percentile"))
    if spread_pct >= 90:
        return 1.75
    if spread_pct >= 80:
        return 1.35
    if spread_pct >= 70:
        return 1.15
    return 1.0


def _spread_cost_r(
    symbol: str,
    row: pd.Series | dict[str, Any],
    risk_distance: float,
    costs: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    spread_points = _float(row.get("spread"), _float(costs.get("fallback_spread_points"), 0.0))
    point_size = _point_size(symbol, costs)
    spread_price = spread_points * point_size
    round_trip_factor = max(0.0, _float(costs.get("spread_round_trip_factor"), 1.0))
    cost_r = (spread_price * round_trip_factor / risk_distance) if risk_distance > 0 else 0.0
    return max(0.0, cost_r), {
        "spread_points": round(spread_points, 4),
        "point_size": point_size,
        "spread_price": round(spread_price, 8),
        "spread_round_trip_factor": round_trip_factor,
    }


def _commission_cost_r(risk_distance: float, costs: dict[str, Any], initial_risk: float | None = None) -> float:
    direct = costs.get("commission_R", costs.get("commission_r"))
    if direct is not None:
        return max(0.0, _float(direct))
    currency = _float(costs.get("commission_currency_per_trade"), 0.0)
    if currency > 0 and initial_risk:
        return max(0.0, currency / initial_risk)
    return max(0.0, _float(costs.get("commission_r_per_trade"), 0.0))


def _slippage_cost_r(
    symbol: str,
    row: pd.Series | dict[str, Any],
    risk_distance: float,
    costs: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    direct = costs.get("slippage_R", costs.get("slippage_r"))
    if direct is not None:
        return max(0.0, _float(direct)), {"slippage_source": "direct_R"}
    points = _float(costs.get("slippage_points"), 0.0)
    stress_extra_points = _float(costs.get("stress_slippage_points"), 0.0) if _volatility_bucket(row) == "stress" else 0.0
    news_extra_points = _float(costs.get("news_slippage_points"), 0.0) if _bool(row.get("news_flag")) else 0.0
    total_points = points + stress_extra_points + news_extra_points
    price = total_points * _point_size(symbol, costs)
    cost_r = price / risk_distance if risk_distance > 0 else 0.0
    return max(0.0, cost_r), {
        "slippage_points": round(total_points, 4),
        "slippage_price": round(price, 8),
        "slippage_source": "points",
    }


def resolve_cost_model(costs: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize request cost settings while preserving old fixed-R behavior."""
    config = dict(costs or {})
    mode = str(config.get("cost_mode") or config.get("mode") or "fixed_r").lower()
    aliases = {
        "fixed": "fixed_r",
        "fixed r": "fixed_r",
        "spread": "spread_derived",
        "spread-derived": "spread_derived",
        "mt5": "mt5_imported",
        "mt5 imported": "mt5_imported",
        "stress": "stress_adjusted",
        "stress-adjusted": "stress_adjusted",
    }
    mode = aliases.get(mode, mode)
    if mode not in {"fixed_r", "spread_derived", "mt5_imported", "stress_adjusted"}:
        mode = "fixed_r"
    config["cost_mode"] = mode
    config.setdefault("cost_r_per_trade", DEFAULT_FIXED_COST_R)
    config.setdefault("max_rollover_cost_mode", "block")
    config.setdefault("news_cost_multiplier", 2.0)
    return config


def calculate_trade_cost(
    *,
    symbol: str,
    row: pd.Series | dict[str, Any],
    signal: dict[str, Any],
    costs: dict[str, Any] | None,
    initial_risk: float | None = None,
) -> dict[str, Any]:
    """Return R-denominated transaction cost detail for one candidate trade."""
    config = resolve_cost_model(costs)
    mode = config["cost_mode"]
    risk_distance = _float(signal.get("risk_distance"))
    session = str(row.get("session") or "OffSession")
    rollover_block = bool(config.get("rollover_block", True)) and session == "Rollover"

    spread_r = 0.0
    commission_r = 0.0
    slippage_r = 0.0
    spread_detail: dict[str, Any] = {}

    if mode == "fixed_r":
        fixed_r = max(0.0, _float(config.get("cost_r_per_trade"), DEFAULT_FIXED_COST_R))
        total_r = fixed_r
        reason = "Fixed R transaction-cost model applied."
    elif mode == "mt5_imported":
        total_r = max(
            0.0,
            _float(
                config.get("mt5_imported_cost_R"),
                _float(config.get("mt5_imported_avg_cost_R"), _float(config.get("cost_r_per_trade"), DEFAULT_FIXED_COST_R)),
            ),
        )
        reason = "MT5 imported cost model applied from supplied imported cost R/fallback value."
    else:
        spread_r, spread_detail = _spread_cost_r(symbol, row, risk_distance, config)
        commission_r = _commission_cost_r(risk_distance, config, initial_risk)
        slippage_r, slippage_detail = _slippage_cost_r(symbol, row, risk_distance, config)
        multiplier = 1.0
        multiplier_components = {
            "session": _session_multiplier(session, config),
            "news": _news_multiplier(row, config),
            "volatility": _volatility_multiplier(row, config),
            "spread_stress": _spread_stress_multiplier(row) if mode == "stress_adjusted" else 1.0,
        }
        for value in multiplier_components.values():
            multiplier *= value
        pre_multiplier = spread_r + commission_r + slippage_r
        total_r = pre_multiplier * multiplier
        reason = f"{mode.replace('_', ' ').title()} transaction-cost model applied."
        spread_detail = {
            **spread_detail,
            **slippage_detail,
            "pre_multiplier_cost_R": round(pre_multiplier, 6),
            "multiplier_components": {k: round(v, 4) for k, v in multiplier_components.items()},
            "combined_multiplier": round(multiplier, 4),
        }

    total_r = max(0.0, _float(total_r))
    if rollover_block:
        reason += " Rollover is configured as blocked; trade should already be filtered before cost is applied."
    return {
        "cost_model": mode,
        "total_cost_R": round(total_r, 6),
        "spread_cost_R": round(spread_r, 6),
        "commission_R": round(commission_r, 6),
        "slippage_R": round(slippage_r, 6),
        "session_cost_multiplier": round(_session_multiplier(session, config), 4),
        "news_cost_multiplier": round(_news_multiplier(row, config), 4),
        "volatility_cost_multiplier": round(_volatility_multiplier(row, config), 4),
        "spread_stress_multiplier": round(_spread_stress_multiplier(row), 4),
        "rollover_block": rollover_block,
        "session": session,
        "volatility_bucket": _volatility_bucket(row),
        "reason": reason,
        **spread_detail,
    }


def _raw_num(raw: dict[str, Any], names: list[str], default: float = 0.0) -> float:
    normalized = {str(k).strip().lower().replace(" ", "_"): v for k, v in (raw or {}).items()}
    for name in names:
        key = name.strip().lower().replace(" ", "_")
        if key in normalized:
            value = _float(normalized.get(key), default)
            if value != default or str(normalized.get(key, "")).strip() not in {"", "0", "0.0"}:
                return value
    return default


def _quantile(values: list[float], q: float) -> float:
    clean = [float(v) for v in values if math.isfinite(float(v))]
    return round(float(np.quantile(clean, q)), 6) if clean else 0.0


def _avg(values: list[float]) -> float:
    clean = [float(v) for v in values if math.isfinite(float(v))]
    return round(float(np.mean(clean)), 6) if clean else 0.0


def _calibration_status(report_count: int, real_tick_count: int, sample_count: int) -> str:
    if report_count == 0:
        return "NO_MT5_REPORTS"
    if real_tick_count == 0:
        return "NO_REAL_TICK_REPORT"
    if sample_count < 20:
        return "LOW_SAMPLE_REVIEW"
    return "BROKER_COST_READY"


def calibrate_broker_costs(request: dict[str, Any] | None = None) -> dict[str, Any]:
    """Derive broker-cost research settings from imported MT5 tester reports."""
    request = dict(request or {})
    symbol_filter = str(request.get("symbol") or "").upper().strip()
    model_filter = str(request.get("test_model") or request.get("model") or "every_tick_real_ticks")
    include_all_models = bool(request.get("include_all_models", False))
    limit = int(request.get("limit") or 25)
    import_ids = [str(item) for item in request.get("import_ids", []) if str(item).strip()]
    if import_ids:
        imports = [load_mt5_report_import(import_id) for import_id in import_ids]
        imports = [item for item in imports if item]
    else:
        imports = list_mt5_report_imports(limit)

    samples: list[dict[str, Any]] = []
    import_summaries: list[dict[str, Any]] = []
    for item in imports:
        if not item:
            continue
        if symbol_filter and str(item.get("symbol") or "").upper() != symbol_filter:
            continue
        model = str(item.get("test_model") or "")
        if not include_all_models and model != model_filter:
            continue
        loaded = load_mt5_report_import(item["import_id"]) if "deals" not in item else item
        if not loaded:
            continue
        import_summaries.append(
            {
                "import_id": loaded.get("import_id"),
                "file_name": loaded.get("file_name"),
                "test_model": model,
                "symbol": loaded.get("symbol"),
                "trade_count": loaded.get("summary", {}).get("trade_count", 0),
                "net_profit": loaded.get("summary", {}).get("net_profit", 0),
                "result_r_source": loaded.get("summary", {}).get("result_r_source"),
            }
        )
        risk_amount = float(loaded.get("initial_equity") or 100000) * float(loaded.get("risk_percent") or 1.0) / 100
        for deal in loaded.get("deals", []):
            profit = _float(deal.get("profit"))
            commission = abs(_float(deal.get("commission")))
            swap = abs(_float(deal.get("swap")))
            raw = deal.get("raw") if isinstance(deal.get("raw"), dict) else {}
            initial_risk = _float(raw.get("initial_risk"), _float(deal.get("initial_risk"), risk_amount))
            if profit == 0 and commission == 0 and swap == 0:
                continue
            spread_points = _raw_num(raw, ["spread", "spread_points", "entry_spread"], 0.0)
            slippage_points = _raw_num(raw, ["slippage_points", "slippage", "slippage_pts"], 0.0)
            explicit_cost_r = _raw_num(raw, ["total_cost_r", "cost_r", "total_cost_R"], 0.0)
            explicit_slippage_r = _raw_num(raw, ["slippage_r", "estimated_slippage_r"], 0.0)
            commission_r = (commission / initial_risk) if initial_risk > 0 else 0.0
            swap_r = (swap / initial_risk) if initial_risk > 0 else 0.0
            total_cost_r = explicit_cost_r if explicit_cost_r > 0 else commission_r + swap_r + explicit_slippage_r
            samples.append(
                {
                    "import_id": loaded.get("import_id"),
                    "model": model,
                    "symbol": deal.get("symbol") or loaded.get("symbol"),
                    "session": _session_from_time(deal.get("time")),
                    "commission_R": round(commission_r, 6),
                    "swap_R": round(swap_r, 6),
                    "slippage_R": round(explicit_slippage_r, 6),
                    "total_cost_R": round(total_cost_r, 6),
                    "spread_points": round(spread_points, 4),
                    "slippage_points": round(slippage_points, 4),
                    "initial_risk": round(initial_risk, 2),
                }
            )

    cost_values = [float(row["total_cost_R"]) for row in samples if float(row["total_cost_R"]) > 0]
    commission_values = [float(row["commission_R"]) for row in samples if float(row["commission_R"]) > 0]
    swap_values = [float(row["swap_R"]) for row in samples if float(row["swap_R"]) > 0]
    spread_values = [float(row["spread_points"]) for row in samples if float(row["spread_points"]) > 0]
    slippage_points = [float(row["slippage_points"]) for row in samples if float(row["slippage_points"]) > 0]
    slippage_r = [float(row["slippage_R"]) for row in samples if float(row["slippage_R"]) > 0]
    real_tick_reports = [item for item in import_summaries if item.get("test_model") == "every_tick_real_ticks"]
    session_rows = []
    for session in sorted({row["session"] for row in samples}):
        group = [row for row in samples if row["session"] == session]
        session_costs = [float(row["total_cost_R"]) for row in group if float(row["total_cost_R"]) > 0]
        session_rows.append(
            {
                "session": session,
                "samples": len(group),
                "avg_cost_R": _avg(session_costs),
                "p75_cost_R": _quantile(session_costs, 0.75),
                "avg_spread_points": _avg([float(row["spread_points"]) for row in group if float(row["spread_points"]) > 0]),
                "avg_slippage_points": _avg([float(row["slippage_points"]) for row in group if float(row["slippage_points"]) > 0]),
            }
        )
    overall_avg = _avg(cost_values)
    recommended_cost = _quantile(cost_values, 0.75) or overall_avg or DEFAULT_FIXED_COST_R
    session_multipliers = {
        row["session"]: round(max(0.5, row["avg_cost_R"] / overall_avg), 4)
        for row in session_rows
        if overall_avg > 0 and row["avg_cost_R"] > 0
    }
    status = _calibration_status(len(import_summaries), len(real_tick_reports), len(samples))
    warnings: list[str] = []
    if status == "NO_MT5_REPORTS":
        warnings.append("No imported MT5 reports matched the calibration request.")
    if status == "NO_REAL_TICK_REPORT":
        warnings.append("No real-tick report was found; broker-cost calibration is weaker without real ticks.")
    if not cost_values:
        warnings.append("Imported reports did not expose commission/swap/cost_R/initial_risk enough to derive direct R costs; using fallback fixed cost.")
    if not spread_values:
        warnings.append("Spread points were not present in imported report rows; spread curve remains candle-derived.")
    if not slippage_points and not slippage_r:
        warnings.append("Slippage was not present in imported report rows; slippage remains model-based.")
    return {
        "status": status,
        "sample_count": len(samples),
        "report_count": len(import_summaries),
        "real_tick_report_count": len(real_tick_reports),
        "symbol": symbol_filter or "ALL",
        "model_filter": model_filter if not include_all_models else "ALL",
        "summary": {
            "avg_cost_R": overall_avg,
            "p50_cost_R": _quantile(cost_values, 0.50),
            "p75_cost_R": _quantile(cost_values, 0.75),
            "p90_cost_R": _quantile(cost_values, 0.90),
            "avg_commission_R": _avg(commission_values),
            "avg_swap_R": _avg(swap_values),
            "avg_spread_points": _avg(spread_values),
            "p90_spread_points": _quantile(spread_values, 0.90),
            "avg_slippage_points": _avg(slippage_points),
            "avg_slippage_R": _avg(slippage_r),
        },
        "recommended_costs": {
            "cost_mode": "mt5_imported",
            "mt5_imported_cost_R": round(recommended_cost, 6),
            "mt5_imported_avg_cost_R": overall_avg,
            "commission_R": _avg(commission_values),
            "slippage_R": _avg(slippage_r),
            "slippage_points": _avg(slippage_points),
            "session_cost_multiplier": session_multipliers,
            "rollover_block": True,
            "calibration_source": "mt5_report_imports",
            "calibration_status": status,
        },
        "session_curve": session_rows,
        "reports": import_summaries,
        "sample_preview": samples[:25],
        "warnings": warnings,
        "next_actions": [
            "Use the recommended mt5_imported_cost_R for candidate validation backtests.",
            "Prefer real-tick reports with result_R, initial_risk, spread, and slippage columns for stronger calibration.",
            "Re-run final approval after applying calibrated broker costs.",
        ],
    }
