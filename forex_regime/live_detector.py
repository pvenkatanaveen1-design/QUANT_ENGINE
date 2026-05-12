"""
Live H1 strip for dashboard API: tick + ADX(14), ATR(14), EMA50/200, Q1–Q4 headline.

Uses an existing MT5 connection only (no initialize/shutdown here).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from forex_regime.mt5_setup import rates_to_dataframe
from forex_regime.regimes52.indicators import adx_wilder, atr_wilder, ema

PERIOD = 14
H1_COUNT = 200
EMA_SLOW = 50
EMA_LONG = 200

_QUADRANT_LABELS = {
    "Q1": "Trend Low Volatility",
    "Q2": "Trend High Volatility",
    "Q3": "Range Low Volatility",
    "Q4": "Transition / Chaos",
}


def _failure_dict() -> dict[str, Any]:
    return {
        "last_price": None,
        "spread": None,
        "adx_14": None,
        "atr_14": None,
        "atr_pct": None,
        "ema50": None,
        "ema200": None,
        "quadrant": None,
        "confidence": None,
        "label": None,
        "direction": None,
        "mt5_connected": False,
        "last_update": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def get_live_candles(
    symbol: str,
    mt5_module: Any,
    *,
    count: int = H1_COUNT,
) -> pd.DataFrame:
    """Last `count` H1 bars via copy_rates_from_pos; empty DataFrame if no data."""
    tf_h1 = mt5_module.TIMEFRAME_H1
    rates = mt5_module.copy_rates_from_pos(symbol, tf_h1, 0, int(count))
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = rates_to_dataframe(rates)
    if df.empty or "time" not in df.columns:
        return pd.DataFrame()
    return df.sort_values("time").reset_index(drop=True)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add ADX(14), ATR(14), EMA50, EMA200 (reuse regimes52 Wilder/EMA)."""
    out = df.copy()
    h = out["high"].astype(float)
    l = out["low"].astype(float)
    c = out["close"].astype(float)
    out["_adx14"] = adx_wilder(h, l, c, PERIOD)
    out["_atr14"] = atr_wilder(h, l, c, PERIOD)
    out["_ema50"] = ema(c, EMA_SLOW)
    out["_ema200"] = ema(c, EMA_LONG)
    return out


def classify_quadrant(adx: float, atr_pct: float) -> str:
    """Headline Q1–Q4 from ADX and ATR percentile (0–100)."""
    if adx >= 30.0 and atr_pct < 50.0:
        return "Q1"
    if adx >= 30.0 and atr_pct >= 50.0:
        return "Q2"
    if adx < 20.0 and atr_pct < 50.0:
        return "Q3"
    return "Q4"


def get_confidence(adx: float, atr_pct: float, quadrant: str) -> float:
    """0–100 confidence heuristic (headline strip only)."""
    if quadrant in ("Q1", "Q2"):
        adx_score = min(max(adx - 20.0, 0.0) / 30.0 * 100.0, 100.0)
    else:
        adx_score = min(max(20.0 - adx, 0.0) / 20.0 * 100.0, 100.0)
    atr_clarity = abs(float(atr_pct) - 50.0) * 2.0
    return round((adx_score + min(atr_clarity, 100.0)) / 2.0, 1)


def _spread_in_pips(tick: Any, info: Any) -> float | None:
    if tick is None or info is None:
        return None
    try:
        ask = float(tick.ask)
        bid = float(tick.bid)
    except (TypeError, ValueError):
        return None
    pt = float(info.point) if getattr(info, "point", None) else 0.0
    if pt <= 0:
        return None
    spr = ask - bid
    digits = int(getattr(info, "digits", 0) or 0)
    pip = pt * 10.0 if digits in (3, 5) else pt
    return round(spr / pip, 2) if pip > 0 else None


def _atr_percentile(last_atr: float, atr_tail: pd.Series) -> float:
    atr_series = atr_tail.dropna()
    if atr_series.empty:
        return 50.0
    lo = float(atr_series.min())
    hi = float(atr_series.max())
    denom = hi - lo + 1e-9
    return float(max(0.0, min(100.0, (float(last_atr) - lo) / denom * 100.0)))


def _direction(close: float, ema50: float, ema200: float) -> str:
    if close > ema50 > ema200:
        return "BULLISH"
    if close < ema50 < ema200:
        return "BEARISH"
    return "NEUTRAL"


def detect(
    symbol: str,
    mt5_module: Any | None = None,
    *,
    candle_count: int = H1_COUNT,
) -> dict[str, Any]:
    """
    Live snapshot dict for `symbol` using `mt5_module` (already initialized).
    Never raises; on any failure returns all-null dict with mt5_connected False.
    """
    out = _failure_dict()
    if mt5_module is None:
        return out
    try:
        if not str(symbol or "").strip():
            return out
        sym = str(symbol).strip()
        if not mt5_module.symbol_select(sym, True):
            return out
        tick = mt5_module.symbol_info_tick(sym)
        info = mt5_module.symbol_info(sym)
        if tick is None or info is None:
            return out

        df = get_live_candles(sym, mt5_module, count=candle_count)
        if df.empty:
            return out
        df = compute_indicators(df)
        row = df.iloc[-1]
        adx = float(row["_adx14"])
        atrv = float(row["_atr14"])
        close = float(row["close"])
        ema50v = float(row["_ema50"])
        ema200v = float(row["_ema200"])

        atr_tail = df["_atr14"].tail(20)
        atr_pct = _atr_percentile(atrv, atr_tail)

        q = classify_quadrant(adx, atr_pct)
        conf = get_confidence(adx, atr_pct, q)
        label = _QUADRANT_LABELS.get(q, "")
        direction = _direction(close, ema50v, ema200v)
        spr = _spread_in_pips(tick, info)

        out["last_price"] = float(tick.ask)
        out["spread"] = spr
        out["adx_14"] = round(adx, 4)
        out["atr_14"] = round(atrv, 6)
        out["atr_pct"] = round(atr_pct, 2)
        out["ema50"] = round(ema50v, 6)
        out["ema200"] = round(ema200v, 6)
        out["quadrant"] = q
        out["confidence"] = conf
        out["label"] = label
        out["direction"] = direction
        out["mt5_connected"] = True
        out["last_update"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return out
    except Exception:
        return _failure_dict()