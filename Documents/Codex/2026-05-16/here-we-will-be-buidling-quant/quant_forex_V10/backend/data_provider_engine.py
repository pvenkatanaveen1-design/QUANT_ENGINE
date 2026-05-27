from __future__ import annotations

import lzma
import os
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from dotenv import load_dotenv

from backend.database import DEFAULT_DATA_SOURCE, normalize_data_source, save_candles
from backend.mt5.mt5_client import fetch_candles as fetch_mt5_candles


PROVIDER_META: dict[str, dict[str, Any]] = {
    "mt5_retail_candles": {
        "label": "MT5 retail candles",
        "free": "Broker/account dependent, usually free",
        "env": ["MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_PATH"],
        "needs_key": False,
        "provider": "MT5 / SQLite",
    },
    "mt5_every_tick": {
        "label": "MT5 every tick report",
        "free": "Broker/account dependent, usually free",
        "env": ["MT5_PATH"],
        "needs_key": False,
        "provider": "MT5 Strategy Tester",
    },
    "mt5_real_ticks": {
        "label": "MT5 real ticks report",
        "free": "Broker/account dependent, usually free",
        "env": ["MT5_PATH"],
        "needs_key": False,
        "provider": "MT5 Strategy Tester",
    },
    "dukascopy_ticks": {
        "label": "Dukascopy historical ticks",
        "free": "Free public historical tick feed; large ranges can be slow",
        "env": [],
        "needs_key": False,
        "provider": "Dukascopy",
    },
    "alpha_vantage_fx": {
        "label": "Alpha Vantage FX",
        "free": "Free API key with limits",
        "env": ["ALPHA_VANTAGE_API_KEY"],
        "needs_key": True,
        "provider": "Alpha Vantage",
    },
    "twelve_data_fx": {
        "label": "Twelve Data FX",
        "free": "Free/trial API limits apply",
        "env": ["TWELVE_DATA_API_KEY"],
        "needs_key": True,
        "provider": "Twelve Data",
    },
    "polygon_fx": {
        "label": "Polygon.io Forex",
        "free": "Free tier/trial limits apply",
        "env": ["POLYGON_API_KEY"],
        "needs_key": True,
        "provider": "Polygon.io",
    },
    "csv_import": {
        "label": "CSV URL/local file",
        "free": "Free when you provide a CSV file or URL",
        "env": ["DATA_PROVIDER_CSV_PATH", "DATA_PROVIDER_CSV_URL"],
        "needs_key": False,
        "provider": "CSV import",
    },
    "cme_fx_futures_proxy": {
        "label": "CME FX futures proxy",
        "free": "Delayed/free CSV sources may work; high quality history is usually paid",
        "env": ["CME_FX_CSV_PATH", "CME_FX_CSV_URL"],
        "needs_key": False,
        "provider": "CME FX futures proxy",
    },
    "prime_broker_ticks": {
        "label": "Prime broker ticks",
        "free": "Usually paid",
        "env": ["PRIME_BROKER_CSV_PATH", "PRIME_BROKER_CSV_URL"],
        "needs_key": False,
        "provider": "Prime broker CSV import",
    },
    "ecn_l2_order_book": {
        "label": "ECN L2 order book",
        "free": "Usually paid",
        "env": ["ECN_L2_CSV_PATH", "ECN_L2_CSV_URL"],
        "needs_key": False,
        "provider": "ECN L2 CSV import",
    },
    "reuters_ebs_tick": {
        "label": "Reuters/EBS tick",
        "free": "Paid institutional feed",
        "env": ["REUTERS_EBS_CSV_PATH", "REUTERS_EBS_CSV_URL"],
        "needs_key": False,
        "provider": "Reuters/EBS CSV import",
    },
    "bloomberg_bpipe_tick": {
        "label": "Bloomberg BPIPE tick",
        "free": "Paid institutional feed",
        "env": ["BLOOMBERG_BPIPE_CSV_PATH", "BLOOMBERG_BPIPE_CSV_URL"],
        "needs_key": False,
        "provider": "Bloomberg BPIPE CSV import",
    },
    "institutional_order_flow": {
        "label": "Institutional order-flow CSV",
        "free": "Usually paid",
        "env": ["INSTITUTIONAL_FLOW_CSV_PATH", "INSTITUTIONAL_FLOW_CSV_URL"],
        "needs_key": False,
        "provider": "Institutional flow CSV import",
    },
}

TIMEFRAME_TO_PANDAS = {
    "M1": "1min",
    "M5": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1D",
}

ALPHA_INTERVALS = {"M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min", "H1": "60min"}
TWELVE_INTERVALS = {"M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min", "H1": "1h", "H4": "4h", "D1": "1day"}
POLYGON_INTERVALS = {
    "M1": (1, "minute"),
    "M5": (5, "minute"),
    "M15": (15, "minute"),
    "M30": (30, "minute"),
    "H1": (1, "hour"),
    "H4": (4, "hour"),
    "D1": (1, "day"),
}


def provider_name(data_source: str | None) -> str:
    source = normalize_data_source(data_source)
    return PROVIDER_META.get(source, {}).get("provider", source.replace("_", " ").title())


def data_source_catalog() -> dict[str, Any]:
    load_dotenv()
    providers = []
    for source, meta in PROVIDER_META.items():
        env_names = meta.get("env", [])
        configured_env = [name for name in env_names if os.getenv(name)]
        providers.append(
            {
                "value": source,
                "label": meta["label"],
                "provider": meta["provider"],
                "free": meta["free"],
                "needs_key": bool(meta.get("needs_key")),
                "env": env_names,
                "configured_env": configured_env,
                "configured": not meta.get("needs_key") or bool(configured_env),
            }
        )
    return {
        "default": DEFAULT_DATA_SOURCE,
        "providers": providers,
        "note": "API keys can be entered in the UI for this run or stored in .env with the listed variable names.",
    }


def _controls(raw: dict[str, Any] | None) -> dict[str, Any]:
    load_dotenv()
    controls = dict(raw or {})
    source = normalize_data_source(controls.get("data_source"))
    controls["data_source"] = source
    controls["provider"] = str(controls.get("provider") or provider_name(source))
    return controls


def _api_key(controls: dict[str, Any], *names: str) -> str:
    value = str(controls.get("api_key") or "").strip()
    if value:
        return value
    for name in names:
        env_value = os.getenv(name)
        if env_value:
            return env_value.strip()
    return ""


def _date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _range_mask(frame: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    start = _date(start_date)
    end = _date(end_date)
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    return frame[(timestamps >= start) & (timestamps <= end)].copy()


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp")
    output = []
    for _, row in frame.iterrows():
        output.append(
            {
                "timestamp": pd.to_datetime(row["timestamp"], utc=True).isoformat(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "tick_volume": float(row.get("tick_volume", 0) or 0),
                "spread": float(row.get("spread", 0) or 0),
                "real_volume": float(row.get("real_volume", 0) or 0),
            }
        )
    return output


def _normalize_ohlc_frame(frame: pd.DataFrame, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    rename = {col: str(col).strip().lower().replace(" ", "_") for col in frame.columns}
    frame = frame.rename(columns=rename)
    aliases = {
        "datetime": "timestamp",
        "date": "timestamp",
        "time": "timestamp",
        "o": "open",
        "h": "high",
        "l": "low",
        "c": "close",
        "v": "real_volume",
        "volume": "real_volume",
        "tickvol": "tick_volume",
        "tick_volume": "tick_volume",
    }
    frame = frame.rename(columns={key: value for key, value in aliases.items() if key in frame.columns})
    if {"open", "high", "low", "close", "timestamp"}.issubset(frame.columns):
        out = frame[["timestamp", "open", "high", "low", "close"]].copy()
        out["tick_volume"] = pd.to_numeric(frame.get("tick_volume", frame.get("real_volume", 0)), errors="coerce").fillna(0)
        out["spread"] = pd.to_numeric(frame.get("spread", 0), errors="coerce").fillna(0)
        out["real_volume"] = pd.to_numeric(frame.get("real_volume", 0), errors="coerce").fillna(0)
        out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
        for col in ["open", "high", "low", "close"]:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        return _range_mask(out.dropna(subset=["timestamp", "open", "high", "low", "close"]), start_date, end_date)

    price_col = next((col for col in ["last", "price", "mid", "close"] if col in frame.columns), None)
    if not price_col and {"bid", "ask"}.issubset(frame.columns):
        frame["mid"] = (pd.to_numeric(frame["bid"], errors="coerce") + pd.to_numeric(frame["ask"], errors="coerce")) / 2
        price_col = "mid"
    if not price_col or "timestamp" not in frame.columns:
        raise ValueError("CSV data needs OHLC columns or tick columns with timestamp plus price/last or bid/ask.")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["price"] = pd.to_numeric(frame[price_col], errors="coerce")
    if {"bid", "ask"}.issubset(frame.columns):
        frame["spread"] = (pd.to_numeric(frame["ask"], errors="coerce") - pd.to_numeric(frame["bid"], errors="coerce")).abs()
    else:
        frame["spread"] = pd.to_numeric(frame.get("spread", 0), errors="coerce").fillna(0)
    frame["volume"] = pd.to_numeric(frame.get("volume", frame.get("real_volume", 0)), errors="coerce").fillna(0)
    return frame


def _resample_ticks(frame: pd.DataFrame, timeframe: str, start_date: str, end_date: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    rule = TIMEFRAME_TO_PANDAS.get(timeframe.upper())
    if not rule:
        raise ValueError(f"Unsupported timeframe for tick resampling: {timeframe}")
    frame = frame.dropna(subset=["timestamp", "price"]).sort_values("timestamp").set_index("timestamp")
    ohlc = frame["price"].resample(rule).ohlc()
    ohlc["tick_volume"] = frame["price"].resample(rule).count()
    ohlc["spread"] = frame["spread"].resample(rule).mean() if "spread" in frame else 0
    ohlc["real_volume"] = frame["volume"].resample(rule).sum() if "volume" in frame else 0
    ohlc = ohlc.dropna(subset=["open", "high", "low", "close"]).reset_index()
    return _range_mask(ohlc, start_date, end_date)


def _read_csv_source(controls: dict[str, Any], env_prefixes: list[str]) -> pd.DataFrame:
    url = str(controls.get("url") or controls.get("csv_url") or "").strip()
    path = str(controls.get("path") or controls.get("csv_path") or "").strip()
    for prefix in env_prefixes:
        url = url or os.getenv(f"{prefix}_CSV_URL", "")
        path = path or os.getenv(f"{prefix}_CSV_PATH", "")
    url = url or os.getenv("DATA_PROVIDER_CSV_URL", "")
    path = path or os.getenv("DATA_PROVIDER_CSV_PATH", "")
    if url:
        return pd.read_csv(url)
    if path:
        return pd.read_csv(Path(path).expanduser())
    raise ValueError("No CSV URL/path provided. Add it in the UI or set the matching *_CSV_URL or *_CSV_PATH variable in .env.")


def _fetch_csv_like(symbol: str, timeframe: str, start_date: str, end_date: str, controls: dict[str, Any], prefixes: list[str]) -> list[dict[str, Any]]:
    frame = _read_csv_source(controls, prefixes)
    frame = _normalize_ohlc_frame(frame, symbol, start_date, end_date)
    if "price" in frame.columns:
        frame = _resample_ticks(frame, timeframe, start_date, end_date)
    return _records(frame)


def _fetch_alpha_vantage(symbol: str, timeframe: str, start_date: str, end_date: str, controls: dict[str, Any]) -> list[dict[str, Any]]:
    interval = ALPHA_INTERVALS.get(timeframe.upper())
    if not interval:
        raise ValueError("Alpha Vantage free FX intraday supports M1/M5/M15/M30/H1 in this app.")
    key = _api_key(controls, "ALPHA_VANTAGE_API_KEY")
    if not key:
        raise ValueError("Alpha Vantage key missing. Add it in the UI or set ALPHA_VANTAGE_API_KEY in .env.")
    base, quote = symbol[:3].upper(), symbol[3:].upper()
    with httpx.Client(timeout=30) as client:
        data = client.get(
            "https://www.alphavantage.co/query",
            params={"function": "FX_INTRADAY", "from_symbol": base, "to_symbol": quote, "interval": interval, "outputsize": "full", "apikey": key},
        ).json()
    series_key = next((key for key in data if key.startswith("Time Series")), "")
    if not series_key:
        raise ValueError(str(data.get("Note") or data.get("Error Message") or "Alpha Vantage returned no time series."))
    rows = [
        {"timestamp": ts, "open": row["1. open"], "high": row["2. high"], "low": row["3. low"], "close": row["4. close"], "tick_volume": 0, "spread": 0, "real_volume": 0}
        for ts, row in data[series_key].items()
    ]
    return _records(_range_mask(pd.DataFrame(rows), start_date, end_date))


def _fetch_twelve_data(symbol: str, timeframe: str, start_date: str, end_date: str, controls: dict[str, Any]) -> list[dict[str, Any]]:
    interval = TWELVE_INTERVALS.get(timeframe.upper())
    if not interval:
        raise ValueError(f"Unsupported Twelve Data timeframe: {timeframe}")
    key = _api_key(controls, "TWELVE_DATA_API_KEY")
    if not key:
        raise ValueError("Twelve Data key missing. Add it in the UI or set TWELVE_DATA_API_KEY in .env.")
    pair = f"{symbol[:3].upper()}/{symbol[3:].upper()}"
    with httpx.Client(timeout=30) as client:
        data = client.get(
            "https://api.twelvedata.com/time_series",
            params={"symbol": pair, "interval": interval, "start_date": start_date, "end_date": end_date, "apikey": key, "outputsize": 5000},
        ).json()
    if data.get("status") == "error" or "values" not in data:
        raise ValueError(str(data.get("message") or "Twelve Data returned no values."))
    rows = [
        {"timestamp": row["datetime"], "open": row["open"], "high": row["high"], "low": row["low"], "close": row["close"], "tick_volume": 0, "spread": 0, "real_volume": row.get("volume", 0)}
        for row in data["values"]
    ]
    return _records(_range_mask(pd.DataFrame(rows), start_date, end_date))


def _fetch_polygon(symbol: str, timeframe: str, start_date: str, end_date: str, controls: dict[str, Any]) -> list[dict[str, Any]]:
    interval = POLYGON_INTERVALS.get(timeframe.upper())
    if not interval:
        raise ValueError(f"Unsupported Polygon timeframe: {timeframe}")
    key = _api_key(controls, "POLYGON_API_KEY")
    if not key:
        raise ValueError("Polygon key missing. Add it in the UI or set POLYGON_API_KEY in .env.")
    multiplier, span = interval
    ticker = f"C:{symbol.upper()}"
    with httpx.Client(timeout=30) as client:
        data = client.get(
            f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/{multiplier}/{span}/{start_date}/{end_date}",
            params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": key},
        ).json()
    if data.get("status") not in {"OK", "DELAYED"} or "results" not in data:
        raise ValueError(str(data.get("error") or data.get("message") or "Polygon returned no aggregate results."))
    rows = [
        {
            "timestamp": datetime.fromtimestamp(row["t"] / 1000, tz=timezone.utc).isoformat(),
            "open": row["o"],
            "high": row["h"],
            "low": row["l"],
            "close": row["c"],
            "tick_volume": row.get("n", 0),
            "spread": 0,
            "real_volume": row.get("v", 0),
        }
        for row in data["results"]
    ]
    return _records(pd.DataFrame(rows))


def _dukascopy_price_scale(symbol: str) -> float:
    return 1000.0 if "JPY" in symbol.upper() else 100000.0


def _fetch_dukascopy(symbol: str, timeframe: str, start_date: str, end_date: str, controls: dict[str, Any]) -> list[dict[str, Any]]:
    start = _date(start_date).replace(minute=0, second=0, microsecond=0)
    end = _date(end_date).replace(minute=0, second=0, microsecond=0)
    max_days = int(controls.get("dukascopy_max_days") or 31)
    if (end - start).days > max_days and not controls.get("allow_large_download"):
        raise ValueError(f"Dukascopy direct tick download is capped at {max_days} days per request in this app. Narrow the range or enable allow_large_download.")
    rows: list[dict[str, Any]] = []
    scale = _dukascopy_price_scale(symbol)
    base_url = str(controls.get("base_url") or "https://datafeed.dukascopy.com/datafeed").rstrip("/")
    current = start
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        while current <= end:
            month = current.month - 1
            path = f"{base_url}/{symbol.upper()}/{current.year}/{month:02d}/{current.day:02d}/{current.hour:02d}h_ticks.bi5"
            response = client.get(path)
            if response.status_code == 200 and response.content:
                try:
                    data = lzma.decompress(response.content)
                    for offset in range(0, len(data) - 19, 20):
                        ms, ask_raw, bid_raw, ask_vol, bid_vol = struct.unpack(">IIIff", data[offset : offset + 20])
                        ts = current + timedelta(milliseconds=ms)
                        bid = bid_raw / scale
                        ask = ask_raw / scale
                        rows.append({"timestamp": ts, "price": (bid + ask) / 2, "spread": abs(ask - bid), "volume": float(ask_vol or 0) + float(bid_vol or 0)})
                except Exception:
                    pass
            current += timedelta(hours=1)
    if not rows:
        raise ValueError("Dukascopy returned no ticks for this symbol/date range.")
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return _records(_resample_ticks(frame, timeframe, start_date, end_date))


def fetch_candles_from_selected_source(symbol: str, timeframe: str, start_date: str, end_date: str, data_source_controls: dict[str, Any] | None = None) -> dict[str, Any]:
    controls = _controls(data_source_controls)
    source = controls["data_source"]
    provider = str(controls.get("provider") or provider_name(source))

    if source in {"mt5_retail_candles", "mt5_every_tick", "mt5_real_ticks"}:
        result = fetch_mt5_candles(symbol, timeframe, start_date, end_date, data_source=source, provider=provider)
        result.update({"data_source": source, "provider": provider, "selected_source_only": True})
        return result

    try:
        if source == "dukascopy_ticks":
            candles = _fetch_dukascopy(symbol, timeframe, start_date, end_date, controls)
        elif source == "alpha_vantage_fx":
            candles = _fetch_alpha_vantage(symbol, timeframe, start_date, end_date, controls)
        elif source == "twelve_data_fx":
            candles = _fetch_twelve_data(symbol, timeframe, start_date, end_date, controls)
        elif source == "polygon_fx":
            candles = _fetch_polygon(symbol, timeframe, start_date, end_date, controls)
        elif source == "csv_import":
            candles = _fetch_csv_like(symbol, timeframe, start_date, end_date, controls, ["DATA_PROVIDER"])
        elif source == "cme_fx_futures_proxy":
            candles = _fetch_csv_like(symbol, timeframe, start_date, end_date, controls, ["CME_FX"])
        elif source in {"prime_broker_ticks", "ecn_l2_order_book", "reuters_ebs_tick", "bloomberg_bpipe_tick", "institutional_order_flow"}:
            prefix = {
                "prime_broker_ticks": "PRIME_BROKER",
                "ecn_l2_order_book": "ECN_L2",
                "reuters_ebs_tick": "REUTERS_EBS",
                "bloomberg_bpipe_tick": "BLOOMBERG_BPIPE",
                "institutional_order_flow": "INSTITUTIONAL_FLOW",
            }[source]
            candles = _fetch_csv_like(symbol, timeframe, start_date, end_date, controls, [prefix])
        else:
            raise ValueError(f"Unsupported data source: {source}")
    except ValueError as exc:
        return {"saved": 0, "symbol": symbol, "timeframe": timeframe, "data_source": source, "provider": provider, "error": str(exc)}

    saved = save_candles(symbol, timeframe, candles, data_source=source, provider=provider)
    return {
        "saved": saved,
        "symbol": symbol,
        "timeframe": timeframe,
        "data_source": source,
        "provider": provider,
        "selected_source_only": True,
        "message": f"Saved {saved} candles from {provider}.",
    }
