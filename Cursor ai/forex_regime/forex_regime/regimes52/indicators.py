from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev = close.shift(1)
    return pd.concat([(high - low).abs(), (high - prev).abs(), low.sub(prev).abs()], axis=1).max(axis=1)


def atr_wilder(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


def adx_wilder(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """ADX (0–100) plus DI+ / DI-."""
    tr = true_range(high, low, close)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0.0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0.0), down_move, 0.0)
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean().replace(0.0, np.nan)
    plus_di = 100.0 * pd.Series(plus_dm, index=close.index).ewm(alpha=1.0 / period, adjust=False).mean() / atr
    minus_di = 100.0 * pd.Series(minus_dm, index=close.index).ewm(alpha=1.0 / period, adjust=False).mean() / atr
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1.0 / period, adjust=False).mean()
    return adx.fillna(0.0)


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0.0)
    down = (-d).clip(lower=0.0)
    ma_u = up.ewm(alpha=1.0 / period, adjust=False).mean()
    ma_d = down.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = ma_u / ma_d.replace(0.0, np.nan)
    return (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)


def ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def bollinger(close: pd.Series, period: int = 20, n_std: float = 2.0):
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + n_std * std
    lower = mid - n_std * std
    width = (upper - lower) / mid.replace(0.0, np.nan)
    return upper, lower, mid, width.fillna(0.0)


def hh_hl_score(close: pd.Series, lookback: int = 10) -> pd.Series:
    """+1 when recent higher high & higher low vs lookback window."""
    hh = close.rolling(lookback).max()
    ll = close.rolling(lookback).min()
    lag_hh = hh.shift(lookback)
    lag_ll = ll.shift(lookback)
    ok = (hh > lag_hh) & (ll > lag_ll)
    return ok.astype(float)


def lh_ll_score(close: pd.Series, lookback: int = 10) -> pd.Series:
    hh = close.rolling(lookback).max()
    ll = close.rolling(lookback).min()
    lag_hh = hh.shift(lookback)
    lag_ll = ll.shift(lookback)
    ok = (hh < lag_hh) & (ll < lag_ll)
    return ok.astype(float)


def zscore(close: pd.Series, period: int = 20) -> pd.Series:
    m = close.rolling(period).mean()
    s = close.rolling(period).std().replace(0.0, np.nan)
    return (close - m) / s


def hour_utc(ts: pd.Series) -> pd.Series:
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")
    return ts.dt.hour


def day_utc(ts: pd.Series) -> pd.Series:
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")
    return ts.dt.day
