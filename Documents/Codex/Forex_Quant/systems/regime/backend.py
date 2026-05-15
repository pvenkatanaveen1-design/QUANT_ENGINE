from __future__ import annotations

import copy
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.config_manager import ConfigManager
from systems.data import backend as data_backend
from systems.data.service import load_cleaned_rows
from systems.regime import research as regime_research
from systems.regime import service
from systems.strategy_router import backend as strategy_backend


PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SNAPSHOT_CACHE_LOCK = threading.Lock()
_SNAPSHOT_CACHE: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
_SNAPSHOT_TTL_SECONDS = 12.0


def detect_latest_regime(symbol: str = "EURUSD", timeframe: str = "M15") -> Any:
    data_result = data_backend.fetch_mt5_bars(symbol.upper(), timeframe.upper(), bars=500)
    rows = load_cleaned_rows(data_result.symbol, data_result.timeframe)
    return service.detect_regime_for_rows(rows, symbol=data_result.symbol, timeframe=data_result.timeframe)


def detect_regime_for_dataframe(dataframe: Any, symbol: str = "UNKNOWN", timeframe: str = "UNKNOWN") -> Any:
    rows = service.dataframe_to_rows(dataframe)
    return service.detect_regime_for_rows(rows, symbol=symbol, timeframe=timeframe)


def calculate_feature_snapshot(dataframe: Any) -> Any:
    rows = service.dataframe_to_rows(dataframe)
    return service.calculate_feature_snapshot(rows)


def explain_regime(regime_id: str) -> dict[str, Any]:
    config = ConfigManager(PROJECT_ROOT).load_yaml("config/regimes.yaml")
    base, _, modifier = regime_id.partition("_")
    return {
        "regime_id": regime_id,
        "base": config.get("base_regimes", {}).get(base, {}),
        "modifier": config.get("modifiers", {}).get(modifier, {}),
    }


def latest_regime_as_dict(symbol: str = "EURUSD", timeframe: str = "M15") -> dict[str, Any]:
    try:
        result = detect_latest_regime(symbol, timeframe)
        return asdict(result)
    except Exception as exc:
        return {
            "base_regime": "Q4",
            "modifier": "M01",
            "regime_id": "Q4_M01",
            "confidence": 0.0,
            "tradable": False,
            "risk_posture": "missing_data",
            "reasons": [{"code": "missing_data", "message": str(exc), "severity": "warning"}],
            "features": {},
        }


def _default_week_bars(timeframe: str) -> int:
    minutes_by_key = {item["key"]: int(item["minutes"]) for item in data_backend.get_market_options().get("timeframes", [])}
    minutes = minutes_by_key.get(timeframe.upper(), 15)
    week_bars = int((7 * 24 * 60) / max(minutes, 1))
    return min(max(week_bars + 260, 300), 5000)


def get_regime_options() -> dict[str, Any]:
    definitions = ConfigManager(PROJECT_ROOT).load_yaml("config/regimes.yaml")
    regimes = [f"{base}_{modifier}" for base in definitions.get("base_regimes", {}) for modifier in definitions.get("modifiers", {})]
    options = data_backend.get_market_options()
    options["regime_library"] = regimes
    return options


def _snapshot_cache_key(
    source: str,
    symbol: str,
    timeframe: str,
    bars: int,
    killzone_enabled: bool,
    include_spread_filter: bool,
    include_sweep_detection: bool,
    include_alpha_features: bool,
    selected_regime: str | None,
) -> tuple[Any, ...]:
    return (
        source,
        symbol.upper(),
        timeframe.upper(),
        int(bars),
        bool(killzone_enabled),
        bool(include_spread_filter),
        bool(include_sweep_detection),
        bool(include_alpha_features),
        selected_regime.upper() if selected_regime else "",
    )


def _snapshot_cache_get(cache_key: tuple[Any, ...], force_refresh: bool) -> dict[str, Any] | None:
    if force_refresh:
        return None
    now = time.time()
    with _SNAPSHOT_CACHE_LOCK:
        cached = _SNAPSHOT_CACHE.get(cache_key)
    if not cached:
        return None
    cached_at, payload = cached
    if now - cached_at > _SNAPSHOT_TTL_SECONDS:
        return None
    return copy.deepcopy(payload)


def _snapshot_cache_set(cache_key: tuple[Any, ...], payload: dict[str, Any]) -> None:
    with _SNAPSHOT_CACHE_LOCK:
        _SNAPSHOT_CACHE[cache_key] = (time.time(), copy.deepcopy(payload))


def _scenario_family(strategy: dict[str, Any]) -> str:
    name = str(strategy.get("name", "")).lower()
    family = str(strategy.get("family", "general"))
    if "sweep" in name or family in {"liquidity", "sweep_reversal"}:
        return "sweep_reversal"
    if "bollinger" in name or "rsi" in name or "fade" in name:
        return "mean_reversion"
    if "break" in name or "donchian" in name or "channel" in name or "atr" in name:
        return "breakout"
    if "no-trade" in name or "defensive" in name or "circuit" in name:
        return "defensive"
    return family


def _strategy_is_scenario_executable(strategy: dict[str, Any]) -> bool:
    research_spec = strategy.get("research_spec") or {}
    if "scenario_executable" in research_spec:
        return bool(research_spec.get("scenario_executable"))
    return _scenario_family(strategy) in {"trend_momentum", "breakout", "mean_reversion", "sweep_reversal", "defensive"}


def _latest_entry_for_regime(snapshot: dict[str, Any], regime_id: str) -> dict[str, Any] | None:
    current = snapshot.get("current_regime") or {}
    if current.get("regime_id") == regime_id:
        return current
    latest_by_regime = snapshot.get("latest_observation_by_regime") or {}
    return latest_by_regime.get(regime_id)


def build_trade_state(snapshot: dict[str, Any], selected_regime: str) -> dict[str, Any]:
    playbook = regime_research.enrich_playbook(strategy_backend.get_by_regime(selected_regime, mode="research"), selected_regime)
    selected_entry = _latest_entry_for_regime(snapshot, selected_regime)
    current = snapshot.get("current_regime") or {}
    features = (selected_entry or current).get("features", {}) if (selected_entry or current) else {}
    microstructure = features.get("extra") or {}
    tick: dict[str, Any] = {}
    try:
        tick = data_backend.get_latest_tick(str(snapshot.get("symbol") or ""))
    except Exception as exc:
        tick = {"available": False, "error": str(exc)}

    candidates = playbook.get("candidates", [])
    allowed_strategy_keys = [item["id"] for item in candidates if _strategy_is_scenario_executable(item)]
    blocked_strategy_keys = [item["id"] for item in candidates if item["id"] not in allowed_strategy_keys]
    research_model = playbook.get("research_model") or regime_research.regime_model(selected_regime)
    regime_tradable = bool((selected_entry or current).get("tradable")) if (selected_entry or current) else False
    regime_block_reasons = []
    if not selected_entry:
        regime_block_reasons.append("selected regime not observed in this analysis window")
    if not regime_tradable:
        regime_block_reasons.append(str((selected_entry or current).get("risk_posture") or "regime not tradable"))

    market_values = {
        "bid": tick.get("bid"),
        "ask": tick.get("ask"),
        "spread_points": tick.get("spread_points"),
        "spread_price": tick.get("spread_price"),
        "latest_close": (selected_entry or current).get("close") if (selected_entry or current) else None,
        "latest_bar_time": (selected_entry or current).get("latest_bar_time") or (selected_entry or current).get("time") if (selected_entry or current) else None,
        "atr": features.get("atr"),
        "adx": features.get("adx"),
        "trend_efficiency": features.get("trend_efficiency"),
        "volatility_percentile": features.get("volatility_percentile"),
        "spread_percentile": features.get("spread_percentile"),
        "compression_percentile": features.get("compression_percentile"),
        "sweep_high": features.get("sweep_high"),
        "sweep_low": features.get("sweep_low"),
        "tick_volume": microstructure.get("tick_volume"),
        "tick_volume_ratio": microstructure.get("tick_volume_ratio"),
        "institutional_trap_score": microstructure.get("institutional_trap_score"),
        "liquidity_sweep_direction": microstructure.get("liquidity_sweep_direction"),
        "retail_stop_zones": microstructure.get("retail_stop_zones"),
        "near_round_number": microstructure.get("near_round_number"),
        "round_number_distance_pips": microstructure.get("round_number_distance_pips"),
        "nearest_round_number": microstructure.get("nearest_round_number"),
        "news_proxy": microstructure.get("news_proxy"),
        "sentiment_status": microstructure.get("sentiment_status"),
        "session": (selected_entry or current).get("session") if (selected_entry or current) else None,
        "killzone": (selected_entry or current).get("killzone") if (selected_entry or current) else None,
    }
    source_keys: list[str] = []
    source_keys.extend(research_model.get("sources", []))
    for item in candidates:
        source_keys.extend((item.get("research_spec") or {}).get("sources", []))
    source_keys = sorted(set(str(key) for key in source_keys if key))
    return {
        "selected_regime_id": selected_regime,
        "strategy_playbook": playbook,
        "research_model": research_model,
        "research_sources": regime_research.source_details(source_keys),
        "news_sentiment_status": regime_research.news_sentiment_status(),
        "selected_strategy_candidates": candidates,
        "allowed_strategy_keys": allowed_strategy_keys,
        "blocked_strategy_keys": blocked_strategy_keys,
        "regime_tradable": regime_tradable,
        "regime_block_reasons": regime_block_reasons,
        "selected_regime_values": selected_entry,
        "current_market_values": market_values,
        "microstructure_values": microstructure,
        "formula_status": {
            item["id"]: {
                "scenario_executable": _strategy_is_scenario_executable(item),
                "family": _scenario_family(item),
                "status": item.get("status", "not_tested"),
                "live_allowed": False,
                "expected_win_rate_mid": (item.get("research_spec") or {}).get("expected_win_rate_mid"),
                "expected_rrr": (item.get("research_spec") or {}).get("expected_rrr"),
                "expected_ev_r": (item.get("research_spec") or {}).get("expected_ev_r"),
                "entry_logic": (item.get("research_spec") or {}).get("entry_logic"),
                "invalid_when": (item.get("research_spec") or {}).get("invalid_when"),
            }
            for item in candidates
        },
        "proposed_trade_context": {
            "symbol": snapshot.get("symbol"),
            "timeframe": snapshot.get("timeframe"),
            "regime_id": selected_regime,
            "risk_mode": (selected_entry or current).get("risk_posture") if (selected_entry or current) else "not_observed",
            "risk_multiplier": research_model.get("risk_multiplier"),
            "expected_ev_r": research_model.get("expected_ev_r"),
            "institutional_trap_score": microstructure.get("institutional_trap_score"),
            "retail_stop_zones": microstructure.get("retail_stop_zones"),
            "live_trading_enabled": False,
            "real_order_enabled": False,
            "reason": "research_or_demo_only",
        },
    }


def run_one_week_test(
    source: str = "mt5_demo",
    symbol: str = "EURUSD",
    timeframe: str = "M15",
    bars: int | None = None,
    killzone_enabled: bool = True,
    include_spread_filter: bool = True,
    include_sweep_detection: bool = True,
    include_alpha_features: bool = True,
    selected_regime: str | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    if source != "mt5_demo":
        raise ValueError("Only MT5 data is supported for regime snapshots. Offline fallback is disabled.")
    requested_bars = int(bars or _default_week_bars(timeframe))
    selected_regime = selected_regime.upper() if selected_regime else None
    cache_key = _snapshot_cache_key(
        source,
        symbol,
        timeframe,
        requested_bars,
        killzone_enabled,
        include_spread_filter,
        include_sweep_detection,
        include_alpha_features,
        selected_regime,
    )
    cached = _snapshot_cache_get(cache_key, force_refresh=force_refresh)
    if cached is not None:
        return cached
    data_result = data_backend.fetch_mt5_bars(symbol.upper(), timeframe.upper(), bars=requested_bars)
    symbol = data_result.symbol
    timeframe = data_result.timeframe
    rows = load_cleaned_rows(symbol.upper(), timeframe.upper())
    snapshot = service.analyze_regime_window(
        rows[-requested_bars:],
        symbol=symbol.upper(),
        timeframe=timeframe.upper(),
        killzone_enabled=killzone_enabled,
        include_spread_filter=include_spread_filter,
        include_sweep_detection=include_sweep_detection,
        include_alpha_features=include_alpha_features,
    )
    quality = data_backend.get_quality_report(symbol.upper(), timeframe.upper())
    selected_regime = selected_regime or (snapshot.get("current_regime") or {}).get("regime_id") or "Q4_M01"
    snapshot["data_quality"] = quality
    snapshot["data_result"] = (
        {
            "symbol": data_result.symbol,
            "timeframe": data_result.timeframe,
            "source_path": data_result.source_path,
            "cleaned_path": data_result.cleaned_path,
            "report_path": data_result.report_path,
            "rows_in": data_result.rows_in,
            "rows_out": data_result.rows_out,
            "quality_status": data_result.quality_status,
            "issues": [issue.__dict__ for issue in data_result.issues],
            "metadata": data_result.metadata,
        }
        if data_result
        else None
    )
    snapshot["selected_regime"] = selected_regime
    snapshot["trade_state"] = build_trade_state(snapshot, selected_regime)
    snapshot["strategy_playbook"] = snapshot["trade_state"].get("strategy_playbook")
    snapshot["research_model"] = snapshot["trade_state"].get("research_model")
    snapshot["research_sources"] = snapshot["trade_state"].get("research_sources")
    snapshot["news_sentiment_status"] = snapshot["trade_state"].get("news_sentiment_status")
    snapshot["control_state"] = {
        "source": source,
        "symbol": symbol.upper(),
        "timeframe": timeframe.upper(),
        "bars": requested_bars,
        "killzone_enabled": killzone_enabled,
        "include_spread_filter": include_spread_filter,
        "include_sweep_detection": include_sweep_detection,
        "include_alpha_features": include_alpha_features,
        "selected_regime": selected_regime,
    }
    snapshot["api_request"] = {
        "method": "GET",
        "url": "/api/regimes/scan",
        "query": {
            "symbol": symbol.upper(),
            "timeframe": timeframe.upper(),
            "bars": requested_bars,
            "lookback_days": 7,
            "killzone_enabled": killzone_enabled,
            "selected_regime": selected_regime,
        },
    }
    snapshot["api_links"] = {
        "scan": f"/api/regimes/scan?symbol={symbol.upper()}&timeframe={timeframe.upper()}&bars={requested_bars}&killzone_enabled={str(killzone_enabled).lower()}",
        "current": f"/api/regimes/current?symbol={symbol.upper()}&timeframe={timeframe.upper()}",
        "change_stats": f"/api/regimes/change-stats?symbol={symbol.upper()}&timeframe={timeframe.upper()}",
        "trade_state": f"/api/regimes/{selected_regime}/trade-state?symbol={symbol.upper()}&timeframe={timeframe.upper()}",
        "live_ws": f"/ws/regime/live?symbol={symbol.upper()}&timeframe={timeframe.upper()}",
    }
    snapshot["source"] = source
    _snapshot_cache_set(cache_key, snapshot)
    return snapshot


def run_regime_scan(
    symbol: str = "EURUSD",
    timeframe: str = "M15",
    lookback_days: int = 7,
    bars: int | None = None,
    killzone_enabled: bool = True,
    selected_regime: str | None = None,
    source: str = "mt5_demo",
) -> dict[str, Any]:
    requested_bars = int(bars or _default_week_bars(timeframe))
    if bars in (None, 0):
        requested_bars = int((max(1, lookback_days) * 24 * 60) / max(1, _timeframe_minutes_from_key(timeframe))) + 260
    requested_bars = min(max(requested_bars, 60), 5000)
    return run_one_week_test(
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        bars=requested_bars,
        killzone_enabled=killzone_enabled,
        include_spread_filter=True,
        include_sweep_detection=True,
        include_alpha_features=True,
        selected_regime=selected_regime,
    )


def _timeframe_minutes_from_key(timeframe: str) -> int:
    key = str(timeframe).upper()
    if key.startswith("M"):
        return max(1, int(key[1:] or 1))
    if key.startswith("H"):
        return max(1, int(key[1:] or 1) * 60)
    if key.startswith("D"):
        return max(1, int(key[1:] or 1) * 1440)
    return 15


def current_regime_state(symbol: str = "EURUSD", timeframe: str = "M15") -> dict[str, Any]:
    snapshot = run_regime_scan(symbol=symbol, timeframe=timeframe, bars=0)
    return {
        "symbol": snapshot.get("symbol"),
        "timeframe": snapshot.get("timeframe"),
        "current_regime": snapshot.get("current_regime"),
        "previous_regime": snapshot.get("previous_regime"),
        "active_since": snapshot.get("active_since"),
        "active_duration_minutes": snapshot.get("active_duration_minutes"),
        "change_stats": snapshot.get("change_stats"),
        "trade_state": snapshot.get("trade_state"),
    }


def regime_change_stats(symbol: str = "EURUSD", timeframe: str = "M15", lookback_days: int = 7) -> dict[str, Any]:
    snapshot = run_regime_scan(symbol=symbol, timeframe=timeframe, lookback_days=lookback_days, bars=0)
    return {
        "symbol": snapshot.get("symbol"),
        "timeframe": snapshot.get("timeframe"),
        "bars_analyzed": snapshot.get("bars_analyzed"),
        "current_regime": snapshot.get("current_regime"),
        "previous_regime": snapshot.get("previous_regime"),
        "change_stats": snapshot.get("change_stats"),
        "regime_transition_table": snapshot.get("regime_transition_table"),
    }


def trade_state_for_regime(symbol: str, timeframe: str, regime_id: str, bars: int | None = None) -> dict[str, Any]:
    snapshot = run_regime_scan(symbol=symbol, timeframe=timeframe, bars=bars or 0, selected_regime=regime_id)
    return {
        "symbol": snapshot.get("symbol"),
        "timeframe": snapshot.get("timeframe"),
        "selected_regime": snapshot.get("selected_regime"),
        "current_regime": snapshot.get("current_regime"),
        "previous_regime": snapshot.get("previous_regime"),
        "strategy_playbook": snapshot.get("strategy_playbook"),
        "trade_state": snapshot.get("trade_state"),
        "api_links": snapshot.get("api_links"),
    }
