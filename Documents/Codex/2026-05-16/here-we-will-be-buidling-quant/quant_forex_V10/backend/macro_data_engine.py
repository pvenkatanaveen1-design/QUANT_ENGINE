from __future__ import annotations

import json
from datetime import datetime, timezone
from io import StringIO
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

import pandas as pd

from backend.database import load_candles, load_latest_macro_row, load_macro_rows, save_macro_rows


EVIDENCE_CONFIDENCE_MIN = 0.50
CSV_COLUMNS = [
    "timestamp",
    "symbol",
    "scope",
    "source",
    "dxy_change_percent",
    "usd_basket_change_percent",
    "us_yield_change_bp",
    "fed_rate_expectation_change_bp",
    "spx_change_percent",
    "vix_change_percent",
    "gold_change_percent",
    "jpy_strength_score",
    "chf_strength_score",
    "base_rate_expectation_change_bp",
    "quote_rate_expectation_change_bp",
    "cb_divergence_bp",
    "high_impact_news",
    "minutes_to_news",
    "minutes_since_news",
    "event_currency",
    "event_name",
    "event_impact",
    "notes",
]

JSON_LIST_KEYS = ["data", "events", "calendar", "rows", "results", "values"]
HIGH_IMPACT_VALUES = {"high", "high impact", "3", "red", "important"}
MAJOR_FX_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD", "EURJPY", "GBPJPY"]
MACRO_INPUT_GROUPS = {
    "usd": ["dxy_change_percent", "usd_basket_change_percent", "us_yield_change_bp", "fed_rate_expectation_change_bp"],
    "risk": ["spx_change_percent", "vix_change_percent", "gold_change_percent", "jpy_strength_score", "chf_strength_score"],
    "central_bank": ["base_rate_expectation_change_bp", "quote_rate_expectation_change_bp", "cb_divergence_bp"],
    "positioning": ["cot_base_score", "cot_quote_score", "cot_pair_score", "cot_usd_score"],
    "news": ["high_impact_news", "minutes_to_news", "minutes_since_news", "event_currency", "event_name", "event_impact"],
}
MACRO_REGIME_NAMES = {
    "R25": "Broad USD Bullish Regime",
    "R26": "Broad USD Bearish Regime",
    "R27": "Risk-On Carry Regime",
    "R28": "Risk-Off Carry Unwind",
    "R29": "Central-Bank Divergence Trend",
}

CFTC_TFF_URL = "https://publicreporting.cftc.gov/resource/udgc-27he.json"
COT_MARKETS = {
    "EUR": "EURO FX",
    "GBP": "BRITISH POUND",
    "JPY": "JAPANESE YEN",
    "CHF": "SWISS FRANC",
    "AUD": "AUSTRALIAN DOLLAR",
    "CAD": "CANADIAN DOLLAR",
    "MXN": "MEXICAN PESO",
}
COT_DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "EURJPY", "GBPJPY", "AUDJPY"]


def _num(data: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = data.get(key, default)
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def _score_label(score: int, positive: str, negative: str, neutral: str) -> tuple[str, float]:
    if score >= 2:
        return positive, min(1.0, score / 4)
    if score <= -2:
        return negative, min(1.0, abs(score) / 4)
    return neutral, max(0.0, 1 - abs(score) / 2)


def _text(data: dict[str, Any], key: str, default: str = "") -> str:
    value = data.get(key, default)
    if value is None:
        return default
    return str(value)


def _normalize_timestamp(value: Any) -> str:
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        raise ValueError(f"Invalid macro timestamp: {value!r}")
    return ts.isoformat()


def _symbol_currencies(symbol: str) -> tuple[str, str]:
    clean = str(symbol or "").upper().replace("/", "").replace("-", "").strip()
    if len(clean) < 6:
        return clean[:3], clean[3:6]
    return clean[:3], clean[3:6]


def _cot_float(record: dict[str, Any], key: str) -> float:
    try:
        value = record.get(key)
        if value is None or str(value).strip() == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _cot_currency_score(record: dict[str, Any]) -> dict[str, Any]:
    open_interest = max(_cot_float(record, "open_interest_all"), 1.0)
    asset_net = _cot_float(record, "asset_mgr_positions_long") - _cot_float(record, "asset_mgr_positions_short")
    lev_net = _cot_float(record, "lev_money_positions_long") - _cot_float(record, "lev_money_positions_short")
    combined_net = asset_net + lev_net
    net_oi = combined_net / open_interest
    return {
        "contract_market_name": record.get("contract_market_name"),
        "market_and_exchange_names": record.get("market_and_exchange_names"),
        "report_date": _normalize_timestamp(record.get("report_date_as_yyyy_mm_dd")),
        "open_interest": open_interest,
        "asset_manager_net": asset_net,
        "leveraged_money_net": lev_net,
        "combined_net": combined_net,
        "asset_manager_net_oi": asset_net / open_interest,
        "leveraged_money_net_oi": lev_net / open_interest,
        "combined_net_oi": net_oi,
        "score": float(max(-1.0, min(1.0, net_oi * 2.0))),
    }


def _fetch_cftc_tff_records(markets: list[str], as_of: str | None = None, report_type: str = "Combined", timeout_seconds: int = 20) -> list[dict[str, Any]]:
    if not markets:
        return []
    clean_markets = sorted({str(m).replace("'", "''") for m in markets if str(m).strip()})
    where_parts = [
        "contract_market_name in(" + ",".join([f"'{m}'" for m in clean_markets]) + ")",
        f"futonly_or_combined='{str(report_type or 'Combined').replace(chr(39), chr(39) + chr(39))}'",
    ]
    if as_of:
        as_of_ts = pd.to_datetime(as_of, utc=True, errors="coerce")
        if pd.notna(as_of_ts):
            where_parts.append(f"report_date_as_yyyy_mm_dd <= '{as_of_ts.date().isoformat()}T00:00:00'")
    params = {
        "$select": "contract_market_name,market_and_exchange_names,report_date_as_yyyy_mm_dd,asset_mgr_positions_long,asset_mgr_positions_short,lev_money_positions_long,lev_money_positions_short,open_interest_all,futonly_or_combined",
        "$where": " AND ".join(where_parts),
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": "500",
    }
    request = UrlRequest(f"{CFTC_TFF_URL}?{urlencode(params)}", headers={"User-Agent": "quant_forex_V10/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(2_000_000)
    except (OSError, URLError) as exc:
        raise ValueError(f"Could not download CFTC COT feed: {exc}") from exc
    try:
        records = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"CFTC COT feed response was not valid JSON: {exc}") from exc
    return [item for item in records if isinstance(item, dict)]


def _row_to_evidence(row: dict[str, Any]) -> dict[str, Any]:
    evidence = {"mode": "evidence"}
    for key in CSV_COLUMNS:
        if key in {"timestamp", "symbol", "scope", "source", "event_currency", "event_name", "event_impact", "notes"}:
            continue
        if key == "high_impact_news":
            evidence[key] = _bool(row, key)
        else:
            evidence[key] = _num(row, key, 0.0)
    evidence["event_currency"] = _text(row, "event_currency")
    evidence["event_name"] = _text(row, "event_name")
    evidence["event_impact"] = _text(row, "event_impact")
    evidence["notes"] = _text(row, "notes")
    return evidence


def _first_present(data: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return default


def _normalize_feed_record(record: dict[str, Any], feed_type: str, source: str) -> dict[str, Any]:
    normalized = {str(k).strip().lower().replace(" ", "_"): v for k, v in record.items()}
    timestamp = _first_present(normalized, ["timestamp", "time", "datetime", "date", "event_time", "published_at"])
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    row: dict[str, Any] = {
        "timestamp": timestamp,
        "symbol": str(_first_present(normalized, ["symbol", "pair"], "GLOBAL") or "GLOBAL").upper(),
        "scope": str(_first_present(normalized, ["scope"], feed_type.upper()) or feed_type.upper()).upper(),
        "source": _text({"source": source}, "source", source),
        "notes": _text(normalized, "notes", ""),
    }
    aliases = {
        "dxy_change_percent": ["dxy_change_percent", "dxy_pct", "dxy_change", "dxy"],
        "usd_basket_change_percent": ["usd_basket_change_percent", "usd_index_change_percent", "usd_change_percent", "usd_strength_percent"],
        "us_yield_change_bp": ["us_yield_change_bp", "yield_change_bp", "us10y_change_bp", "us_10y_change_bp"],
        "fed_rate_expectation_change_bp": ["fed_rate_expectation_change_bp", "fed_exp_bp", "fed_change_bp", "usd_rate_expectation_change_bp"],
        "spx_change_percent": ["spx_change_percent", "sp500_change_percent", "equity_change_percent", "risk_asset_change_percent"],
        "vix_change_percent": ["vix_change_percent", "vix_pct", "volatility_change_percent"],
        "gold_change_percent": ["gold_change_percent", "xau_change_percent", "xauusd_change_percent"],
        "jpy_strength_score": ["jpy_strength_score", "jpy_score", "jpy_strength"],
        "chf_strength_score": ["chf_strength_score", "chf_score", "chf_strength"],
        "base_rate_expectation_change_bp": ["base_rate_expectation_change_bp", "base_rate_bp", "base_cb_bp"],
        "quote_rate_expectation_change_bp": ["quote_rate_expectation_change_bp", "quote_rate_bp", "quote_cb_bp"],
        "cb_divergence_bp": ["cb_divergence_bp", "rate_differential_change_bp", "relative_rate_change_bp"],
        "minutes_to_news": ["minutes_to_news", "mins_to_news", "minutes_until_event"],
        "minutes_since_news": ["minutes_since_news", "mins_since_news", "minutes_after_event"],
    }
    for target, names in aliases.items():
        row[target] = _num(normalized, names[0], 0.0) if names[0] in normalized else _num({target: _first_present(normalized, names, 0)}, target, 0.0)
    event_impact = str(_first_present(normalized, ["event_impact", "impact", "importance"], "") or "")
    row["event_currency"] = str(_first_present(normalized, ["event_currency", "currency", "ccy"], "") or "").upper()
    row["event_name"] = str(_first_present(normalized, ["event_name", "name", "title", "event"], "") or "")
    row["event_impact"] = event_impact
    row["high_impact_news"] = _bool(normalized, "high_impact_news") or event_impact.strip().lower() in HIGH_IMPACT_VALUES
    if feed_type == "news":
        row["scope"] = "NEWS"
        row["symbol"] = row["symbol"] if row["symbol"] != "GLOBAL" else (row["event_currency"] or "GLOBAL")
        row["high_impact_news"] = row["high_impact_news"] or event_impact.strip().lower() in HIGH_IMPACT_VALUES
        row["minutes_to_news"] = row.get("minutes_to_news", 0) or 0
        row["minutes_since_news"] = row.get("minutes_since_news", 0) or 0
        if not row["event_name"]:
            row["event_name"] = "Imported macro news event"
    return row


def _records_from_json(json_text: str) -> list[dict[str, Any]]:
    try:
        loaded = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Feed JSON is invalid: {exc}") from exc
    if isinstance(loaded, list):
        return [item for item in loaded if isinstance(item, dict)]
    if isinstance(loaded, dict):
        for key in JSON_LIST_KEYS:
            value = loaded.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [loaded]
    raise ValueError("Feed JSON must be an object, a list, or contain a data/events/calendar list.")


def _csv_from_records(records: list[dict[str, Any]]) -> str:
    if not records:
        raise ValueError("Feed did not contain any importable records.")
    frame = pd.DataFrame(records)
    return frame.to_csv(index=False)


def import_macro_feed_text(
    feed_text: str,
    source: str = "macro_feed",
    feed_type: str = "macro",
    feed_format: str = "csv",
) -> dict[str, Any]:
    if not feed_text.strip():
        raise ValueError("Macro feed text is empty.")
    normalized_feed_type = str(feed_type or "macro").strip().lower()
    if normalized_feed_type not in {"macro", "news", "cross_pair"}:
        raise ValueError("feed_type must be one of: macro, news, cross_pair.")
    normalized_format = str(feed_format or "csv").strip().lower()
    if normalized_format not in {"csv", "json"}:
        raise ValueError("feed_format must be csv or json.")

    if normalized_format == "json":
        raw_records = _records_from_json(feed_text)
    else:
        frame = pd.read_csv(StringIO(feed_text))
        if frame.empty:
            raise ValueError("Macro feed CSV did not contain any rows.")
        raw_records = [{str(k): (None if pd.isna(v) else v) for k, v in row.items()} for row in frame.to_dict(orient="records")]

    rows = [_normalize_feed_record(record, normalized_feed_type, source) for record in raw_records]
    result = import_macro_csv(_csv_from_records(rows), source)
    result["feed_type"] = normalized_feed_type
    result["feed_format"] = normalized_format
    return result


def _pair_change_percent(df: pd.DataFrame) -> float | None:
    if df.empty or "close" not in df.columns:
        return None
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) < 2:
        return None
    first = float(close.iloc[0])
    last = float(close.iloc[-1])
    if first == 0:
        return None
    return ((last - first) / first) * 100


def _avg(values: list[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def import_cross_pair_evidence(
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    symbols: list[str] | None = None,
    source: str = "cross_pair_candles",
) -> dict[str, Any]:
    selected_symbols = [str(item).upper().strip() for item in (symbols or MAJOR_FX_SYMBOLS) if str(item).strip()]
    if not selected_symbols:
        raise ValueError("At least one cross-pair symbol is required.")

    components: list[dict[str, Any]] = []
    usd_scores: list[float] = []
    jpy_scores: list[float] = []
    chf_scores: list[float] = []
    risk_scores: list[float] = []
    latest_timestamp: pd.Timestamp | None = None

    for pair in selected_symbols:
        df = load_candles(pair, timeframe, start_date, end_date)
        change = _pair_change_percent(df)
        if change is None:
            components.append({"symbol": pair, "status": "missing_or_insufficient_candles"})
            continue
        if not df.empty:
            pair_latest = pd.to_datetime(df["timestamp"].iloc[-1], utc=True)
            latest_timestamp = pair_latest if latest_timestamp is None or pair_latest > latest_timestamp else latest_timestamp
        component = {"symbol": pair, "status": "ok", "change_percent": round(change, 4)}
        if pair.startswith("USD"):
            usd_scores.append(change)
            component["usd_contribution"] = round(change, 4)
        elif pair.endswith("USD"):
            usd_scores.append(-change)
            component["usd_contribution"] = round(-change, 4)
        if "JPY" in pair:
            jpy_strength = -change if pair.endswith("JPY") else change
            jpy_scores.append(jpy_strength)
            component["jpy_strength_contribution"] = round(jpy_strength, 4)
        if "CHF" in pair:
            chf_strength = -change if pair.endswith("CHF") else change
            chf_scores.append(chf_strength)
            component["chf_strength_contribution"] = round(chf_strength, 4)
        if pair in {"AUDJPY", "NZDJPY", "EURJPY", "GBPJPY", "CADJPY"}:
            risk_scores.append(change)
            component["risk_proxy_contribution"] = round(change, 4)
        components.append(component)

    if latest_timestamp is None:
        raise ValueError("No cross-pair candles found for the selected symbols/date range.")

    usd_basket_change = _avg(usd_scores)
    jpy_strength = _avg(jpy_scores)
    chf_strength = _avg(chf_scores)
    risk_proxy = _avg(risk_scores)
    row = {
        "timestamp": latest_timestamp.isoformat(),
        "symbol": symbol.upper(),
        "scope": "CROSS_PAIR",
        "source": source,
        "usd_basket_change_percent": round(usd_basket_change, 4),
        "jpy_strength_score": round(jpy_strength, 4),
        "chf_strength_score": round(chf_strength, 4),
        "spx_change_percent": round(risk_proxy, 4),
        "notes": (
            "Cross-pair evidence from saved candle returns. "
            f"USD basket={usd_basket_change:.4f}, JPY strength={jpy_strength:.4f}, "
            f"CHF strength={chf_strength:.4f}, risk proxy={risk_proxy:.4f}."
        ),
    }
    result = import_macro_csv(_csv_from_records([row]), source)
    result["cross_pair_components"] = components
    result["cross_pair_summary"] = {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "start_date": start_date,
        "end_date": end_date,
        "symbols_requested": selected_symbols,
        "symbols_used": sum(1 for item in components if item.get("status") == "ok"),
        "usd_basket_change_percent": round(usd_basket_change, 4),
        "jpy_strength_score": round(jpy_strength, 4),
        "chf_strength_score": round(chf_strength, 4),
        "risk_proxy_change_percent": round(risk_proxy, 4),
    }
    return result


def import_cot_evidence(
    symbols: list[str] | None = None,
    as_of: str | None = None,
    source: str = "cftc_tff_cot",
    report_type: str = "Combined",
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    selected_symbols = [str(item).upper().replace("/", "").replace("-", "").strip() for item in (symbols or COT_DEFAULT_SYMBOLS) if str(item).strip()]
    if not selected_symbols:
        raise ValueError("At least one symbol is required for COT import.")

    currencies = sorted({ccy for symbol in selected_symbols for ccy in _symbol_currencies(symbol) if ccy in COT_MARKETS})
    markets = [COT_MARKETS[ccy] for ccy in currencies]
    if not markets:
        raise ValueError("No supported COT futures markets found for the selected symbols.")

    records = _fetch_cftc_tff_records(markets, as_of=as_of, report_type=report_type, timeout_seconds=timeout_seconds)
    latest_by_market: dict[str, dict[str, Any]] = {}
    for record in records:
        market = str(record.get("contract_market_name") or "")
        if market and market not in latest_by_market:
            latest_by_market[market] = record

    currency_scores: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for ccy in currencies:
        market = COT_MARKETS[ccy]
        record = latest_by_market.get(market)
        if not record:
            warnings.append(f"No COT record found for {ccy} / {market}.")
            continue
        currency_scores[ccy] = _cot_currency_score(record)

    rows: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    for symbol in selected_symbols:
        base, quote = _symbol_currencies(symbol)
        base_score = float(currency_scores.get(base, {}).get("score", 0.0)) if base != "USD" else 0.0
        quote_score = float(currency_scores.get(quote, {}).get("score", 0.0)) if quote != "USD" else 0.0
        pair_score = base_score - quote_score
        if base == "USD":
            usd_score = pair_score
        elif quote == "USD":
            usd_score = -pair_score
        else:
            usd_score = 0.0

        report_dates = [currency_scores.get(ccy, {}).get("report_date") for ccy in {base, quote} if ccy in currency_scores]
        timestamp = sorted([str(item) for item in report_dates if item])[-1] if report_dates else datetime.now(timezone.utc).isoformat()
        jpy_strength = quote_score if quote == "JPY" else (base_score if base == "JPY" else 0.0)
        chf_strength = quote_score if quote == "CHF" else (base_score if base == "CHF" else 0.0)
        evidence = {
            "mode": "evidence",
            "cot_source": "CFTC Traders in Financial Futures",
            "cot_report_type": report_type,
            "cot_base_currency": base,
            "cot_quote_currency": quote,
            "cot_base_score": round(base_score, 4),
            "cot_quote_score": round(quote_score, 4),
            "cot_pair_score": round(pair_score, 4),
            "cot_usd_score": round(usd_score, 4),
            "cot_base_details": currency_scores.get(base, {}),
            "cot_quote_details": currency_scores.get(quote, {}),
            "usd_basket_change_percent": round(usd_score, 4),
            "jpy_strength_score": round(jpy_strength * 2.0, 4),
            "chf_strength_score": round(chf_strength * 2.0, 4),
            "cb_divergence_bp": round(pair_score * 50.0, 4),
            "notes": f"CFTC COT positioning imported for {symbol}: pair_score={pair_score:.4f}, usd_score={usd_score:.4f}.",
        }
        resolved = resolve_macro_context("NEUTRAL", "NEUTRAL", "NEUTRAL", evidence)
        rows.append(
            {
                "timestamp": timestamp,
                "symbol": symbol,
                "scope": "COT",
                "source": source,
                "dxy_change_percent": 0,
                "usd_basket_change_percent": evidence["usd_basket_change_percent"],
                "us_yield_change_bp": 0,
                "fed_rate_expectation_change_bp": 0,
                "spx_change_percent": 0,
                "vix_change_percent": 0,
                "gold_change_percent": 0,
                "jpy_strength_score": evidence["jpy_strength_score"],
                "chf_strength_score": evidence["chf_strength_score"],
                "base_rate_expectation_change_bp": 0,
                "quote_rate_expectation_change_bp": 0,
                "cb_divergence_bp": evidence["cb_divergence_bp"],
                "high_impact_news": 0,
                "minutes_to_news": 9999,
                "minutes_since_news": 9999,
                "event_currency": "",
                "event_name": "CFTC COT positioning",
                "event_impact": "Weekly",
                "notes": evidence["notes"],
                "evidence_json": json.dumps(evidence),
                "resolved_json": json.dumps(resolved),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        components.append(
            {
                "symbol": symbol,
                "base": base,
                "quote": quote,
                "base_score": round(base_score, 4),
                "quote_score": round(quote_score, 4),
                "pair_score": round(pair_score, 4),
                "usd_score": round(usd_score, 4),
                "timestamp": timestamp,
                "activation_allowed": resolved.get("activation_allowed", {}),
            }
        )

    if not rows:
        raise ValueError("COT feed returned no usable rows for selected symbols.")
    saved = save_macro_rows(rows)
    latest = rows[-1]
    return {
        "saved": saved,
        "rows_received": len(rows),
        "source": source,
        "columns_expected": CSV_COLUMNS,
        "latest": {
            "timestamp": latest["timestamp"],
            "symbol": latest["symbol"],
            "scope": latest["scope"],
            "resolved": json.loads(latest["resolved_json"]),
        },
        "cot_summary": {
            "dataset": "CFTC Traders in Financial Futures",
            "dataset_url": CFTC_TFF_URL,
            "report_type": report_type,
            "as_of": as_of,
            "symbols_requested": selected_symbols,
            "currencies_requested": currencies,
            "symbols_imported": len(rows),
        },
        "cot_components": components,
        "warnings": warnings,
    }


def _confidence_passes(result: dict[str, Any], key: str, minimum: float) -> bool:
    label = result.get(key)
    confidence = float(result.get("confidence", {}).get(key, 0) or 0)
    return label != "NEUTRAL" and confidence >= minimum


def _evidence_field_present(evidence: dict[str, Any], key: str) -> bool:
    if key not in evidence:
        return False
    value = evidence.get(key)
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    return True


def _input_coverage(evidence: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, Any] = {}
    available_total = 0
    required_total = 0
    missing_all: list[str] = []
    for group, fields in MACRO_INPUT_GROUPS.items():
        available = [field for field in fields if _evidence_field_present(evidence, field)]
        missing = [field for field in fields if field not in available]
        required_total += len(fields)
        available_total += len(available)
        missing_all.extend(missing)
        groups[group] = {
            "available": available,
            "missing": missing,
            "available_count": len(available),
            "required_count": len(fields),
            "coverage_percent": round((len(available) / len(fields)) * 100, 2) if fields else 0,
        }
    coverage_percent = round((available_total / required_total) * 100, 2) if required_total else 0
    return {
        "groups": groups,
        "available_count": available_total,
        "required_count": required_total,
        "coverage_percent": coverage_percent,
        "missing_inputs": missing_all,
    }


def _activation_table(result: dict[str, Any]) -> list[dict[str, Any]]:
    confidence = result.get("confidence", {})
    activation = result.get("activation_allowed", {})
    rows = [
        ("R25", "USD_BULLISH", result.get("usd_bias"), confidence.get("usd_bias", 0)),
        ("R26", "USD_BEARISH", result.get("usd_bias"), confidence.get("usd_bias", 0)),
        ("R27", "RISK_ON", result.get("risk_sentiment"), confidence.get("risk_sentiment", 0)),
        ("R28", "RISK_OFF", result.get("risk_sentiment"), confidence.get("risk_sentiment", 0)),
        ("R29", "BULLISH_BASE/BEARISH_BASE", result.get("cb_divergence"), confidence.get("cb_divergence", 0)),
    ]
    table = []
    threshold = float(result.get("activation_threshold", EVIDENCE_CONFIDENCE_MIN) or EVIDENCE_CONFIDENCE_MIN)
    for regime_id, required, observed, conf in rows:
        allowed = bool(activation.get(regime_id))
        conf_value = float(conf or 0)
        if allowed:
            reason = f"{observed} evidence confidence {conf_value:.2f} passed the {threshold:.2f} gate."
        elif observed in {None, "", "NEUTRAL"}:
            reason = f"Blocked because evidence is neutral; required {required}."
        elif conf_value < threshold:
            reason = f"Blocked because confidence {conf_value:.2f} is below required {threshold:.2f}."
        else:
            reason = f"Blocked because observed evidence {observed} does not match required {required}."
        table.append(
            {
                "regime_id": regime_id,
                "regime_name": MACRO_REGIME_NAMES[regime_id],
                "required_evidence": required,
                "observed_evidence": observed or "NEUTRAL",
                "confidence": round(conf_value, 4),
                "required_confidence": threshold,
                "allowed": allowed,
                "status": "ALLOWED" if allowed else "BLOCKED",
                "reason": reason,
            }
        )
    return table


def _macro_recommendations(result: dict[str, Any], coverage: dict[str, Any]) -> list[str]:
    recommendations: list[str] = []
    groups = coverage.get("groups", {})
    if groups.get("usd", {}).get("available_count", 0) < 2:
        recommendations.append("Import at least two USD evidence inputs: DXY, USD basket, US yields, or Fed rate expectations.")
    if groups.get("risk", {}).get("available_count", 0) < 2:
        recommendations.append("Import at least two risk inputs: SPX, VIX, gold, JPY strength, or CHF strength.")
    if groups.get("central_bank", {}).get("available_count", 0) < 1:
        recommendations.append("Import central-bank divergence evidence: cb_divergence_bp or base/quote rate expectation changes.")
    if result.get("mode") == "manual":
        recommendations.append("Manual macro mode is useful for notes, but R25-R29 need evidence/database mode for institutional validation.")
    if not any(result.get("activation_allowed", {}).values()):
        recommendations.append("No macro regime passed the evidence gate; keep R25-R29 inactive until confidence improves.")
    if result.get("news_flag"):
        recommendations.append("News risk is active; prefer R09/R10 handling instead of normal macro continuation until spread normalizes.")
    return recommendations


def _augment_macro_result(result: dict[str, Any]) -> dict[str, Any]:
    coverage = _input_coverage(result.get("evidence", {}) or {})
    activation_rows = _activation_table(result)
    if result.get("mode") in {"manual", "off"}:
        quality_status = "MANUAL_FALLBACK"
    elif coverage["available_count"] == 0:
        quality_status = "NO_EVIDENCE"
    elif any(row["allowed"] for row in activation_rows):
        quality_status = "EVIDENCE_READY"
    else:
        quality_status = "PARTIAL_EVIDENCE"
    result["input_coverage"] = coverage
    result["activation_table"] = activation_rows
    result["missing_inputs"] = coverage["missing_inputs"]
    result["quality_status"] = quality_status
    result["recommendations"] = _macro_recommendations(result, coverage)
    return result


def resolve_macro_context(
    manual_usd_bias: str = "NEUTRAL",
    manual_risk_sentiment: str = "NEUTRAL",
    manual_cb_divergence: str = "NEUTRAL",
    macro_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = macro_evidence or {}
    mode = str(evidence.get("mode") or "manual").lower()
    reasons: list[str] = []
    warnings: list[str] = []

    result = {
        "mode": mode,
        "source": "manual",
        "usd_bias": manual_usd_bias or "NEUTRAL",
        "risk_sentiment": manual_risk_sentiment or "NEUTRAL",
        "cb_divergence": manual_cb_divergence or "NEUTRAL",
        "news_flag": bool(evidence.get("news_flag", False)),
        "confidence": {"usd_bias": 0.0, "risk_sentiment": 0.0, "cb_divergence": 0.0},
        "scores": {"usd_score": 0, "risk_score": 0, "cb_score": 0.0},
        "reasons": reasons,
        "warnings": warnings,
        "evidence": evidence,
        "activation_allowed": {
            "R25": False,
            "R26": False,
            "R27": False,
            "R28": False,
            "R29": False,
        },
        "activation_threshold": EVIDENCE_CONFIDENCE_MIN,
    }

    if mode == "database":
        latest = load_latest_macro_row(evidence.get("symbol"), evidence.get("as_of") or evidence.get("end_date"))
        if latest is None:
            result["source"] = "database"
            result["usd_bias"] = "NEUTRAL"
            result["risk_sentiment"] = "NEUTRAL"
            result["cb_divergence"] = "NEUTRAL"
            warnings.append("No macro_data row found for selected symbol/date; R25-R29 will not activate.")
            reasons.append("Database macro mode selected but no imported evidence was available.")
            return _augment_macro_result(result)
        db_evidence = dict(latest.get("evidence") or {})
        db_evidence["mode"] = "evidence"
        db_evidence["database_row_id"] = latest.get("id")
        db_evidence["database_timestamp"] = latest.get("timestamp")
        db_evidence["database_symbol"] = latest.get("symbol")
        db_result = resolve_macro_context("NEUTRAL", "NEUTRAL", "NEUTRAL", db_evidence)
        db_result["mode"] = "database"
        db_result["source"] = "macro_data"
        db_result["database_row"] = {
            "id": latest.get("id"),
            "timestamp": latest.get("timestamp"),
            "symbol": latest.get("symbol"),
            "scope": latest.get("scope"),
            "source": latest.get("source"),
        }
        db_result["evidence"] = db_evidence
        return _augment_macro_result(db_result)

    if mode in {"manual", "off"}:
        reasons.append("Macro mode is manual; using explicit USD/risk/central-bank selections.")
        result["confidence"] = {
            "usd_bias": 0.25 if result["usd_bias"] != "NEUTRAL" else 0.0,
            "risk_sentiment": 0.25 if result["risk_sentiment"] != "NEUTRAL" else 0.0,
            "cb_divergence": 0.25 if result["cb_divergence"] != "NEUTRAL" else 0.0,
        }
        return _augment_macro_result(result)

    result["source"] = "evidence"
    usd_score = 0
    if _num(evidence, "dxy_change_percent") >= 0.25:
        usd_score += 1
        reasons.append("DXY change supports USD strength.")
    if _num(evidence, "dxy_change_percent") <= -0.25:
        usd_score -= 1
        reasons.append("DXY change supports USD weakness.")
    if _num(evidence, "usd_basket_change_percent") >= 0.20:
        usd_score += 1
        reasons.append("USD basket change supports USD strength.")
    if _num(evidence, "usd_basket_change_percent") <= -0.20:
        usd_score -= 1
        reasons.append("USD basket change supports USD weakness.")
    if _num(evidence, "fed_rate_expectation_change_bp") >= 5:
        usd_score += 1
        reasons.append("Fed rate expectations moved hawkish for USD.")
    if _num(evidence, "fed_rate_expectation_change_bp") <= -5:
        usd_score -= 1
        reasons.append("Fed rate expectations moved dovish for USD.")
    if _num(evidence, "us_yield_change_bp") >= 5:
        usd_score += 1
        reasons.append("US yields rose enough to support USD.")
    if _num(evidence, "us_yield_change_bp") <= -5:
        usd_score -= 1
        reasons.append("US yields fell enough to pressure USD.")
    if _num(evidence, "cot_usd_score") >= 0.20:
        usd_score += 1
        reasons.append("CFTC COT positioning supports USD strength.")
    if _num(evidence, "cot_usd_score") <= -0.20:
        usd_score -= 1
        reasons.append("CFTC COT positioning supports USD weakness.")
    usd_bias, usd_conf = _score_label(usd_score, "USD_BULLISH", "USD_BEARISH", "NEUTRAL")

    risk_score = 0
    if _num(evidence, "spx_change_percent") >= 0.50:
        risk_score += 1
        reasons.append("Equity proxy supports risk-on.")
    if _num(evidence, "spx_change_percent") <= -0.50:
        risk_score -= 1
        reasons.append("Equity proxy supports risk-off.")
    if _num(evidence, "vix_change_percent") <= -3:
        risk_score += 1
        reasons.append("VIX decline supports risk-on.")
    if _num(evidence, "vix_change_percent") >= 3:
        risk_score -= 1
        reasons.append("VIX rise supports risk-off.")
    if _num(evidence, "gold_change_percent") >= 0.50:
        risk_score -= 1
        reasons.append("Gold strength supports defensive/risk-off behavior.")
    if _num(evidence, "gold_change_percent") <= -0.50:
        risk_score += 1
        reasons.append("Gold weakness supports risk-on behavior.")
    if _num(evidence, "jpy_strength_score") <= -1 or _num(evidence, "chf_strength_score") <= -1:
        risk_score += 1
        reasons.append("Safe-haven weakness supports risk-on.")
    if _num(evidence, "jpy_strength_score") >= 1 or _num(evidence, "chf_strength_score") >= 1:
        risk_score -= 1
        reasons.append("Safe-haven strength supports risk-off.")
    risk_sentiment, risk_conf = _score_label(risk_score, "RISK_ON", "RISK_OFF", "NEUTRAL")

    cb_score = _num(evidence, "cb_divergence_bp")
    if cb_score == 0:
        cb_score = _num(evidence, "base_rate_expectation_change_bp") - _num(evidence, "quote_rate_expectation_change_bp")
    if abs(cb_score) < 10 and abs(_num(evidence, "cot_pair_score")) >= 0.20:
        cb_score = _num(evidence, "cot_pair_score") * 50
        reasons.append("CFTC COT positioning divergence is being used as a base-vs-quote positioning signal.")
    if cb_score >= 10:
        cb_divergence = "BULLISH_BASE"
        cb_conf = min(1.0, abs(cb_score) / 50)
        reasons.append("Base currency rate expectations are stronger than quote currency expectations.")
    elif cb_score <= -10:
        cb_divergence = "BEARISH_BASE"
        cb_conf = min(1.0, abs(cb_score) / 50)
        reasons.append("Base currency rate expectations are weaker than quote currency expectations.")
    else:
        cb_divergence = "NEUTRAL"
        cb_conf = 0.0
        reasons.append("Central-bank divergence evidence is neutral or too small.")

    high_impact = _bool(evidence, "high_impact_news")
    minutes_to_news = _num(evidence, "minutes_to_news", 9999)
    minutes_since_news = _num(evidence, "minutes_since_news", 9999)
    news_flag = high_impact or abs(minutes_to_news) <= 60 or 0 <= minutes_since_news <= 30
    if news_flag:
        reasons.append("News risk is active from high-impact flag or nearby event timing.")

    if usd_bias == "NEUTRAL":
        warnings.append("USD macro evidence is neutral; R25/R26 should not activate from macro evidence alone.")
    if risk_sentiment == "NEUTRAL":
        warnings.append("Risk sentiment evidence is neutral; R27/R28 should not activate from macro evidence alone.")
    if cb_divergence == "NEUTRAL":
        warnings.append("Central-bank divergence evidence is neutral; R29 should not activate from macro evidence alone.")

    result.update(
        {
            "usd_bias": usd_bias,
            "risk_sentiment": risk_sentiment,
            "cb_divergence": cb_divergence,
            "news_flag": news_flag,
            "confidence": {"usd_bias": round(usd_conf, 4), "risk_sentiment": round(risk_conf, 4), "cb_divergence": round(cb_conf, 4)},
            "scores": {"usd_score": usd_score, "risk_score": risk_score, "cb_score": round(cb_score, 2)},
        }
    )
    result["activation_allowed"] = {
        "R25": result["usd_bias"] == "USD_BULLISH" and _confidence_passes(result, "usd_bias", EVIDENCE_CONFIDENCE_MIN),
        "R26": result["usd_bias"] == "USD_BEARISH" and _confidence_passes(result, "usd_bias", EVIDENCE_CONFIDENCE_MIN),
        "R27": result["risk_sentiment"] == "RISK_ON" and _confidence_passes(result, "risk_sentiment", EVIDENCE_CONFIDENCE_MIN),
        "R28": result["risk_sentiment"] == "RISK_OFF" and _confidence_passes(result, "risk_sentiment", EVIDENCE_CONFIDENCE_MIN),
        "R29": result["cb_divergence"] != "NEUTRAL" and _confidence_passes(result, "cb_divergence", EVIDENCE_CONFIDENCE_MIN),
    }
    blocked = [regime for regime, allowed in result["activation_allowed"].items() if not allowed]
    if blocked:
        warnings.append(f"Evidence gate blocks {', '.join(blocked)} unless matching confidence is at least {EVIDENCE_CONFIDENCE_MIN:.2f}.")
    return _augment_macro_result(result)


def import_macro_csv(csv_text: str, source: str = "csv_upload") -> dict[str, Any]:
    if not csv_text.strip():
        raise ValueError("Macro CSV text is empty.")
    frame = pd.read_csv(StringIO(csv_text))
    if frame.empty:
        raise ValueError("Macro CSV did not contain any rows.")
    normalized_columns = {col: col.strip().lower() for col in frame.columns}
    frame = frame.rename(columns=normalized_columns)
    if "timestamp" not in frame.columns:
        raise ValueError("Macro CSV must include a timestamp column.")
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for idx, raw in frame.iterrows():
        raw_dict = {str(k): (None if pd.isna(v) else v) for k, v in raw.to_dict().items()}
        timestamp = _normalize_timestamp(raw_dict.get("timestamp"))
        symbol = _text(raw_dict, "symbol", "GLOBAL").upper() or "GLOBAL"
        scope = _text(raw_dict, "scope", "GLOBAL").upper() or "GLOBAL"
        row_source = _text(raw_dict, "source", source) or source
        evidence = _row_to_evidence(raw_dict)
        resolved = resolve_macro_context("NEUTRAL", "NEUTRAL", "NEUTRAL", evidence)
        if not any(resolved.get("activation_allowed", {}).values()):
            warnings.append(f"Row {idx + 1} imported but no R25-R29 macro regime passed the evidence confidence gate.")
        rows.append(
            {
                "timestamp": timestamp,
                "symbol": symbol,
                "scope": scope,
                "source": row_source,
                "dxy_change_percent": evidence.get("dxy_change_percent", 0),
                "usd_basket_change_percent": evidence.get("usd_basket_change_percent", 0),
                "us_yield_change_bp": evidence.get("us_yield_change_bp", 0),
                "fed_rate_expectation_change_bp": evidence.get("fed_rate_expectation_change_bp", 0),
                "spx_change_percent": evidence.get("spx_change_percent", 0),
                "vix_change_percent": evidence.get("vix_change_percent", 0),
                "gold_change_percent": evidence.get("gold_change_percent", 0),
                "jpy_strength_score": evidence.get("jpy_strength_score", 0),
                "chf_strength_score": evidence.get("chf_strength_score", 0),
                "base_rate_expectation_change_bp": evidence.get("base_rate_expectation_change_bp", 0),
                "quote_rate_expectation_change_bp": evidence.get("quote_rate_expectation_change_bp", 0),
                "cb_divergence_bp": evidence.get("cb_divergence_bp", 0),
                "high_impact_news": int(bool(evidence.get("high_impact_news"))),
                "minutes_to_news": evidence.get("minutes_to_news", 9999),
                "minutes_since_news": evidence.get("minutes_since_news", 9999),
                "event_currency": evidence.get("event_currency", ""),
                "event_name": evidence.get("event_name", ""),
                "event_impact": evidence.get("event_impact", ""),
                "notes": evidence.get("notes", ""),
                "evidence_json": json.dumps(evidence),
                "resolved_json": json.dumps(resolved),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    saved = save_macro_rows(rows)
    latest = rows[-1]
    return {
        "saved": saved,
        "rows_received": len(rows),
        "source": source,
        "columns_expected": CSV_COLUMNS,
        "latest": {
            "timestamp": latest["timestamp"],
            "symbol": latest["symbol"],
            "scope": latest["scope"],
            "resolved": json.loads(latest["resolved_json"]),
        },
        "warnings": warnings,
    }


def macro_evidence_from_database(symbol: str | None = None, as_of: str | None = None) -> dict[str, Any]:
    return resolve_macro_context("NEUTRAL", "NEUTRAL", "NEUTRAL", {"mode": "database", "symbol": symbol, "as_of": as_of})


def list_macro_evidence(symbol: str | None = None, start_date: str | None = None, end_date: str | None = None, limit: int = 100) -> dict[str, Any]:
    rows = load_macro_rows(symbol, start_date, end_date, limit)
    return {"count": len(rows), "rows": rows}


def macro_pipeline_diagnostics(
    symbol: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    as_of: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    rows = load_macro_rows(symbol, start_date, end_date, limit)
    latest = load_latest_macro_row(symbol, as_of or end_date)
    resolved = resolve_macro_context(
        "NEUTRAL",
        "NEUTRAL",
        "NEUTRAL",
        {"mode": "database", "symbol": symbol, "as_of": as_of or end_date},
    )
    latest_row = None
    if latest:
        latest_row = {
            "id": latest.get("id"),
            "timestamp": latest.get("timestamp"),
            "symbol": latest.get("symbol"),
            "scope": latest.get("scope"),
            "source": latest.get("source"),
            "notes": latest.get("notes"),
        }
    coverage = resolved.get("input_coverage", {})
    activation_table = resolved.get("activation_table", [])
    recommendations = list(resolved.get("recommendations", []))
    if not rows:
        recommendations.insert(0, "Import macro CSV/feed rows or build cross-pair evidence before relying on R25-R29.")
    status = resolved.get("quality_status", "NO_EVIDENCE")
    return {
        "status": status,
        "pipeline_ready": status == "EVIDENCE_READY",
        "symbol": (symbol or "GLOBAL").upper(),
        "start_date": start_date,
        "end_date": end_date,
        "as_of": as_of or end_date,
        "history_count": len(rows),
        "latest_row": latest_row,
        "resolved": resolved,
        "input_coverage": coverage,
        "activation_table": activation_table,
        "missing_inputs": resolved.get("missing_inputs", []),
        "recommendations": recommendations,
        "warnings": resolved.get("warnings", []),
        "rows": rows,
    }
