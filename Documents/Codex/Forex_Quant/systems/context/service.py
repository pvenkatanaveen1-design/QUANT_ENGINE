from __future__ import annotations

import math
from pathlib import Path
from statistics import mean
from typing import Any

from systems.data import backend as data_backend
from systems.data.service import load_cleaned_rows


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def news_calendar_status() -> dict[str, Any]:
    return {
        "status": "unavailable_without_feed",
        "connector": "economic_calendar",
        "reason": "No calendar API key/feed is configured. Do not infer scheduled events from MT5 bars.",
    }


def sentiment_status() -> dict[str, Any]:
    return {
        "status": "unavailable_without_feed",
        "connector": "market_sentiment_feed",
        "reason": "No sentiment feed is configured. UI may show MT5 proxy shocks only.",
    }


def macro_context_status() -> dict[str, Any]:
    options = data_backend.get_market_options()
    symbols = [item.get("symbol") for item in (options.get("symbols") or {}).get("symbols", [])]
    dxy_candidates = [symbol for symbol in symbols if str(symbol).upper() in {"DXY", "USDX", "USDOLLAR", "USDOLLAR.F"}]
    return {
        "status": "available_from_mt5" if dxy_candidates else "unavailable_without_broker_symbol",
        "dxy_candidates": dxy_candidates,
        "carry_status": "unavailable_without_swap_or_rates_feed",
        "rule": "Use broker-provided DXY/swap/rates data only. Do not fabricate macro alignment.",
    }


def _returns(rows: list[dict[str, Any]]) -> list[float]:
    closes = [float(row["close"]) for row in rows]
    out: list[float] = []
    for index in range(1, len(closes)):
        if closes[index - 1] > 0:
            out.append(math.log(closes[index] / closes[index - 1]))
    return out


def _corr(a: list[float], b: list[float]) -> float:
    size = min(len(a), len(b))
    if size < 5:
        return 0.0
    x = a[-size:]
    y = b[-size:]
    mx = mean(x)
    my = mean(y)
    numerator = sum((xv - mx) * (yv - my) for xv, yv in zip(x, y))
    denom_x = math.sqrt(sum((xv - mx) ** 2 for xv in x))
    denom_y = math.sqrt(sum((yv - my) ** 2 for yv in y))
    denominator = denom_x * denom_y
    return numerator / denominator if denominator else 0.0


def correlation_context(symbol: str, timeframe: str, peers: list[str] | None = None) -> dict[str, Any]:
    peers = peers or ["GBPUSD", "AUDUSD", "USDJPY", "XAUUSD"]
    try:
        base_rows = load_cleaned_rows(symbol.upper(), timeframe.upper())
    except Exception as exc:
        return {"status": "unavailable_without_cached_data", "error": str(exc), "correlations": []}
    base_returns = _returns(base_rows)
    rows: list[dict[str, Any]] = []
    for peer in peers:
        if peer.upper() == symbol.upper():
            continue
        try:
            peer_rows = load_cleaned_rows(peer.upper(), timeframe.upper())
        except Exception:
            continue
        rows.append({"symbol": peer.upper(), "correlation": round(_corr(base_returns, _returns(peer_rows)), 4)})
    return {
        "status": "available_from_cached_mt5_data" if rows else "unavailable_without_peer_data",
        "symbol": symbol.upper(),
        "timeframe": timeframe.upper(),
        "correlations": rows,
    }


def full_context_status(symbol: str = "EURUSD", timeframe: str = "M15") -> dict[str, Any]:
    return {
        "news": news_calendar_status(),
        "sentiment": sentiment_status(),
        "macro": macro_context_status(),
        "correlation": correlation_context(symbol, timeframe),
        "hmm": {
            "status": "future_phase",
            "reason": "Hamilton/HMM layer is intentionally gated until backtest and paper validation are stable.",
        },
    }

