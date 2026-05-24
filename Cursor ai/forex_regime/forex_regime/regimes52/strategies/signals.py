from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from forex_regime.regimes52.indicators import (
    adx_wilder,
    atr_wilder,
    bollinger,
    ema,
    zscore as zs,
)
from forex_regime.regimes52.classify import Regime52Params

# Thresholds shared by strategy_signal and PDF legends (keep in sync).
DONCHIAN_PERIOD = 20
CONTINUATION_BODY_FRAC = 0.45
TREND_DRIFT_ADX_MIN = 18.0
RSI_FADE_OVERSOLD = 32.0
RSI_FADE_OVERBOUGHT = 68.0
SQUEEZE_BW_WINDOW = 100
SQUEEZE_BW_MIN_PERIODS = 40
SQUEEZE_BW_QUANTILE = 0.28
SQUEEZE_IMPULSE_ATR_MULT = 1.15
IMPULSE_RET3_THRESH = 0.008
IMPULSE_RSI_LONG_MAX = 42.0
IMPULSE_RSI_SHORT_MIN = 58.0
FADE_BB_HIGH_MULT = 0.999
FADE_BB_LOW_MULT = 1.001
ZSCORE_FADE_ABS = 1.6
RANGE_EQ_WIN = 80
RANGE_EQ_BUY_BELOW = 0.34
RANGE_EQ_SELL_ABOVE = 0.66
WICK_BODY_MULT = 1.2
VOL_SPIKE_ATR_MA_WIN = 50
VOL_SPIKE_ATR_MULT = 1.55
NARROW_RANGE_WIN = 8
TINY_DRIFT_EMA_ATR_FRAC = 0.2


def side_rule_label(side: int) -> str:
    if int(side) == 1:
        return "side=+1 → only bullish rule arm fires long"
    if int(side) == -1:
        return "side=-1 → only bearish rule arm fires short"
    return "side=0 → model picks long or short from rules"


def signal_kind_legend(kind: str, p: Regime52Params | None = None) -> str:
    """
    Human-readable parameter names and numeric values for PDF / docs.
    Uses the same constants as strategy_signal; EMA/BB/RSI/Z windows from `p`.
    """
    if p is None:
        p = Regime52Params()
    k = str(kind)
    if k == "pullback_with_trend":
        return (
            f"EMA windows (Regime52Params): ema_fast={p.ema_fast}, ema_ob={p.ema_ob}, "
            f"ema_slow={p.ema_slow}\n"
            "Long: low≤ema_ob & close>ema_ob & close>ema50 & ema_fast>ema50\n"
            "Short: high≥ema_ob & close<ema_ob & close<ema50 & ema_fast<ema50"
        )
    if k == "breakout_with_trend":
        return (
            f"Donchian high/low: rolling max(high) / min(low), period={DONCHIAN_PERIOD}\n"
            f"EMA filter: close vs ema_slow (period={p.ema_slow})\n"
            "Long: close > prior Donchian high & close > ema_slow\n"
            "Short: close < prior Donchian low & close < ema_slow"
        )
    if k == "continuation_bar":
        return (
            f"Body filter: |close-open| > {CONTINUATION_BODY_FRAC}×(high-low)\n"
            f"EMA trend filter: ema_fast={p.ema_fast}, ema_slow={p.ema_slow}\n"
            "Long: bullish bar, body filter, close>ema_fast, ema_fast>ema_slow\n"
            "Short: bearish bar, body filter, close<ema_fast, ema_fast<ema_slow"
        )
    if k == "trend_drift":
        return (
            f"ADX filter: Wilder ADX period={p.adx_period}, threshold > {TREND_DRIFT_ADX_MIN:g}\n"
            f"EMA slow={p.ema_slow}: long if close>ema & 1-bar return>0 & ADX OK; short mirrored"
        )
    if k == "fade_extreme_rsi":
        return (
            f"RSI period={p.rsi_period}: long if RSI < {RSI_FADE_OVERSOLD:g}; "
            f"short if RSI > {RSI_FADE_OVERBOUGHT:g} (sideRule trims which arm fires)"
        )
    if k == "squeeze_breakout_dir":
        return (
            "BB width = (upper-lower)/middle on BB from "
            f"bb_period={p.bb_period}\n"
            f"Tight width: < rolling {SQUEEZE_BW_WINDOW}-bar quantile {SQUEEZE_BW_QUANTILE} "
            f"(min_periods={SQUEEZE_BW_MIN_PERIODS})\n"
            f"Impulse bar: (high-low) > {SQUEEZE_IMPULSE_ATR_MULT}×ATR (ATR period={p.adx_period})\n"
            f"Direction: vs ema_slow={p.ema_slow} and candle color (side={0}: both dirs)"
        )
    if k == "impulse_reversal":
        return (
            f"3-bar return < -{IMPULSE_RET3_THRESH} & RSI < {IMPULSE_RSI_LONG_MAX:g} → long; "
            f"3-bar return > {IMPULSE_RET3_THRESH} & RSI > {IMPULSE_RSI_SHORT_MIN:g} → short\n"
            f"(RSI period={p.rsi_period})"
        )
    if k == "fade_bb_high":
        return f"Short when close ≥ upper_BB × {FADE_BB_HIGH_MULT} (bb_period={p.bb_period})"
    if k == "fade_bb_low":
        return f"Long when close ≤ lower_BB × {FADE_BB_LOW_MULT} (bb_period={p.bb_period})"
    if k == "zscore_fade":
        return (
            f"Z-score window={p.z_period}: short if z > +{ZSCORE_FADE_ABS:g}; "
            f"long if z < -{ZSCORE_FADE_ABS:g}"
        )
    if k == "range_equilibrium":
        return (
            f"Range position over {RANGE_EQ_WIN} bars: pos = (close-lo)/(hi-lo)\n"
            f"Long if pos < {RANGE_EQ_BUY_BELOW:g}; short if pos > {RANGE_EQ_SELL_ABOVE:g}"
        )
    if k == "wick_reversal":
        return (
            f"Lower wick > {WICK_BODY_MULT}×|body| & bullish bar → long; "
            f"upper wick > {WICK_BODY_MULT}×|body| & bearish bar → short"
        )
    if k == "vol_spike_fade":
        return (
            f"ATR({p.adx_period}) > {VOL_SPIKE_ATR_MULT}× "
            f"{VOL_SPIKE_ATR_MA_WIN}-bar ATR mean → fade: long on bearish close, short on bullish close"
        )
    if k == "narrow_range_break_fake":
        return (
            f"Narrow range: range < prior min range over {NARROW_RANGE_WIN} bars; "
            "fade: short on bearish close, long on bullish close"
        )
    if k == "tiny_drift":
        return (
            f"|ema_fast-ema_slow|/ATR < {TINY_DRIFT_EMA_ATR_FRAC} "
            f"(ema_fast={p.ema_fast}, ema_slow={p.ema_slow}, ATR period={p.adx_period})\n"
            "Long: 1-bar return > 0; short: 1-bar return < 0"
        )
    return f"(No built-in legend for signal_kind={kind!r}.)"


@dataclass
class SignalContext:
    open: pd.Series
    high: pd.Series
    low: pd.Series
    close: pd.Series
    ema_f: pd.Series
    ema_ob: pd.Series
    ema50: pd.Series
    atr: pd.Series
    adx: pd.Series
    rsi: pd.Series
    z: pd.Series
    upper_bb: pd.Series
    lower_bb: pd.Series
    mid_bb: pd.Series
    don_hi: pd.Series
    don_lo: pd.Series


def build_signal_context(df: pd.DataFrame, p: Regime52Params | None = None) -> SignalContext:
    if p is None:
        p = Regime52Params()
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)
    o = df["open"].astype(float)
    atr = atr_wilder(h, l, c, p.adx_period)
    adx_v = adx_wilder(h, l, c, p.adx_period)
    rsi = _rsi(c, p.rsi_period)
    u, lo, mid, _ = bollinger(c, p.bb_period)
    z = zs(c, p.z_period)
    ema_f = ema(c, p.ema_fast)
    ema_ob = ema(c, p.ema_ob)
    ema50 = ema(c, p.ema_slow)
    don_hi = h.rolling(DONCHIAN_PERIOD).max()
    don_lo = l.rolling(DONCHIAN_PERIOD).min()
    return SignalContext(
        open=o,
        high=h,
        low=l,
        close=c,
        ema_f=ema_f,
        ema_ob=ema_ob,
        ema50=ema50,
        atr=atr,
        adx=adx_v,
        rsi=rsi,
        z=z,
        upper_bb=u,
        lower_bb=lo,
        mid_bb=mid,
        don_hi=don_hi,
        don_lo=don_lo,
    )


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0.0)
    down = (-d).clip(lower=0.0)
    ma_u = up.ewm(alpha=1.0 / period, adjust=False).mean()
    ma_d = down.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = ma_u / ma_d.replace(0.0, np.nan)
    return (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)


def strategy_signal(ctx: SignalContext, kind: str, side: int) -> pd.Series:
    """
    Return int8 series: 0 flat, +1 long entry, -1 short entry (same index as OHLC).
    side==0 means direction comes from model rule (trend/squeeze).
    """
    c = ctx.close
    idx = c.index
    out = pd.Series(0, index=idx, dtype=np.int8)
    o = ctx.open
    h = ctx.high
    l = ctx.low
    rng = (h - l).replace(0.0, np.nan)
    body = (c - o).abs()

    if kind == "pullback_with_trend":
        up = (l <= ctx.ema_ob) & (c > ctx.ema_ob) & (c > ctx.ema50) & (ctx.ema_f > ctx.ema50)
        dn = (h >= ctx.ema_ob) & (c < ctx.ema_ob) & (c < ctx.ema50) & (ctx.ema_f < ctx.ema50)
        if side == 1:
            out.loc[up] = 1
        elif side == -1:
            out.loc[dn] = -1
        else:
            out.loc[up] = 1
            out.loc[dn] = -1
        return out

    if kind == "breakout_with_trend":
        up = (c > ctx.don_hi.shift(1)) & (c > ctx.ema50)
        dn = (c < ctx.don_lo.shift(1)) & (c < ctx.ema50)
        if side == 1:
            out.loc[up] = 1
        elif side == -1:
            out.loc[dn] = -1
        else:
            out.loc[up] = 1
            out.loc[dn] = -1
        return out

    if kind == "continuation_bar":
        up = (c > o) & (body > CONTINUATION_BODY_FRAC * rng) & (c > ctx.ema_f) & (ctx.ema_f > ctx.ema50)
        dn = (c < o) & (body > CONTINUATION_BODY_FRAC * rng) & (c < ctx.ema_f) & (ctx.ema_f < ctx.ema50)
        if side == 1:
            out.loc[up] = 1
        elif side == -1:
            out.loc[dn] = -1
        else:
            out.loc[up] = 1
            out.loc[dn] = -1
        return out

    if kind == "trend_drift":
        ret1 = c.pct_change()
        up = (c > ctx.ema50) & (ret1 > 0) & (ctx.adx > TREND_DRIFT_ADX_MIN)
        dn = (c < ctx.ema50) & (ret1 < 0) & (ctx.adx > TREND_DRIFT_ADX_MIN)
        if side == 1:
            out.loc[up] = 1
        elif side == -1:
            out.loc[dn] = -1
        else:
            out.loc[up] = 1
            out.loc[dn] = -1
        return out

    if kind == "fade_extreme_rsi":
        if side == 1:
            out.loc[ctx.rsi < RSI_FADE_OVERSOLD] = 1
        elif side == -1:
            out.loc[ctx.rsi > RSI_FADE_OVERBOUGHT] = -1
        else:
            out.loc[ctx.rsi > RSI_FADE_OVERBOUGHT] = -1
            out.loc[ctx.rsi < RSI_FADE_OVERSOLD] = 1
        return out

    if kind == "squeeze_breakout_dir":
        bw = (ctx.upper_bb - ctx.lower_bb) / ctx.mid_bb.replace(0.0, np.nan)
        tight = bw < bw.rolling(SQUEEZE_BW_WINDOW, min_periods=SQUEEZE_BW_MIN_PERIODS).quantile(
            SQUEEZE_BW_QUANTILE
        )
        impulse = rng > SQUEEZE_IMPULSE_ATR_MULT * ctx.atr
        up = tight.shift(1).fillna(False) & impulse & (c > o) & (c > ctx.ema50)
        dn = tight.shift(1).fillna(False) & impulse & (c < o) & (c < ctx.ema50)
        out.loc[up] = 1
        out.loc[dn] = -1
        return out

    if kind == "impulse_reversal":
        ret3 = c.pct_change(3)
        out.loc[(ret3 < -IMPULSE_RET3_THRESH) & (ctx.rsi < IMPULSE_RSI_LONG_MAX)] = 1
        out.loc[(ret3 > IMPULSE_RET3_THRESH) & (ctx.rsi > IMPULSE_RSI_SHORT_MIN)] = -1
        return out

    if kind == "fade_bb_high":
        out.loc[c >= ctx.upper_bb * FADE_BB_HIGH_MULT] = -1
        return out

    if kind == "fade_bb_low":
        out.loc[c <= ctx.lower_bb * FADE_BB_LOW_MULT] = 1
        return out

    if kind == "zscore_fade":
        out.loc[ctx.z > ZSCORE_FADE_ABS] = -1
        out.loc[ctx.z < -ZSCORE_FADE_ABS] = 1
        return out

    if kind == "range_equilibrium":
        hi = h.rolling(RANGE_EQ_WIN).max()
        lo2 = l.rolling(RANGE_EQ_WIN).min()
        sp = (hi - lo2).replace(0.0, np.nan)
        pos = (c - lo2) / sp
        out.loc[pos < RANGE_EQ_BUY_BELOW] = 1
        out.loc[pos > RANGE_EQ_SELL_ABOVE] = -1
        return out

    if kind == "wick_reversal":
        lower_wick = np.minimum(o, c) - l
        upper_wick = h - np.maximum(o, c)
        bull = (lower_wick > WICK_BODY_MULT * body) & (c > o)
        bear = (upper_wick > WICK_BODY_MULT * body) & (c < o)
        out.loc[bull] = 1
        out.loc[bear] = -1
        return out

    if kind == "vol_spike_fade":
        atr_ma = ctx.atr.rolling(VOL_SPIKE_ATR_MA_WIN).mean()
        spike = ctx.atr > VOL_SPIKE_ATR_MULT * atr_ma
        out.loc[spike & (c < o)] = 1
        out.loc[spike & (c > o)] = -1
        return out

    if kind == "narrow_range_break_fake":
        nr = rng < rng.rolling(NARROW_RANGE_WIN).min().shift(1)
        out.loc[nr & (c < o)] = -1
        out.loc[nr & (c > o)] = 1
        return out

    if kind == "tiny_drift":
        squeeze = (ctx.ema_f - ctx.ema50).abs() / ctx.atr.replace(0.0, np.nan) < TINY_DRIFT_EMA_ATR_FRAC
        out.loc[squeeze & (c.pct_change() > 0)] = 1
        out.loc[squeeze & (c.pct_change() < 0)] = -1
        return out

    return out
