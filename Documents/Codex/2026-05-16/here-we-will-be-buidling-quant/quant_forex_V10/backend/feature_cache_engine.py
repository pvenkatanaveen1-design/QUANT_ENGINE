from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from backend.common.engines.feature_engine import calculate_features
from backend.database import (
    load_candles,
    load_feature_cache_metadata,
    load_features_for_cache,
    normalize_data_source,
    save_feature_cache_metadata,
    save_features,
)


FINGERPRINT_COLUMNS = ["timestamp", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
FEATURE_ENGINE_VERSION = "2026-05-25-stat-regime-v2"


def candles_provider_name(data_source: str) -> str:
    names = {
        "mt5_retail_candles": "MT5 / SQLite",
        "mt5_every_tick": "MT5 Strategy Tester every tick",
        "mt5_real_ticks": "MT5 Strategy Tester real ticks",
        "dukascopy_ticks": "Dukascopy",
        "alpha_vantage_fx": "Alpha Vantage",
        "twelve_data_fx": "Twelve Data",
        "polygon_fx": "Polygon.io",
        "csv_import": "CSV import",
        "cme_fx_futures_proxy": "CME FX futures proxy",
    }
    return names.get(data_source, data_source.replace("_", " ").title())


def _stable_json(value: Any) -> str:
    return json.dumps(value or {}, sort_keys=True, default=str, separators=(",", ":"))


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def feature_params(
    *,
    timeframe: str,
    sentiment: str = "NEUTRAL",
    usd_bias: str = "NEUTRAL",
    risk_sentiment: str = "NEUTRAL",
    cb_divergence: str = "NEUTRAL",
    macro_evidence: dict[str, Any] | None = None,
    data_source: str | None = None,
) -> dict[str, Any]:
    macro = dict(macro_evidence or {})
    source = normalize_data_source(data_source)
    return {
        "feature_engine_version": FEATURE_ENGINE_VERSION,
        "timeframe": timeframe,
        "data_source": source,
        "sentiment": sentiment or "NEUTRAL",
        "usd_bias": usd_bias or "NEUTRAL",
        "risk_sentiment": risk_sentiment or "NEUTRAL",
        "cb_divergence": cb_divergence or "NEUTRAL",
        "macro_evidence": macro,
    }


def params_hash(params: dict[str, Any]) -> str:
    return _hash_text(_stable_json(params))


def candle_fingerprint(candles: pd.DataFrame) -> str:
    if candles.empty:
        return "empty"
    cols = [col for col in FINGERPRINT_COLUMNS if col in candles.columns]
    frame = candles[cols].copy()
    if "timestamp" in frame:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).astype(str)
    row_hashes = pd.util.hash_pandas_object(frame, index=False).astype("uint64").to_numpy().tobytes()
    meta = {
        "columns": cols,
        "rows": int(len(frame)),
        "first": str(frame["timestamp"].iloc[0]) if "timestamp" in frame and len(frame) else "",
        "last": str(frame["timestamp"].iloc[-1]) if "timestamp" in frame and len(frame) else "",
    }
    digest = hashlib.sha256()
    digest.update(_stable_json(meta).encode("utf-8"))
    digest.update(row_hashes)
    return digest.hexdigest()


def _attach_candle_columns(features: pd.DataFrame, candles: pd.DataFrame) -> pd.DataFrame:
    candle_cols = [col for col in FINGERPRINT_COLUMNS if col in candles.columns]
    if "timestamp" not in candle_cols or features.empty:
        return features
    candle_frame = candles[candle_cols].copy()
    candle_frame["timestamp"] = pd.to_datetime(candle_frame["timestamp"], utc=True)
    merged = features.drop(columns=[col for col in candle_cols if col != "timestamp" and col in features.columns], errors="ignore").merge(
        candle_frame,
        on="timestamp",
        how="left",
        sort=False,
    )
    return merged


def cache_key(symbol: str, timeframe: str, start_date: str, end_date: str, param_hash: str, data_source: str | None = None) -> str:
    return _hash_text(
        _stable_json(
            {
                "symbol": symbol.upper(),
                "timeframe": timeframe.upper(),
                "start_date": start_date,
                "end_date": end_date,
                "data_source": normalize_data_source(data_source),
                "params_hash": param_hash,
            }
        )
    )


def feature_cache_status(
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    params: dict[str, Any],
    candles: pd.DataFrame | None = None,
    data_source: str | None = None,
) -> dict[str, Any]:
    source = normalize_data_source(data_source or params.get("data_source"))
    param_hash = params_hash(params)
    key = cache_key(symbol, timeframe, start_date, end_date, param_hash, source)
    metadata = load_feature_cache_metadata(key)
    if candles is None:
        candles = load_candles(symbol, timeframe, start_date, end_date, data_source=source)
    if candles.empty:
        return {"enabled": True, "cache_key": key, "cache_hit": False, "status": "MISS", "reason": "No candles available for cache validation."}
    fingerprint = candle_fingerprint(candles)
    if not metadata:
        return {"enabled": True, "cache_key": key, "cache_hit": False, "status": "MISS", "reason": "No cached feature metadata for this parameter set.", "candle_count": int(len(candles))}
    reasons = []
    if metadata.get("candle_fingerprint") != fingerprint:
        reasons.append("candle fingerprint changed")
    if int(metadata.get("candle_count") or 0) != len(candles):
        reasons.append("candle count changed")
    if metadata.get("status") != "READY":
        reasons.append(f"cache status is {metadata.get('status')}")
    hit = not reasons
    return {
        "enabled": True,
        "cache_key": key,
        "cache_hit": hit,
        "status": "HIT" if hit else "MISS",
        "reason": "Cached features are valid." if hit else "Cache invalid: " + ", ".join(reasons),
        "created_at": metadata.get("created_at"),
        "candle_count": int(len(candles)),
        "feature_count": int(metadata.get("feature_count") or 0),
    }


def load_or_calculate_features(
    *,
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    sentiment: str = "NEUTRAL",
    usd_bias: str = "NEUTRAL",
    risk_sentiment: str = "NEUTRAL",
    cb_divergence: str = "NEUTRAL",
    macro_evidence: dict[str, Any] | None = None,
    data_source_controls: dict[str, Any] | None = None,
    use_cache: bool = True,
    persist_cache: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    controls = data_source_controls if isinstance(data_source_controls, dict) else {}
    source = normalize_data_source(controls.get("data_source"))
    provider = str(controls.get("provider") or candles_provider_name(source)).strip()
    candles = load_candles(symbol, timeframe, start_date, end_date, data_source=source)
    if candles.empty:
        raise ValueError(f"No candles found for selected symbol/timeframe/date range and data source '{source}'. Fetch/import that source first.")

    params = feature_params(
        timeframe=timeframe,
        sentiment=sentiment,
        usd_bias=usd_bias,
        risk_sentiment=risk_sentiment,
        cb_divergence=cb_divergence,
        macro_evidence=macro_evidence,
        data_source=source,
    )
    param_hash = params_hash(params)
    key = cache_key(symbol, timeframe, start_date, end_date, param_hash, source)
    fingerprint = candle_fingerprint(candles)
    base_meta = {
        "enabled": bool(use_cache),
        "cache_key": key,
        "params_hash": param_hash,
        "candle_fingerprint": fingerprint,
        "candle_count": int(len(candles)),
        "first_candle_time": candles["timestamp"].iloc[0].isoformat() if not candles.empty else "",
        "last_candle_time": candles["timestamp"].iloc[-1].isoformat() if not candles.empty else "",
    }
    if use_cache:
        metadata = load_feature_cache_metadata(key)
        if metadata and metadata.get("status") == "READY" and metadata.get("candle_fingerprint") == fingerprint and int(metadata.get("candle_count") or 0) == len(candles):
            cached = load_features_for_cache(symbol, timeframe, start_date, end_date, data_source=source)
            if len(cached) == len(candles):
                cached = _attach_candle_columns(cached, candles)
                meta = {**base_meta, "cache_hit": True, "status": "HIT", "reason": "Loaded calculated features from SQLite cache.", "feature_count": int(len(cached)), "created_at": metadata.get("created_at")}
                cached.attrs["feature_cache"] = meta
                return candles, cached, meta

    features = calculate_features(
        candles,
        timeframe=timeframe,
        sentiment=sentiment,
        usd_bias=usd_bias,
        risk_sentiment=risk_sentiment,
        cb_divergence=cb_divergence,
        macro_evidence=macro_evidence,
    )
    saved = 0
    if persist_cache:
        saved = save_features(symbol, timeframe, features, data_source=source, provider=provider)
        save_feature_cache_metadata(
            {
                "cache_key": key,
                "symbol": symbol,
                "timeframe": timeframe,
                "start_date": start_date,
                "end_date": end_date,
                "data_source": source,
                "provider": provider,
                "params_hash": param_hash,
                "candle_fingerprint": fingerprint,
                "candle_count": int(len(candles)),
                "feature_count": int(len(features)),
                "first_candle_time": base_meta["first_candle_time"],
                "last_candle_time": base_meta["last_candle_time"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "READY",
                "reason": "Feature cache refreshed after calculation.",
            }
        )
    meta = {**base_meta, "cache_hit": False, "status": "MISS", "reason": "Calculated features and refreshed cache.", "feature_count": int(len(features)), "saved": saved}
    features.attrs["feature_cache"] = meta
    return candles, features, meta
