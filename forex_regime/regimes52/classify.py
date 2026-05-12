from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from forex_regime.regimes52.indicators import (
    adx_wilder,
    atr_wilder,
    bollinger,
    ema,
    hh_hl_score,
    hour_utc,
    lh_ll_score,
    rsi_wilder,
    zscore,
)
from forex_regime.regimes52.taxonomy import REGIME_NAME, quadrant_for_id


@dataclass(frozen=True)
class Regime52Params:
    adx_period: int = 14
    rsi_period: int = 14
    ema_slow: int = 50
    ema_ob: int = 20
    ema_fast: int = 12
    structure_lb: int = 10
    mom_lookback: int = 60
    bb_period: int = 20
    z_period: int = 20
    squeeze_win: int = 250
    vol_cluster_win: int = 48
    hmm_vol_quantile: float = 0.75


def _has(df: pd.DataFrame, col: str) -> bool:
    return col in df.columns and df[col].notna().any()


def add_regime52_columns(df: pd.DataFrame, p: Regime52Params | None = None) -> pd.DataFrame:
    """
    Add operational 52-regime labels (single primary `regime52_id` per bar).

    **OHLC columns required:** `time`, `open`, `high`, `low`, `close`.
    **Optional `tick_volume`** improves microstructure proxies (41–43).

    **Optional context columns** (same index as df), when present, activate macro/event regimes:
    - `ctx_vix` (float): VIX level for 25–27.
    - `ctx_dxy_close` (float): DXY series for 49–50 trends.
    - `ctx_yield_inverted` (0/1 bool): regime 23.
    - `ctx_macro` (str): one of `HIKE`, `CUT`, `QE`, `QT`, `STAG`, `DEFL`, `REFL` for 16–22.
    - `ctx_geopolitical` (bool): regime 32.
    - `ctx_cot_extreme` (bool): regime 51.
    - `ctx_pre_fomc` (bool): regime 29.
    - `ctx_options_expiry` (bool): regime 33.
    - `ctx_post_news_reversal` (bool): regime 31.
    - `ctx_intermarket_div` (bool): regime 52.

    Without context, IDs 16–23,29,31–34,32,51–52 may never fire—this is intentional.

    **Conflict resolution:** first rule in priority order claims the bar (see source).
    """
    if p is None:
        p = Regime52Params()

    out = df.copy()
    h = out["high"].astype(float)
    l = out["low"].astype(float)
    c = out["close"].astype(float)
    o = out["open"].astype(float)
    t = out["time"]
    atr = atr_wilder(h, l, c, p.adx_period)
    adx = adx_wilder(h, l, c, p.adx_period)
    rsi = rsi_wilder(c, p.rsi_period)
    ema50 = ema(c, p.ema_slow)
    ema_ob = ema(c, p.ema_ob)
    ema_f = ema(c, p.ema_fast)
    _, _, _, bb_w = bollinger(c, p.bb_period)
    z = zscore(c, p.z_period)
    ret1 = c.pct_change()
    ret_n = c.pct_change(p.mom_lookback)
    mom_hi = ret_n > ret_n.rolling(260, min_periods=80).quantile(0.88)
    roll_vol = ret1.rolling(20).std()
    vol_ma = roll_vol.rolling(100).mean()
    atr_ma = atr.rolling(100).mean()
    rng = (h - l).replace(0.0, np.nan)
    body = (c - o).abs()
    wick_ratio = rng / body.replace(0.0, np.nan)
    hh = hh_hl_score(c, p.structure_lb) > 0.5
    lhl = lh_ll_score(c, p.structure_lb) > 0.5

    hi_win = h.rolling(100).max()
    lo_win = l.rolling(100).min()
    span = (hi_win - lo_win).replace(0.0, np.nan)
    pos_in_range = (c - lo_win) / span

    squeeze_thresh = bb_w.rolling(max(p.squeeze_win, 50), min_periods=30).quantile(0.20)
    abs_ret = ret1.abs()
    abs_lag = abs_ret.shift(1)
    vol_cl = (abs_ret > roll_vol * 1.15) & (abs_lag > roll_vol * 1.15)

    claimed = pd.Series(False, index=out.index)
    rid = pd.Series(6, index=out.index, dtype="int64")

    def claim(mask: pd.Series, regime_id: int) -> None:
        nonlocal rid, claimed
        m = mask.fillna(False) & ~claimed
        rid = rid.where(~m, regime_id)
        claimed = claimed | m

    # --- Stress / flows (price + optional VIX) ---
    liq = (ret1 < -(2.2 * atr / c.replace(0.0, np.nan))) & (atr / atr_ma.replace(0.0, np.nan) > 1.75)
    claim(liq, 28)

    if _has(out, "ctx_vix"):
        vx = out["ctx_vix"].astype(float)
        claim(vx > 30.0, 26)
        claim((vx > 20.0) & (vx <= 30.0), 25)
    else:
        fear_px = (rsi < 32.0) & (roll_vol > roll_vol.rolling(200, min_periods=40).quantile(0.85))
        claim(fear_px, 26)
        roff = (rsi < 40.0) & (adx > 28.0) & (c < ema50)
        claim(roff, 25)

    if _has(out, "ctx_geopolitical"):
        claim(out["ctx_geopolitical"].astype(bool), 32)

    if _has(out, "ctx_yield_inverted"):
        claim(out["ctx_yield_inverted"].astype(bool).fillna(False), 23)

    if _has(out, "ctx_macro"):
        mx = out["ctx_macro"].astype(str).str.upper().str.strip()
        claim(mx.eq("DEFL"), 21)
        claim(mx.eq("STAG"), 20)
        claim(mx.eq("REFL"), 22)
        claim(mx.eq("QT"), 19)
        claim(mx.eq("QE"), 18)
        claim(mx.eq("HIKE"), 16)
        claim(mx.eq("CUT"), 17)

    # Stop / crash patterns
    wide = rng > 2.4 * atr
    cascade = wide & (body / rng.replace(0.0, np.nan) < 0.35)
    claim(cascade, 44)

    crash = mom_hi.shift(1).fillna(False) & (c.pct_change(3) < -(1.35 * atr / c.replace(0.0, np.nan)))
    claim(crash, 5)

    if _has(out, "ctx_post_news_reversal"):
        claim(out["ctx_post_news_reversal"].astype(bool).fillna(False), 31)

    claim(bb_w < squeeze_thresh, 9)
    claim(z.abs() > 2.0, 7)

    bull = (adx > 40.0) & (rsi > 55.0) & (c > ema50) & hh
    bear = (adx > 40.0) & (rsi < 45.0) & (c < ema50) & lhl
    claim(bull, 1)
    claim(bear, 2)

    markdown = (adx > 22.0) & (ema_f < ema50) & (c < ema50) & (ret_n < 0)
    markup = (adx > 22.0) & (ema_f > ema50) & (c > ema50) & (ret_n > 0)
    dist = (adx > 18.0) & (pos_in_range > 0.72) & (rsi > 58.0) & (~bull)
    acc = (adx < 22.0) & (pos_in_range < 0.35) & (bb_w < bb_w.rolling(120, min_periods=40).median())

    claim(markdown, 13)
    claim(markup, 11)
    claim(dist, 12)
    claim(acc, 10)

    reacc = (ema_f > ema50) & (adx < adx.shift(4)) & (adx.between(18.0, 32.0))
    redist = (ema_f < ema50) & (adx < adx.shift(4)) & (adx.between(18.0, 32.0))
    claim(reacc, 14)
    claim(redist, 15)

    weak = adx.between(25.0, 40.0) & (adx > adx.shift(3)) & (rsi.sub(50.0).abs() < 14.0)
    claim(weak, 3)

    manip = (body < 0.28 * rng) & (rng > 0.9 * atr)
    claim(manip, 35)
    exp = manip.shift(1).fillna(False) & (body > 0.55 * rng) & (rng > 1.1 * atr)
    claim(exp, 36)

    hr = hour_utc(t)
    claim(hr.isin([7, 8, 12, 13, 14, 15, 16]), 38)
    claim((hr.between(0, 6)) & (adx < 25.0), 37)

    ob_long = (ema_f > ema50) & (c < ema_ob) & (c.shift(1) >= ema_ob.shift(1))
    ob_short = (ema_f < ema50) & (c > ema_ob) & (c.shift(1) <= ema_ob.shift(1))
    claim(ob_long | ob_short, 39)

    fvg_up = l > h.shift(2)
    fvg_dn = h < l.shift(2)
    claim(fvg_up | fvg_dn, 40)

    if _has(out, "tick_volume"):
        v = out["tick_volume"].astype(float)
        dv = v.pct_change().replace([np.inf, -np.inf], np.nan)
        imb = (np.sign(c - o) * v).rolling(8).sum()
        claim(imb.abs() > imb.rolling(80, min_periods=30).quantile(0.85), 41)
        claim((rng < 0.8 * atr) & (dv > 0.6), 42)
        trend_sign = np.sign(ema_f - ema50)
        vol_dn = v < v.rolling(10).mean() * 0.85
        claim((trend_sign != 0) & vol_dn & (adx > 22.0), 43)
    else:
        imb = (c - o) * rng
        claim(imb.abs() > imb.rolling(100, min_periods=50).quantile(0.9), 41)

    hmm = roll_vol > roll_vol.rolling(p.vol_cluster_win * 4, min_periods=60).quantile(p.hmm_vol_quantile)
    claim(hmm, 45)
    claim(vol_cl, 46)

    claim(ret_n > 0.025, 4)

    if _has(out, "ctx_vix"):
        greed = (out["ctx_vix"].astype(float) < 14.0) & (bb_w < bb_w.rolling(200, min_periods=50).median())
        claim(greed, 27)

    risk_on = (rsi.between(52.0, 68.0)) & (adx < 34.0) & (roll_vol < roll_vol.rolling(120, min_periods=40).median())
    claim(risk_on, 24)

    cont = (ret1.abs() > (1.1 * atr / c.replace(0.0, np.nan))) & (np.sign(ret1) == np.sign(ret_n.replace(0.0, np.nan)))
    claim(cont, 30)

    if _has(out, "ctx_pre_fomc"):
        claim(out["ctx_pre_fomc"].astype(bool).fillna(False), 29)
    if _has(out, "ctx_options_expiry"):
        claim(out["ctx_options_expiry"].astype(bool).fillna(False), 33)

    # EOM last ~3 UTC calendar days
    if pd.api.types.is_datetime64_any_dtype(t):
        dt = t.dt.tz_convert("UTC") if t.dt.tz is not None else t.dt.tz_localize("UTC")
        last = dt + pd.offsets.MonthEnd(0)
        claim((last - dt).dt.days < 3, 34)

    # Carry: proxy sustained directional drift + low vol — research anchor only
    carry = (ret_n > 0.012) & (roll_vol < roll_vol.rolling(200, min_periods=60).quantile(0.35))
    claim(carry, 47)

    mom_sign = np.sign(ret_n.rolling(20).mean())
    rev_sign = np.sign(z)
    fact = (mom_sign != 0) & (rev_sign != 0) & (mom_sign != rev_sign) & (adx.between(20.0, 35.0))
    claim(fact, 48)

    if _has(out, "ctx_dxy_close"):
        dx = out["ctx_dxy_close"].astype(float)
        dret = dx.pct_change(40)
        claim(dret > 0.01, 49)
        claim(dret < -0.01, 50)

    if _has(out, "ctx_cot_extreme"):
        claim(out["ctx_cot_extreme"].astype(bool).fillna(False), 51)
    if _has(out, "ctx_intermarket_div"):
        claim(out["ctx_intermarket_div"].astype(bool).fillna(False), 52)

    out["regime52_id"] = rid.astype(int)
    out["regime52_name"] = out["regime52_id"].map(REGIME_NAME).fillna("Unknown")
    out["regime52_quad"] = out["regime52_id"].map(quadrant_for_id)
    # diagnostics used by strategies / debugging
    out["_reg52_adx"] = adx
    out["_reg52_rsi"] = rsi
    out["_reg52_atr"] = atr
    return out
