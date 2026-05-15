from __future__ import annotations

import copy
import importlib
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.api_response import timestamp
from core.config_manager import ConfigManager


PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MT5_LOCK = threading.RLock()
_UNSET = object()
_MT5_MODULE_OVERRIDE: Any = _UNSET
_ENV_CACHE: dict[str, str] | None = None
_STATUS_CACHE: tuple[float, dict[str, Any]] | None = None
_SYMBOLS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

TIMEFRAME_MAP: dict[str, tuple[int, str]] = {
    "M1": (1, "TIMEFRAME_M1"),
    "M5": (5, "TIMEFRAME_M5"),
    "M15": (15, "TIMEFRAME_M15"),
    "M30": (30, "TIMEFRAME_M30"),
    "H1": (60, "TIMEFRAME_H1"),
    "H4": (240, "TIMEFRAME_H4"),
    "D1": (1440, "TIMEFRAME_D1"),
}


class MT5GatewayError(RuntimeError):
    def __init__(self, code: str, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code


def set_mt5_module_for_tests(module: Any) -> None:
    global _MT5_MODULE_OVERRIDE
    _MT5_MODULE_OVERRIDE = module
    _invalidate_caches()


def clear_mt5_module_for_tests() -> None:
    global _MT5_MODULE_OVERRIDE
    _MT5_MODULE_OVERRIDE = _UNSET
    _invalidate_caches()


def _config() -> dict[str, Any]:
    return ConfigManager(PROJECT_ROOT).load_yaml("systems/mt5_gateway/config.yaml")


def _cache_ttl_seconds(name: str, fallback: float) -> float:
    raw_value = _config().get(name, fallback)
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return fallback


def _invalidate_caches() -> None:
    global _STATUS_CACHE
    _STATUS_CACHE = None
    _SYMBOLS_CACHE.clear()


def _env() -> dict[str, str]:
    global _ENV_CACHE
    if _ENV_CACHE is not None:
        return _ENV_CACHE
    values: dict[str, str] = {}
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#") or "=" not in clean:
                continue
            key, value = clean.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    values.update({key: value for key, value in os.environ.items() if key.startswith("MT5_")})
    _ENV_CACHE = values
    return values


def _obj_to_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "_asdict"):
        return dict(value._asdict())
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _safe_get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    try:
        return value[key]
    except Exception:
        pass
    return getattr(value, key, default)


def _to_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any, default: bool | None = None) -> bool | None:
    if value is None:
        return default
    return bool(value)


def _normalize_symbol_name(symbol: str) -> str:
    return "".join(character for character in symbol.upper() if character.isalnum())


def _preferred_symbols() -> list[str]:
    return [str(item).upper() for item in _config().get("preferred_symbols", [])]


def _sanitize_account_info(account: Any) -> dict[str, Any] | None:
    data = _obj_to_dict(account)
    if data is None:
        return None
    safe_keys = {
        "trade_mode",
        "leverage",
        "limit_orders",
        "margin_so_mode",
        "trade_allowed",
        "trade_expert",
        "margin_mode",
        "currency_digits",
        "fifo_close",
        "balance",
        "credit",
        "profit",
        "equity",
        "margin",
        "margin_free",
        "margin_level",
        "margin_so_call",
        "margin_so_so",
        "currency",
        "server",
        "company",
    }
    return {key: data.get(key) for key in safe_keys if key in data}


def _sanitize_terminal_info(terminal: Any) -> dict[str, Any] | None:
    data = _obj_to_dict(terminal)
    if data is None:
        return None
    sensitive = {"path", "data_path", "commondata_path"}
    return {key: value for key, value in data.items() if key not in sensitive}


def _import_mt5() -> tuple[Any | None, str | None]:
    if _MT5_MODULE_OVERRIDE is not _UNSET:
        if _MT5_MODULE_OVERRIDE is None:
            return None, "MetaTrader5 package is not installed."
        return _MT5_MODULE_OVERRIDE, None
    try:
        return importlib.import_module("MetaTrader5"), None
    except Exception as exc:
        return None, f"MetaTrader5 package is not available: {exc}"


def _last_error(mt5: Any) -> Any:
    try:
        return mt5.last_error()
    except Exception:
        return None


def _initialize_locked(mt5: Any) -> tuple[bool, Any]:
    try:
        env = _env()
        login = env.get("MT5_LOGIN")
        password = env.get("MT5_PASSWORD")
        server = env.get("MT5_SERVER")
        if login and password and server:
            try:
                connected = bool(mt5.initialize(login=int(login), password=password, server=server))
            except TypeError:
                connected = bool(mt5.initialize())
        else:
            connected = bool(mt5.initialize())
    except Exception as exc:
        return False, str(exc)
    return connected, _last_error(mt5)


def initialize() -> dict[str, Any]:
    config = _config()
    if not config.get("enabled", True):
        return {"available": False, "connected": False, "reason": "MT5 gateway is disabled by config.", "last_error": None}
    mt5, reason = _import_mt5()
    if mt5 is None:
        return {"available": False, "connected": False, "reason": reason, "last_error": None}
    with _MT5_LOCK:
        connected, last_error = _initialize_locked(mt5)
    return {"available": True, "connected": connected, "reason": None if connected else "MT5 initialize failed.", "last_error": last_error}


def shutdown() -> dict[str, Any]:
    mt5, reason = _import_mt5()
    if mt5 is None:
        return {"available": False, "shutdown": False, "reason": reason}
    with _MT5_LOCK:
        try:
            return {"available": True, "shutdown": bool(mt5.shutdown()), "reason": None}
        except Exception as exc:
            return {"available": True, "shutdown": False, "reason": str(exc)}


def get_status() -> dict[str, Any]:
    global _STATUS_CACHE
    ttl_seconds = _cache_ttl_seconds("status_cache_seconds", 2.0)
    now = time.time()
    if _STATUS_CACHE is not None:
        cached_at, cached_payload = _STATUS_CACHE
        if now - cached_at <= ttl_seconds:
            return copy.deepcopy(cached_payload)

    init = initialize()
    status = {
        "available": init["available"],
        "connected": init["connected"],
        "terminal_info": None,
        "account_info": None,
        "server": None,
        "currency": None,
        "balance": None,
        "equity": None,
        "margin": None,
        "free_margin": None,
        "last_error": init.get("last_error"),
        "checked_at": timestamp(),
        "reason": init.get("reason"),
    }
    if not init["available"] or not init["connected"]:
        return status
    mt5, _ = _import_mt5()
    with _MT5_LOCK:
        terminal = mt5.terminal_info()
        account = mt5.account_info()
    safe_account = _sanitize_account_info(account)
    status.update(
        {
            "terminal_info": _sanitize_terminal_info(terminal),
            "account_info": safe_account,
            "server": _safe_get(account, "server"),
            "currency": _safe_get(account, "currency"),
            "balance": _to_float(_safe_get(account, "balance")),
            "equity": _to_float(_safe_get(account, "equity")),
            "margin": _to_float(_safe_get(account, "margin")),
            "free_margin": _to_float(_safe_get(account, "margin_free")),
            "last_error": _last_error(mt5),
            "reason": None,
        }
    )
    _STATUS_CACHE = (now, copy.deepcopy(status))
    return status


def get_timeframes() -> list[dict[str, Any]]:
    allowed = set(_config().get("allowed_timeframes", TIMEFRAME_MAP.keys()))
    return [
        {"key": key, "label": key, "minutes": minutes, "mt5_constant_name": constant_name}
        for key, (minutes, constant_name) in TIMEFRAME_MAP.items()
        if key in allowed
    ]


def _timeframe_constant(mt5: Any, key: str) -> int:
    normalized = key.upper()
    if normalized not in TIMEFRAME_MAP:
        raise MT5GatewayError("invalid_timeframe", f"Unsupported timeframe: {key}", 400)
    _, constant_name = TIMEFRAME_MAP[normalized]
    if not hasattr(mt5, constant_name):
        raise MT5GatewayError("mt5_timeframe_missing", f"MT5 module does not expose {constant_name}.", 500)
    return int(getattr(mt5, constant_name))


def _ensure_connected() -> Any:
    init = initialize()
    if not init["available"]:
        raise MT5GatewayError("mt5_unavailable", init.get("reason") or "MT5 unavailable.", 503)
    if not init["connected"]:
        raise MT5GatewayError("mt5_disconnected", init.get("reason") or "MT5 is not connected.", 503)
    mt5, _ = _import_mt5()
    return mt5


def _symbol_info_or_error(mt5: Any, symbol: str) -> Any:
    clean_symbol = resolve_symbol(symbol)
    if not clean_symbol:
        raise MT5GatewayError("invalid_symbol", "Symbol is required.", 400)
    with _MT5_LOCK:
        info = mt5.symbol_info(clean_symbol)
        if info is None:
            raise MT5GatewayError("invalid_symbol", f"Symbol not found in MT5: {clean_symbol}", 404)
        if not bool(_safe_get(info, "visible", False)) and hasattr(mt5, "symbol_select"):
            mt5.symbol_select(clean_symbol, True)
    return info


def _symbol_payload(item: Any) -> dict[str, Any]:
    symbol = str(_safe_get(item, "name", ""))
    normalized = _normalize_symbol_name(symbol)
    preferred = _preferred_symbols()
    popular_alias = next((alias for alias in preferred if normalized.startswith(alias)), None)
    return {
        "symbol": symbol,
        "description": _safe_get(item, "description"),
        "path": _safe_get(item, "path"),
        "base_currency": _safe_get(item, "currency_base"),
        "profit_currency": _safe_get(item, "currency_profit"),
        "margin_currency": _safe_get(item, "currency_margin"),
        "digits": _to_int(_safe_get(item, "digits")),
        "point": _to_float(_safe_get(item, "point")),
        "trade_mode": _to_int(_safe_get(item, "trade_mode")),
        "visible": _to_bool(_safe_get(item, "visible")),
        "spread": _to_int(_safe_get(item, "spread")),
        "selected": _to_bool(_safe_get(item, "select", _safe_get(item, "visible"))),
        "popular": popular_alias is not None,
        "popular_alias": popular_alias,
    }


def _symbols_get(mt5: Any, group: str | None = None) -> list[Any]:
    try:
        if group:
            return list(mt5.symbols_get(group=group) or [])
        return list(mt5.symbols_get() or [])
    except TypeError:
        return list(mt5.symbols_get() or [])


def _preferred_symbol_payloads(mt5: Any) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    seen: set[str] = set()
    for alias in _preferred_symbols():
        info = None
        with _MT5_LOCK:
            info = mt5.symbol_info(alias)
        if info is None:
            candidates = _symbols_get(mt5, group=f"*{alias}*")
            candidates.sort(key=lambda item: (0 if _normalize_symbol_name(_safe_get(item, "name", "")).startswith(alias) else 1, str(_safe_get(item, "name", ""))))
            info = next((item for item in candidates if alias in _normalize_symbol_name(_safe_get(item, "name", ""))), None)
        if info is None:
            continue
        payload = _symbol_payload(info)
        if payload["symbol"] in seen:
            continue
        seen.add(payload["symbol"])
        payloads.append(payload)
    return payloads


def get_symbols() -> dict[str, Any]:
    ttl_seconds = _cache_ttl_seconds("symbols_cache_seconds", 30.0)
    try:
        mt5 = _ensure_connected()
    except MT5GatewayError as exc:
        return {"symbols": [], "available": False, "connected": False, "reason": exc.detail}
    mode = str(_config().get("symbol_filter_mode", "all")).lower()
    now = time.time()
    cached_entry = _SYMBOLS_CACHE.get(mode)
    if cached_entry is not None:
        cached_at, cached_payload = cached_entry
        if now - cached_at <= ttl_seconds:
            return copy.deepcopy(cached_payload)

    preferred = _preferred_symbols()
    preferred_symbols = _preferred_symbol_payloads(mt5) if preferred and mode in {"preferred", "preferred_then_all"} else []
    if mode == "preferred" or (mode == "preferred_then_all" and preferred_symbols):
        payload = {
            "symbols": preferred_symbols,
            "available": True,
            "connected": True,
            "reason": None,
            "filtered": True,
            "filter_mode": mode,
            "total_symbols": len(preferred_symbols),
        }
        _SYMBOLS_CACHE[mode] = (now, copy.deepcopy(payload))
        return payload
    raw_symbols = _symbols_get(mt5)
    symbols = [_symbol_payload(item) for item in raw_symbols if _safe_get(item, "name")]
    if mode == "visible":
        symbols = [item for item in symbols if item.get("visible")]
    elif mode == "tradable":
        symbols = [item for item in symbols if item.get("trade_mode") not in (None, 0, "disabled")]
    preferred_rank = {symbol: index for index, symbol in enumerate(preferred)}
    symbols.sort(
        key=lambda item: (
            preferred_rank.get(str(item.get("popular_alias") or ""), len(preferred)),
            0 if item.get("popular") else 1,
            item["symbol"],
        )
    )
    payload = {"symbols": symbols, "available": True, "connected": True, "reason": None, "filtered": False, "filter_mode": mode, "total_symbols": len(symbols)}
    _SYMBOLS_CACHE[mode] = (now, copy.deepcopy(payload))
    return payload


def resolve_symbol(symbol: str) -> str:
    requested = symbol.strip()
    if not requested:
        raise MT5GatewayError("invalid_symbol", "Symbol is required.", 400)
    mt5 = _ensure_connected()
    with _MT5_LOCK:
        exact = mt5.symbol_info(requested)
    if exact is not None:
        return requested
    requested_normalized = _normalize_symbol_name(requested)
    symbols = get_symbols().get("symbols", [])
    for item in symbols:
        if _normalize_symbol_name(item["symbol"]) == requested_normalized:
            return item["symbol"]
    for item in symbols:
        normalized = _normalize_symbol_name(item["symbol"])
        if normalized.startswith(requested_normalized) or requested_normalized in normalized:
            return item["symbol"]
    raise MT5GatewayError("invalid_symbol", f"Symbol not found in MT5: {requested}", 404)


def _to_iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return str(value)


def _rate_row(row: Any) -> dict[str, Any]:
    return {
        "time": _to_iso(_safe_get(row, "time")),
        "open": _to_float(_safe_get(row, "open"), 0.0),
        "high": _to_float(_safe_get(row, "high"), 0.0),
        "low": _to_float(_safe_get(row, "low"), 0.0),
        "close": _to_float(_safe_get(row, "close"), 0.0),
        "tick_volume": _to_int(_safe_get(row, "tick_volume"), 0),
        "spread": _to_int(_safe_get(row, "spread"), 0),
        "real_volume": _to_int(_safe_get(row, "real_volume"), 0),
    }


def get_rates(symbol: str, timeframe: str, bars: int | None = None) -> dict[str, Any]:
    config = _config()
    max_bars = int(config.get("max_bars", 5000))
    requested = int(bars if bars is not None else config.get("default_bars", 500))
    if requested < 1:
        raise MT5GatewayError("invalid_bars", "Bars must be at least 1.", 400)
    if requested > max_bars:
        raise MT5GatewayError("bars_limit_exceeded", f"Bars limit exceeded: {requested} > {max_bars}.", 400)
    mt5 = _ensure_connected()
    clean_symbol = resolve_symbol(symbol)
    _symbol_info_or_error(mt5, clean_symbol)
    mt5_timeframe = _timeframe_constant(mt5, timeframe)
    with _MT5_LOCK:
        rates = mt5.copy_rates_from_pos(clean_symbol, mt5_timeframe, 0, requested)
    if rates is None:
        raise MT5GatewayError("rates_unavailable", f"MT5 returned no rates for {clean_symbol} {timeframe}.", 503)
    rows = [_rate_row(row) for row in list(rates)]
    return {
        "metadata": {
            "symbol": clean_symbol,
            "timeframe": timeframe.upper(),
            "bars_requested": requested,
            "bars_returned": len(rows),
            "source": "mt5",
            "fetched_at": timestamp(),
        },
        "rows": rows,
    }


def get_tick(symbol: str) -> dict[str, Any]:
    mt5 = _ensure_connected()
    clean_symbol = resolve_symbol(symbol)
    info = _symbol_info_or_error(mt5, clean_symbol)
    with _MT5_LOCK:
        tick = mt5.symbol_info_tick(clean_symbol)
    if tick is None:
        raise MT5GatewayError("tick_unavailable", f"MT5 returned no tick for {clean_symbol}.", 503)
    bid = _to_float(_safe_get(tick, "bid"))
    ask = _to_float(_safe_get(tick, "ask"))
    point = _to_float(_safe_get(info, "point"), 0.0) or 0.0
    spread_price = float(ask - bid) if bid is not None and ask is not None else None
    spread_points = spread_price / point if spread_price is not None and point else None
    return {
        "bid": bid,
        "ask": ask,
        "last": _to_float(_safe_get(tick, "last")),
        "spread_points": spread_points,
        "spread_price": spread_price,
        "time": _to_iso(_safe_get(tick, "time")),
        "symbol": clean_symbol,
        "source": "mt5",
    }
