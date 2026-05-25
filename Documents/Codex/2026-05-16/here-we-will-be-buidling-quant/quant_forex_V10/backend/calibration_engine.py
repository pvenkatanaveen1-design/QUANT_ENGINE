from __future__ import annotations

from copy import deepcopy
from typing import Any

import pandas as pd


ALL_REGIMES = [f"R{i:02d}" for i in range(1, 51)]
CORE_REGIMES = ALL_REGIMES


BALANCED_REGIME_VALUES: dict[str, dict[str, float]] = {
    "R01": {"adx_min": 18, "adx_max": 35, "er_min": 0.25, "atr_percentile_min": 25, "atr_percentile_max": 80, "max_spread_percentile": 70, "max_distance_ema20_atr": 2.5, "min_alpha_score": 8, "confidence_min": 0.75},
    "R02": {"adx_min": 18, "adx_max": 35, "er_min": 0.25, "atr_percentile_min": 25, "atr_percentile_max": 80, "max_spread_percentile": 70, "max_distance_ema20_atr": 2.5, "min_alpha_score": 8, "confidence_min": 0.75},
    "R03": {"adx_max": 18, "er_max": 0.25, "atr_percentile_min": 25, "atr_percentile_max": 75, "ema50_cross_count_min": 3, "max_spread_percentile": 70, "range_edge_tolerance_atr": 0.20, "min_alpha_score": 5, "confidence_min": 0.70},
    "R04": {"adx_min": 22, "er_min": 0.25, "atr_percentile_min": 75, "atr_percentile_max": 90, "candle_range_atr_min": 1.2, "max_spread_percentile": 80, "min_alpha_score": 7, "confidence_min": 0.75},
    "R05": {"adx_min": 22, "er_min": 0.25, "atr_percentile_min": 75, "atr_percentile_max": 90, "candle_range_atr_min": 1.2, "max_spread_percentile": 80, "min_alpha_score": 7, "confidence_min": 0.75},
    "R06": {"adx_max": 18, "er_max": 0.25, "atr_percentile_max": 25, "bb_width_percentile_max": 25, "candle_range_atr_max": 1.0, "max_spread_percentile": 70, "compression_lookback": 20, "min_alpha_score": 5, "confidence_min": 0.70},
    "R07": {"adx_min": 25, "atr_percentile_min": 75, "upper_wick_min": 0.45, "distance_ema20_min": 2.5, "distance_ema50_min": 2.5, "max_spread_percentile": 80, "min_alpha_score": 6, "confidence_min": 0.70},
    "R08": {"adx_min": 25, "atr_percentile_min": 75, "lower_wick_min": 0.45, "distance_ema20_max": -2.5, "distance_ema50_max": -2.5, "max_spread_percentile": 80, "min_alpha_score": 6, "confidence_min": 0.70},
    "R09": {"candle_range_atr_shock_min": 2.0, "atr_percentile_shock_min": 85, "candle_range_atr_cool_max": 2.0, "max_spread_percentile": 80, "post_news_wait_bars": 3, "min_alpha_score": 7, "confidence_min": 0.75},
    "R10": {"spread_stress_min": 90, "atr_percentile_shock_min": 90, "candle_range_atr_shock_min": 2.5, "adx_chop_max": 18, "er_chop_max": 0.20, "atr_chop_min": 80, "min_alpha_score": 99},
    "R11": {"adx_min": 14, "adx_max": 25, "er_min": 0.20, "atr_percentile_min": 15, "atr_percentile_max": 35, "candle_range_atr_max": 1.2, "max_spread_percentile": 70, "max_distance_ema20_atr": 2.0, "min_alpha_score": 6, "confidence_min": 0.75},
    "R12": {"adx_min": 14, "adx_max": 25, "er_min": 0.20, "atr_percentile_min": 15, "atr_percentile_max": 35, "candle_range_atr_max": 1.2, "max_spread_percentile": 70, "max_distance_ema20_atr": 2.0, "min_alpha_score": 6, "confidence_min": 0.75},
    "R13": {"channel_slope_min": 0.02, "adx_min": 15, "adx_max": 30, "er_min": 0.20, "atr_percentile_min": 25, "atr_percentile_max": 75, "max_spread_percentile": 70, "min_alpha_score": 6, "confidence_min": 0.75},
    "R14": {"channel_slope_max": -0.02, "adx_min": 15, "adx_max": 30, "er_min": 0.20, "atr_percentile_min": 25, "atr_percentile_max": 75, "max_spread_percentile": 70, "min_alpha_score": 6, "confidence_min": 0.75},
    "R15": {"adx_max": 25, "er_max": 0.30, "upper_wick_min": 0.35, "range_edge_tolerance_atr": 0.20, "max_spread_percentile": 70, "min_alpha_score": 5, "confidence_min": 0.75},
    "R16": {"adx_max": 25, "er_max": 0.30, "lower_wick_min": 0.35, "range_edge_tolerance_atr": 0.20, "max_spread_percentile": 70, "min_alpha_score": 5, "confidence_min": 0.75},
    "R17": {"upper_wick_min": 0.35, "max_spread_percentile": 70, "atr_percentile_max": 90, "false_breakout_reclaim_bars": 3, "min_alpha_score": 5, "confidence_min": 0.70},
    "R18": {"lower_wick_min": 0.35, "max_spread_percentile": 70, "atr_percentile_max": 90, "false_breakout_reclaim_bars": 3, "min_alpha_score": 5, "confidence_min": 0.70},
    "R19": {"atr_percentile_min": 40, "candle_range_atr_min": 1.0, "max_spread_percentile": 70, "start_hour_utc": 7, "end_hour_utc": 10, "opening_range_minutes": 30, "min_alpha_score": 7, "confidence_min": 0.75},
    "R20": {"atr_percentile_min": 40, "candle_range_atr_min": 1.0, "max_spread_percentile": 70, "start_hour_utc": 12, "end_hour_utc": 15, "opening_range_minutes": 30, "min_alpha_score": 7, "confidence_min": 0.75},
    "R21": {"adx_min": 18, "er_min": 0.25, "atr_percentile_min": 25, "atr_percentile_max": 90, "max_spread_percentile": 70, "start_hour_utc": 12, "end_hour_utc": 16, "min_alpha_score": 7, "confidence_min": 0.75},
    "R22": {"adx_max": 18, "er_max": 0.25, "atr_percentile_max": 75, "max_spread_percentile": 70, "range_edge_tolerance_atr": 0.20, "min_alpha_score": 5, "confidence_min": 0.75},
    "R23": {"adx_max": 18, "er_max": 0.20, "atr_percentile_min": 75, "candle_range_atr_min": 1.2, "ema50_cross_count_min": 4, "max_spread_percentile": 90, "chop_score_min": 4, "min_alpha_score": 99, "confidence_min": 0.70},
    "R24": {"atr_percentile_max": 15, "bb_width_percentile_max": 15, "adx_max": 15, "candle_range_atr_max": 0.70, "dead_market_score_min": 3, "min_alpha_score": 99, "confidence_min": 0.75},
    "R25": {"macro_confidence_min": 0.50, "adx_min": 18, "er_min": 0.20, "max_spread_percentile": 70, "min_alpha_score": 7, "confidence_min": 0.75},
    "R26": {"macro_confidence_min": 0.50, "adx_min": 18, "er_min": 0.20, "max_spread_percentile": 70, "min_alpha_score": 7, "confidence_min": 0.75},
    "R27": {"macro_confidence_min": 0.50, "adx_min": 18, "er_min": 0.20, "atr_percentile_max": 90, "max_spread_percentile": 70, "min_alpha_score": 7, "confidence_min": 0.75},
    "R28": {"macro_confidence_min": 0.50, "adx_min": 18, "er_min": 0.20, "atr_percentile_max": 90, "max_spread_percentile": 80, "min_alpha_score": 7, "confidence_min": 0.75},
    "R29": {"macro_confidence_min": 0.50, "adx_min": 18, "er_min": 0.25, "atr_percentile_min": 25, "atr_percentile_max": 90, "max_spread_percentile": 70, "min_alpha_score": 8, "confidence_min": 0.75},
    "R30": {"month_end_start_day": 25, "fixing_start_hour_utc": 15, "fixing_end_hour_utc": 16.25, "max_spread_percentile": 90, "min_alpha_score": 99},
    "R31": {"adx_min": 15, "adx_max": 22, "er_min": 0.18, "er_max": 0.28, "ema50_cross_count_min": 3, "max_spread_percentile": 90, "min_alpha_score": 8, "confidence_min": 0.50},
    "R32": {"adx_min": 18, "adx_slope_max": 0, "er_slope_max": 0, "atr_percentile_min": 25, "atr_percentile_max": 90, "max_spread_percentile": 70, "min_alpha_score": 8, "confidence_min": 0.75},
    "R33": {"adx_min": 18, "adx_slope_max": 0, "er_slope_max": 0, "atr_percentile_min": 25, "atr_percentile_max": 90, "max_spread_percentile": 70, "min_alpha_score": 8, "confidence_min": 0.75},
    "R34": {"lower_wick_min": 0.40, "atr_percentile_min": 25, "atr_percentile_max": 90, "max_spread_percentile": 70, "min_alpha_score": 7, "confidence_min": 0.75},
    "R35": {"upper_wick_min": 0.40, "atr_percentile_min": 25, "atr_percentile_max": 90, "max_spread_percentile": 70, "min_alpha_score": 7, "confidence_min": 0.75},
    "R36": {"adx_max": 18, "er_max": 0.25, "atr_percentile_min": 25, "atr_percentile_max": 75, "vwap_distance_atr_min": 1.5, "max_spread_percentile": 70, "min_alpha_score": 5, "confidence_min": 0.75},
    "R37": {"adx_min": 15, "adx_max": 25, "er_max": 0.30, "ema50_cross_count_min": 3, "max_spread_percentile": 70, "min_alpha_score": 7, "confidence_min": 0.75},
    "R38": {"spread_stress_min": 90, "spread_normalized_max": 70, "candle_range_atr_max": 2.0, "post_stress_wait_bars": 3, "min_alpha_score": 7, "confidence_min": 0.75},
    "R39": {"gap_atr_min": 0.75, "monday_gap_atr_min": 0.50, "max_spread_percentile": 90, "gap_trade_wait_bars": 3, "min_alpha_score": 7},
    "R40": {"minimum_percentile_bars": 252, "minimum_er_bars": 30, "minimum_adx_bars": 14, "minimum_swing_bars": 20, "min_alpha_score": 99},
    "R41": {"atr_percentile_min": 25, "atr_percentile_max": 90, "max_spread_percentile": 70, "min_alpha_score": 7, "confidence_min": 0.75},
    "R42": {"wick_min": 0.35, "adx_max": 25, "er_max": 0.30, "max_spread_percentile": 70, "min_alpha_score": 6, "confidence_min": 0.75},
    "R43": {"wick_min": 0.35, "adx_max": 25, "er_max": 0.30, "max_spread_percentile": 70, "min_alpha_score": 6, "confidence_min": 0.75},
    "R44": {"adx_min": 25, "er_min": 0.30, "atr_percentile_min": 50, "atr_percentile_max": 90, "candle_range_atr_min": 1.0, "max_spread_percentile": 70, "min_alpha_score": 8, "confidence_min": 0.75},
    "R45": {"atr_percentile_min": 80, "candle_range_atr_min": 1.6, "distance_ema20_atr_min": 2.5, "wick_min": 0.45, "max_spread_percentile": 90, "min_alpha_score": 8, "confidence_min": 0.75},
    "R46": {"adx_min": 18, "er_min": 0.25, "vwap_distance_min": 0.20, "vwap_distance_max": 1.50, "max_spread_percentile": 70, "min_alpha_score": 7, "confidence_min": 0.75},
    "R47": {"bb_width_percentile_max": 50, "atr_percentile_min": 20, "atr_percentile_max": 75, "candle_range_atr_min": 1.0, "max_spread_percentile": 70, "min_alpha_score": 7, "confidence_min": 0.75},
    "R48": {"adx_max": 18, "er_max": 0.25, "atr_percentile_min": 25, "atr_percentile_max": 75, "midpoint_distance_atr_min": 0.75, "wick_min": 0.35, "max_spread_percentile": 70, "min_alpha_score": 5, "confidence_min": 0.75},
    "R49": {"wick_min": 0.35, "max_spread_percentile": 70, "min_alpha_score": 6, "confidence_min": 0.75},
    "R50": {"spread_percentile_min": 70, "spread_percentile_max": 90, "candle_range_atr_max": 1.0, "atr_percentile_max": 50, "min_alpha_score": 9, "confidence_min": 0.75},
}


PROFILE_SETTINGS = {
    "balanced": {
        "name": "Balanced",
        "meaning": "Matches the current research defaults. Use this as the baseline for comparison.",
        "global_controls": {"min_alpha_score": 5, "max_spread_percentile": 70},
    },
    "conservative": {
        "name": "Conservative",
        "meaning": "Requires cleaner movement, lower spread stress, and higher alpha before approving setups.",
        "global_controls": {"min_alpha_score": 8, "max_spread_percentile": 65},
    },
    "aggressive": {
        "name": "Aggressive",
        "meaning": "Loosens filters for discovery. Treat results as exploratory and require OOS/WF/MT5 validation.",
        "global_controls": {"min_alpha_score": 4, "max_spread_percentile": 80},
    },
    "funded_style": {
        "name": "Funded-Style",
        "meaning": "Prioritizes drawdown control: stricter alpha, lower spread, and narrower trade windows.",
        "global_controls": {"min_alpha_score": 9, "max_spread_percentile": 60, "risk_percent_hint": "0.25% to 0.50%"},
    },
}


def _adjust_value(key: str, value: float, profile: str) -> float:
    if profile == "balanced":
        return value
    bounded = lambda item, low, high: max(low, min(high, item))
    if key in {"min_alpha_score"}:
        return min(99.0, value + {"conservative": 1.0, "aggressive": -1.0, "funded_style": 2.0}[profile])
    if key in {"max_spread_percentile", "spread_normalized_max", "spread_stress_min"}:
        return max(0.0, min(100.0, value + {"conservative": -5.0, "aggressive": 10.0, "funded_style": -10.0}[profile]))
    if key == "macro_confidence_min":
        return round(bounded(value + {"conservative": 0.10, "aggressive": -0.10, "funded_style": 0.15}[profile], 0.0, 1.0), 4)
    if key == "confidence_min":
        return round(bounded(value + {"conservative": 0.05, "aggressive": -0.05, "funded_style": 0.08}[profile], 0.4, 0.95), 4)
    if "wick" in key:
        return round(bounded(value + {"conservative": 0.05, "aggressive": -0.05, "funded_style": 0.08}[profile], 0.0, 0.95), 4)
    if any(part in key for part in ["distance_", "candle_range_atr", "gap_atr", "vwap_distance", "range_edge_tolerance"]):
        if key.endswith("_max"):
            delta = {"conservative": -0.10, "aggressive": 0.15, "funded_style": -0.20}[profile]
            if value < 0:
                delta *= -1
        elif key.endswith("_min"):
            delta = {"conservative": 0.10, "aggressive": -0.10, "funded_style": 0.15}[profile]
        else:
            delta = {"conservative": -0.02, "aggressive": 0.03, "funded_style": -0.04}[profile]
        return round(value + delta, 4)
    if "percentile" in key or key.startswith("atr_"):
        if key.endswith("_max"):
            return round(bounded(value + {"conservative": -5.0, "aggressive": 5.0, "funded_style": -8.0}[profile], 0.0, 100.0), 4)
        if key.endswith("_min"):
            return round(bounded(value + {"conservative": 5.0, "aggressive": -5.0, "funded_style": 8.0}[profile], 0.0, 100.0), 4)
    if key.endswith("_min") and key not in {"start_hour_utc", "minimum_percentile_bars", "minimum_er_bars", "minimum_adx_bars", "minimum_swing_bars"}:
        return round(value + {"conservative": 0.05 if value < 1 else 2.0, "aggressive": -0.05 if value < 1 else -2.0, "funded_style": 0.08 if value < 1 else 3.0}[profile], 4)
    if key.endswith("_max") and key not in {"end_hour_utc"}:
        if value < 0:
            return round(value + {"conservative": -0.01, "aggressive": 0.01, "funded_style": -0.015}[profile], 4)
        return round(value + {"conservative": -0.03 if value < 1 else -3.0, "aggressive": 0.05 if value < 1 else 5.0, "funded_style": -0.05 if value < 1 else -5.0}[profile], 4)
    return value


def _build_profile(profile: str) -> dict[str, Any]:
    settings = PROFILE_SETTINGS[profile]
    regimes = {
        regime_id: {key: _adjust_value(key, value, profile) for key, value in values.items()}
        for regime_id, values in BALANCED_REGIME_VALUES.items()
    }
    return {
        "profile": profile,
        "name": settings["name"],
        "meaning": settings["meaning"],
        "global_controls": deepcopy(settings["global_controls"]),
        "regimes": regimes,
    }


CALIBRATION_PROFILES: dict[str, dict[str, Any]] = {
    key: _build_profile(key) for key in ["balanced", "conservative", "aggressive", "funded_style"]
}


def _profile_name(value: Any) -> str:
    profile = str(value or "balanced").strip().lower().replace("-", "_")
    return profile if profile in CALIBRATION_PROFILES else "balanced"


def list_calibration_profiles() -> dict[str, Any]:
    profiles = [deepcopy(CALIBRATION_PROFILES[key]) for key in ["balanced", "conservative", "aggressive", "funded_style"]]
    return {
        "profiles": profiles,
        "core_regimes": CORE_REGIMES,
        "notes": [
            "Profiles preserve current behavior when calibration is omitted.",
            "R01-R50 now have profile values so UI, optimizer, and reports can compare regimes consistently.",
            "Detector-level threshold reads are wired into the major trend, range, breakout, session, macro, safety, and advanced regimes.",
        ],
    }


def resolve_calibration(request: dict[str, Any] | None) -> dict[str, Any]:
    request = request or {}
    raw = request.get("calibration") if isinstance(request.get("calibration"), dict) else {}
    profile_name = _profile_name(raw.get("profile") or request.get("calibration_profile"))
    resolved = deepcopy(CALIBRATION_PROFILES[profile_name])
    overrides = raw.get("overrides") if isinstance(raw.get("overrides"), dict) else {}
    for regime_id, values in overrides.items():
        rid = str(regime_id).upper()
        if not isinstance(values, dict):
            continue
        resolved.setdefault("regimes", {}).setdefault(rid, {})
        for key, value in values.items():
            if value in {None, ""}:
                continue
            resolved["regimes"][rid][key] = value
    if isinstance(raw.get("global_controls"), dict):
        resolved.setdefault("global_controls", {}).update({k: v for k, v in raw["global_controls"].items() if v not in {None, ""}})
    resolved["overrides"] = overrides
    resolved["active"] = bool(raw or request.get("calibration_profile"))
    return resolved


def regime_calibration(calibration: dict[str, Any], regime_id: str) -> dict[str, Any]:
    return deepcopy((calibration.get("regimes") or {}).get(str(regime_id).upper(), {}))


def calibration_summary(calibration: dict[str, Any], regime_filter: str = "ALL") -> dict[str, Any]:
    target = str(regime_filter or "ALL").upper()
    regimes = calibration.get("regimes") or {}
    return {
        "active": bool(calibration.get("active")),
        "profile": calibration.get("profile", "balanced"),
        "name": calibration.get("name", "Balanced"),
        "meaning": calibration.get("meaning", ""),
        "global_controls": calibration.get("global_controls", {}),
        "target_regime": target,
        "target_regime_values": regime_calibration(calibration, target) if target != "ALL" else {},
        "calibrated_regimes": sorted(regimes.keys()),
        "notes": [
            "Calibration changes research thresholds only; it does not add order execution.",
            "For ALL-regime runs, per-regime threshold overrides are applied during each regime detector where supported.",
            "For selected-regime runs, profile min alpha and max spread are also pushed into the active backtest filters.",
        ],
    }


def apply_calibration_to_request(request: dict[str, Any], calibration: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(request)
    target = str(payload.get("regime_filter") or "ALL").upper()
    values = regime_calibration(calibration, target) if target != "ALL" else {}
    controls = calibration.get("global_controls") or {}
    filters = payload.setdefault("filters", {})
    if target != "ALL" and values:
        if values.get("min_alpha_score") not in {None, ""}:
            filters["min_alpha_score"] = float(values["min_alpha_score"])
        if values.get("max_spread_percentile") not in {None, ""}:
            filters["max_spread_percentile"] = float(values["max_spread_percentile"])
    else:
        if controls.get("min_alpha_score") not in {None, ""}:
            filters.setdefault("min_alpha_score", float(controls["min_alpha_score"]))
        if controls.get("max_spread_percentile") not in {None, ""}:
            filters.setdefault("max_spread_percentile", float(controls["max_spread_percentile"]))
    payload["calibration"] = {
        "profile": calibration.get("profile", "balanced"),
        "global_controls": controls,
        "regimes": calibration.get("regimes", {}),
        "overrides": calibration.get("overrides", {}),
    }
    return payload


def inject_calibration_columns(features: pd.DataFrame, calibration: dict[str, Any]) -> pd.DataFrame:
    if features.empty:
        return features
    additions: dict[str, Any] = {}
    for regime_id, values in (calibration.get("regimes") or {}).items():
        prefix = f"cal_{str(regime_id).lower()}_"
        for key, value in values.items():
            if isinstance(value, (int, float)):
                additions[f"{prefix}{key}"] = float(value)
    if not additions:
        return features
    return pd.concat([features, pd.DataFrame(additions, index=features.index)], axis=1)
