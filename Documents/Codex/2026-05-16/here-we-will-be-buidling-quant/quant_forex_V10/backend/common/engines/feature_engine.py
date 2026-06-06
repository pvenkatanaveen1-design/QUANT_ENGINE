from __future__ import annotations

import numpy as np
import pandas as pd

from backend.macro_data_engine import resolve_macro_context


HTF_RESAMPLE = {
    "M1": "5min",
    "M5": "15min",
    "M15": "1h",
    "M30": "1h",
    "H1": "4h",
    "H4": "1D",
    "D1": "1D",
}

TIMEFRAME_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}

STAT_REGIME_STATES = ("trend", "range", "stress")


def _wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _rolling_percentile(series: pd.Series, window: int = 252) -> pd.Series:
    min_periods = max(20, min(window, 20))
    return series.rolling(window=window, min_periods=min_periods).rank(method="max", pct=True) * 100


def _session(ts: pd.Timestamp) -> str:
    hour = ts.hour
    if 21 <= hour < 22:
        return "Rollover"
    if 12 <= hour < 16:
        return "Overlap"
    if 0 <= hour < 7:
        return "Asia"
    if 7 <= hour < 12:
        return "London"
    if 12 <= hour < 17:
        return "NewYork"
    return "OffSession"


def _session_series(timestamps: pd.Series) -> pd.Series:
    hour = timestamps.dt.hour
    return pd.Series(
        np.select(
            [
                (hour >= 21) & (hour < 22),
                (hour >= 12) & (hour < 16),
                (hour >= 0) & (hour < 7),
                (hour >= 7) & (hour < 12),
                (hour >= 12) & (hour < 17),
            ],
            ["Rollover", "Overlap", "Asia", "London", "NewYork"],
            default="OffSession",
        ),
        index=timestamps.index,
    )


def _linear_regression_slope(values: np.ndarray) -> float:
    valid = values[~np.isnan(values)]
    if len(valid) < 2:
        return np.nan
    x = np.arange(len(valid), dtype=float)
    return float(np.polyfit(x, valid, 1)[0])


def _linear_regression_last(values: np.ndarray) -> float:
    valid = values[~np.isnan(values)]
    if len(valid) < 2:
        return np.nan
    x = np.arange(len(valid), dtype=float)
    slope, intercept = np.polyfit(x, valid, 1)
    return float(intercept + slope * (len(valid) - 1))


def _rolling_linear_regression(series: pd.Series, window: int = 50, min_periods: int = 20) -> tuple[pd.Series, pd.Series]:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    n_rows = len(values)
    slope = np.full(n_rows, np.nan, dtype=float)
    last = np.full(n_rows, np.nan, dtype=float)
    if n_rows < min_periods or np.isnan(values).any():
        return (
            series.rolling(window, min_periods=min_periods).apply(_linear_regression_slope, raw=True),
            series.rolling(window, min_periods=min_periods).apply(_linear_regression_last, raw=True),
        )

    indexes = np.arange(n_rows, dtype=float)
    prefix_y = np.concatenate([[0.0], np.cumsum(values)])
    prefix_jy = np.concatenate([[0.0], np.cumsum(indexes * values)])

    end = np.arange(n_rows)
    start = np.maximum(0, end - window + 1)
    length = end - start + 1
    valid = length >= min_periods

    sum_y = prefix_y[end + 1] - prefix_y[start]
    sum_jy = prefix_jy[end + 1] - prefix_jy[start]
    sum_xy = sum_jy - start * sum_y
    sum_x = length * (length - 1) / 2
    sum_x2 = (length - 1) * length * (2 * length - 1) / 6
    denom = length * sum_x2 - sum_x * sum_x
    valid = valid & (denom != 0)

    slope_values = np.full(n_rows, np.nan, dtype=float)
    np.divide(length * sum_xy - sum_x * sum_y, denom, out=slope_values, where=denom != 0)
    intercept_values = (sum_y - slope_values * sum_x) / length
    slope[valid] = slope_values[valid]
    last[valid] = intercept_values[valid] + slope_values[valid] * (length[valid] - 1)
    return pd.Series(slope, index=series.index), pd.Series(last, index=series.index)


def _bars_since_event(event: pd.Series) -> pd.Series:
    indexes = pd.Series(np.arange(len(event)), index=event.index, dtype=float)
    last_event = indexes.where(event.astype(bool)).ffill()
    return (indexes - last_event).where(last_event.notna(), np.nan)


def _hurst_window(values: np.ndarray) -> float:
    clean = values[~np.isnan(values)]
    if len(clean) < 40:
        return np.nan
    lags = np.array([2, 4, 8, 16], dtype=int)
    tau = []
    used_lags = []
    for lag in lags:
        if len(clean) <= lag:
            continue
        diff = clean[lag:] - clean[:-lag]
        value = np.std(diff)
        if value > 0:
            tau.append(value)
            used_lags.append(lag)
    if len(tau) < 2:
        return np.nan
    slope = np.polyfit(np.log(used_lags), np.log(tau), 1)[0]
    return float(np.clip(slope, 0.0, 1.0))


def _rolling_hurst(series: pd.Series, window: int = 100, min_periods: int = 80) -> pd.Series:
    return series.rolling(window=window, min_periods=min_periods).apply(_hurst_window, raw=True)


def _kalman_level(series: pd.Series, process_var: float = 1e-5, measurement_var: float = 1e-3) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    estimates = np.full(len(values), np.nan, dtype=float)
    estimate = np.nan
    error_cov = 1.0
    for i, value in enumerate(values):
        if np.isnan(value):
            estimates[i] = estimate
            continue
        if np.isnan(estimate):
            estimate = value
            estimates[i] = estimate
            continue
        error_cov += process_var
        gain = error_cov / (error_cov + measurement_var)
        estimate = estimate + gain * (value - estimate)
        error_cov = (1 - gain) * error_cov
        estimates[i] = estimate
    return pd.Series(estimates, index=series.index)


def _garch_forecast_vol(close: pd.Series, omega: float = 1e-8, alpha: float = 0.08, beta: float = 0.90) -> pd.Series:
    returns = pd.to_numeric(close, errors="coerce").pct_change().fillna(0.0).to_numpy(dtype=float)
    variance = np.full(len(returns), np.nan, dtype=float)
    seed = float(np.nanvar(returns[: min(len(returns), 100)])) if len(returns) else 0.0
    current_var = max(seed, omega / max(1e-6, 1 - alpha - beta))
    for i, ret in enumerate(returns):
        current_var = omega + alpha * (ret ** 2) + beta * current_var
        variance[i] = current_var
    return pd.Series(np.sqrt(np.maximum(variance, 0.0)), index=close.index)


def _rolling_structural_break_score(close: pd.Series, short_window: int = 20, long_window: int = 100) -> pd.Series:
    returns = pd.to_numeric(close, errors="coerce").pct_change()
    short_mean = returns.rolling(short_window, min_periods=max(5, short_window // 2)).mean()
    long_mean = returns.rolling(long_window, min_periods=max(30, long_window // 2)).mean()
    long_std = returns.rolling(long_window, min_periods=max(30, long_window // 2)).std().replace(0, np.nan)
    return ((short_mean - long_mean).abs() / long_std).replace([np.inf, -np.inf], np.nan)


def _state_probs_from_scores(trend_score: pd.Series, range_score: pd.Series, stress_score: pd.Series) -> pd.DataFrame:
    scores = pd.concat([trend_score, range_score, stress_score], axis=1).fillna(0.0).to_numpy(dtype=float)
    probs = np.full_like(scores, np.nan, dtype=float)
    transition = np.array(
        [
            [0.86, 0.10, 0.04],
            [0.12, 0.82, 0.06],
            [0.10, 0.15, 0.75],
        ],
        dtype=float,
    )
    prior = np.array([0.34, 0.46, 0.20], dtype=float)
    for i, row in enumerate(scores):
        row = row - np.nanmax(row)
        likelihood = np.exp(row)
        likelihood = likelihood / likelihood.sum() if likelihood.sum() else np.array([0.34, 0.46, 0.20])
        predicted = transition.T @ prior
        posterior = predicted * likelihood
        posterior = posterior / posterior.sum() if posterior.sum() else likelihood
        probs[i] = posterior
        prior = posterior
    return pd.DataFrame(probs, index=trend_score.index, columns=["hmm_trend_probability", "hmm_range_probability", "hmm_stress_probability"])


def _add_statistical_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    df["hurst_exponent"] = _rolling_hurst(df["close"])
    df["hurst_state"] = np.select(
        [df["hurst_exponent"] >= 0.58, df["hurst_exponent"] <= 0.42],
        ["trend", "range"],
        default="neutral",
    )
    df["fractal_dimension"] = 2.0 - df["hurst_exponent"]
    df["fractal_dimension_state"] = np.select(
        [df["fractal_dimension"] <= 1.42, df["fractal_dimension"] >= 1.58],
        ["trend", "range"],
        default="neutral",
    )

    df["kalman_price"] = _kalman_level(df["close"])
    df["kalman_slope"] = (df["kalman_price"] - df["kalman_price"].shift(10)) / df["atr"].replace(0, np.nan)
    df["kalman_trend_state"] = np.select(
        [df["kalman_slope"] >= 0.15, df["kalman_slope"] <= -0.15],
        ["bullish", "bearish"],
        default="neutral",
    )

    df["garch_vol_forecast"] = _garch_forecast_vol(df["close"])
    df["garch_vol_percentile"] = _rolling_percentile(df["garch_vol_forecast"])
    df["garch_vol_state"] = np.select(
        [df["garch_vol_percentile"] >= 85, df["garch_vol_percentile"] <= 25],
        ["stress", "quiet"],
        default="normal",
    )
    df["structural_break_score"] = _rolling_structural_break_score(df["close"])
    df["structural_break_flag"] = (
        (df["structural_break_score"] >= 2.50)
        | (
            (df["garch_vol_percentile"] >= 90)
            & (pd.to_numeric(df["candle_range_atr"], errors="coerce").fillna(0) >= 1.50)
        )
    ).astype(int)
    df["structural_break_direction"] = np.select(
        [
            (df["structural_break_flag"] == 1) & (df["close"] > df["close"].shift(20)),
            (df["structural_break_flag"] == 1) & (df["close"] < df["close"].shift(20)),
        ],
        ["bullish", "bearish"],
        default="neutral",
    )

    trend_score = (
        (pd.to_numeric(df["er"], errors="coerce").fillna(0) >= 0.25).astype(float)
        + (pd.to_numeric(df["adx"], errors="coerce").fillna(0) >= 18).astype(float)
        + (df["hurst_state"] == "trend").astype(float)
        + (df["fractal_dimension_state"] == "trend").astype(float)
        + (df["kalman_trend_state"] != "neutral").astype(float)
        - (df["garch_vol_state"] == "stress").astype(float) * 0.5
        - (df["structural_break_flag"] == 1).astype(float) * 0.5
    )
    range_score = (
        (pd.to_numeric(df["er"], errors="coerce").fillna(0) <= 0.25).astype(float)
        + (pd.to_numeric(df["adx"], errors="coerce").fillna(100) <= 18).astype(float)
        + (df["hurst_state"] == "range").astype(float)
        + (df["fractal_dimension_state"] == "range").astype(float)
        + (df["ema50_cross_count"].fillna(0) >= 3).astype(float)
    )
    stress_score = (
        (pd.to_numeric(df["atr_percentile"], errors="coerce").fillna(0) >= 90).astype(float)
        + (pd.to_numeric(df["spread_percentile"], errors="coerce").fillna(0) >= 90).astype(float)
        + (df["garch_vol_state"] == "stress").astype(float)
        + (df["structural_break_flag"] == 1).astype(float)
        + (pd.to_numeric(df["candle_range_atr"], errors="coerce").fillna(0) >= 2.0).astype(float)
    )
    probs = _state_probs_from_scores(trend_score, range_score, stress_score)
    df = pd.concat([df, probs], axis=1)
    prob_values = probs.to_numpy(dtype=float)
    max_idx = np.nanargmax(np.where(np.isnan(prob_values), -1, prob_values), axis=1)
    df["hmm_state"] = [STAT_REGIME_STATES[i] for i in max_idx]
    df["hmm_state_probability"] = np.nanmax(prob_values, axis=1)

    votes = pd.DataFrame(
        {
            "er": np.select([df["er"] >= 0.25, df["er"] <= 0.20], ["trend", "range"], default="neutral"),
            "adx": np.select([df["adx"] >= 18, df["adx"] <= 15], ["trend", "range"], default="neutral"),
            "hurst": df["hurst_state"],
            "fractal": df["fractal_dimension_state"],
            "kalman": np.where(df["kalman_trend_state"] == "neutral", "neutral", "trend"),
            "garch": np.where(df["garch_vol_state"] == "stress", "stress", "neutral"),
            "structural_break": np.where(df["structural_break_flag"] == 1, "stress", "neutral"),
            "hmm": df["hmm_state"],
        },
        index=df.index,
    )
    vote_counts = pd.DataFrame({state: (votes == state).sum(axis=1) for state in STAT_REGIME_STATES}, index=df.index)
    df["stat_regime_vote"] = vote_counts.idxmax(axis=1)
    df["stat_regime_confidence"] = vote_counts.max(axis=1) / len(votes.columns)
    df["stat_regime_direction"] = np.select(
        [df["kalman_trend_state"] == "bullish", df["kalman_trend_state"] == "bearish"],
        ["bullish", "bearish"],
        default=df["ltf_bias"],
    )
    df["stat_regime_disagreement"] = (df["stat_regime_confidence"] < 0.50).astype(int)
    df["stat_regime_summary"] = (
        "vote=" + df["stat_regime_vote"].astype(str)
        + ";conf=" + df["stat_regime_confidence"].round(2).astype(str)
        + ";hurst=" + df["hurst_state"].astype(str)
        + ";fdi=" + df["fractal_dimension_state"].astype(str)
        + ";kalman=" + df["kalman_trend_state"].astype(str)
        + ";garch=" + df["garch_vol_state"].astype(str)
        + ";break=" + df["structural_break_flag"].astype(str)
        + ";hmm=" + df["hmm_state"].astype(str)
    )
    return df


def _calculate_htf(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    rule = HTF_RESAMPLE.get(timeframe.upper(), "1h")
    source = df[["timestamp", "open", "high", "low", "close"]].copy().set_index("timestamp")
    htf = source.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    if htf.empty:
        df["htf_close"] = df["close"]
        df["htf_ema50"] = df["ema50"]
        return df
    htf["htf_close"] = htf["close"]
    htf["htf_ema50"] = htf["close"].ewm(span=50, adjust=False, min_periods=10).mean()
    htf = htf[["htf_close", "htf_ema50"]].reset_index()
    return pd.merge_asof(df.sort_values("timestamp"), htf.sort_values("timestamp"), on="timestamp", direction="backward")


def _add_opening_ranges(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    df = df.copy()
    minutes = TIMEFRAME_MINUTES.get(timeframe.upper(), 15)
    opening_bars = max(1, int(np.ceil(30 / minutes)))
    tradable_sessions = {"Asia", "London", "NewYork", "Overlap"}

    df["session_date"] = df["timestamp"].dt.date
    df["session_key"] = np.where(df["session"].isin(tradable_sessions), df["session"], "None")
    df["session_bar_index"] = df.groupby(["session_date", "session_key"]).cumcount()
    in_opening = (df["session_key"] != "None") & (df["session_bar_index"] < opening_bars)

    opening = (
        df[in_opening]
        .groupby(["session_date", "session_key"])
        .agg(opening_range_high=("high", "max"), opening_range_low=("low", "min"))
        .reset_index()
    )
    if opening.empty:
        df["opening_range_high"] = np.nan
        df["opening_range_low"] = np.nan
        df["opening_range_mid"] = np.nan
    else:
        opening["opening_range_mid"] = (opening["opening_range_high"] + opening["opening_range_low"]) / 2
        df = df.merge(opening, on=["session_date", "session_key"], how="left")
    df["orb_up"] = (df["close"] > df["opening_range_high"] + df["atr"] * 0.10).astype(int)
    df["orb_down"] = (df["close"] < df["opening_range_low"] - df["atr"] * 0.10).astype(int)

    asia = (
        df[df["session"] == "Asia"]
        .groupby("session_date")
        .agg(asia_high=("high", "max"), asia_low=("low", "min"))
        .reset_index()
    )
    if asia.empty:
        df["asia_high"] = np.nan
        df["asia_low"] = np.nan
        df["asia_midpoint"] = np.nan
    else:
        asia["asia_midpoint"] = (asia["asia_high"] + asia["asia_low"]) / 2
        df = df.merge(asia, on="session_date", how="left")
    return df.drop(columns=["session_date", "session_key"])


def calculate_features(
    candles: pd.DataFrame,
    timeframe: str = "M15",
    sentiment: str = "NEUTRAL",
    usd_bias: str = "NEUTRAL",
    risk_sentiment: str = "NEUTRAL",
    cb_divergence: str = "NEUTRAL",
    macro_evidence: dict | None = None,
) -> pd.DataFrame:
    if candles.empty:
        return candles.copy()

    df = candles.copy().sort_values("timestamp").reset_index(drop=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    spread_missing_source = pd.Series("spread" not in df.columns, index=df.index)
    if "spread" in df.columns:
        spread_missing_source = df["spread"].isna()
    required_ohlc = ["open", "high", "low", "close"]
    missing_ohlc_source = pd.Series(False, index=df.index)
    for col in required_ohlc:
        if col not in df:
            missing_ohlc_source = pd.Series(True, index=df.index)
            break
        missing_ohlc_source = missing_ohlc_source | df[col].isna()
    duplicate_timestamp = df["timestamp"].duplicated(keep=False)
    for col in ["open", "high", "low", "close", "tick_volume", "spread", "real_volume"]:
        if col not in df:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    invalid_ohlc = (
        (df["high"] < df["low"])
        | (df["close"] > df["high"])
        | (df["close"] < df["low"])
        | (df["open"] > df["high"])
        | (df["open"] < df["low"])
    )
    zero_range = df["high"] == df["low"]
    df["missing_ohlc"] = missing_ohlc_source.astype(int)
    df["invalid_ohlc"] = invalid_ohlc.astype(int)
    df["zero_range"] = zero_range.astype(int)
    df["duplicate_timestamp"] = duplicate_timestamp.astype(int)
    df["spread_missing"] = spread_missing_source.astype(int)

    prev_close = df["close"].shift(1)
    df["previous_close"] = prev_close
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = _wilder(tr, 14)
    df["atr_percent"] = np.where(df["close"] != 0, df["atr"] / df["close"] * 100, np.nan)
    df["atr_percentile"] = _rolling_percentile(df["atr_percent"])
    df["gap_size"] = (df["open"] - prev_close).abs()
    df["gap_atr"] = df["gap_size"] / df["atr"].replace(0, np.nan)
    df["gap_flag"] = (df["gap_atr"] >= 0.75).astype(int)
    df["gap_fill_percent"] = np.where(df["gap_size"] > 0, (df["close"] - df["open"]).abs() / df["gap_size"], 0)

    df["ema20"] = df["close"].ewm(span=20, adjust=False, min_periods=10).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False, min_periods=20).mean()
    df = _calculate_htf(df, timeframe)
    df["htf_bias"] = np.select(
        [df["htf_close"] > df["htf_ema50"], df["htf_close"] < df["htf_ema50"]],
        ["bullish", "bearish"],
        default="neutral",
    )
    df["htf_unavailable"] = df["htf_close"].isna().astype(int)
    df["ltf_bias"] = np.select(
        [df["close"] > df["ema50"], df["close"] < df["ema50"]],
        ["bullish", "bearish"],
        default="neutral",
    )
    df["ema_slope"] = (df["ema50"] - df["ema50"].shift(10)) / df["atr"].replace(0, np.nan)
    df["distance_from_ema20_atr"] = (df["close"] - df["ema20"]) / df["atr"].replace(0, np.nan)
    df["distance_from_ema50_atr"] = (df["close"] - df["ema50"]) / df["atr"].replace(0, np.nan)

    plus_dm_raw = df["high"] - df["high"].shift(1)
    minus_dm_raw = df["low"].shift(1) - df["low"]
    plus_dm = np.where((plus_dm_raw > minus_dm_raw) & (plus_dm_raw > 0), plus_dm_raw, 0.0)
    minus_dm = np.where((minus_dm_raw > plus_dm_raw) & (minus_dm_raw > 0), minus_dm_raw, 0.0)
    plus_di = 100 * _wilder(pd.Series(plus_dm, index=df.index), 14) / df["atr"].replace(0, np.nan)
    minus_di = 100 * _wilder(pd.Series(minus_dm, index=df.index), 14) / df["atr"].replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di
    df["adx"] = _wilder(dx, 14)
    df["adx_slope"] = df["adx"] - df["adx"].shift(5)

    n = 30
    movement = (df["close"] - df["close"].shift(n)).abs()
    noise = df["close"].diff().abs().rolling(n, min_periods=n).sum()
    df["er"] = movement / noise.replace(0, np.nan)
    df["er_slope"] = df["er"] - df["er"].shift(5)
    df["ema_slope_change"] = df["ema_slope"] - df["ema_slope"].shift(5)
    df["trend_weakening"] = ((df["adx_slope"] < 0) & (df["er_slope"] < 0)).astype(int)

    basis = df["close"].rolling(20, min_periods=20).mean()
    std = df["close"].rolling(20, min_periods=20).std()
    upper = basis + 2 * std
    lower = basis - 2 * std
    df["bb_basis"] = basis
    df["bb_upper"] = upper
    df["bb_lower"] = lower
    df["bb_width"] = upper - lower
    df["bb_width_percentile"] = _rolling_percentile(df["bb_width"])

    df["candle_range"] = df["high"] - df["low"]
    df["candle_range_atr"] = df["candle_range"] / df["atr"].replace(0, np.nan)
    same_price = df["candle_range"] == 0
    df["upper_wick_ratio"] = np.where(
        same_price,
        0,
        (df["high"] - df[["open", "close"]].max(axis=1)) / df["candle_range"],
    )
    df["lower_wick_ratio"] = np.where(
        same_price,
        0,
        (df[["open", "close"]].min(axis=1) - df["low"]) / df["candle_range"],
    )

    df["prev_swing_high"] = df["high"].shift(1).rolling(20, min_periods=5).max()
    df["prev_swing_low"] = df["low"].shift(1).rolling(20, min_periods=5).min()
    df["range_midpoint"] = (df["prev_swing_high"] + df["prev_swing_low"]) / 2

    day = df["timestamp"].dt.date
    daily_high = df.groupby(day)["high"].transform("max")
    daily_low = df.groupby(day)["low"].transform("min")
    day_frame = pd.DataFrame({"date": day, "daily_high": daily_high, "daily_low": daily_low}).drop_duplicates("date")
    day_frame["prev_day_high"] = day_frame["daily_high"].shift(1)
    day_frame["prev_day_low"] = day_frame["daily_low"].shift(1)
    df = df.merge(day_frame[["date", "prev_day_high", "prev_day_low"]], left_on=day, right_on="date", how="left").drop(columns=["date"])

    df["sweep_high_flag"] = (
        (df["high"] > df["prev_swing_high"])
        & (df["close"] < df["prev_swing_high"])
        & (df["upper_wick_ratio"] >= 0.40)
    ).astype(int)
    df["sweep_low_flag"] = (
        (df["low"] < df["prev_swing_low"])
        & (df["close"] > df["prev_swing_low"])
        & (df["lower_wick_ratio"] >= 0.40)
    ).astype(int)
    df["compression_flag"] = ((df["atr_percentile"] < 25) | (df["bb_width_percentile"] < 25)).astype(int)
    df["volatility_expansion_flag"] = ((df["atr_percentile"] >= 75) & (df["candle_range_atr"] >= 1.2)).astype(int)
    df["spread"] = df["spread"].fillna(0)
    df["spread_percentile"] = _rolling_percentile(df["spread"]).fillna(0)
    spread_stress_event = df["spread_percentile"] >= 90
    df["spread_was_stressed"] = (df["spread_percentile"].rolling(10, min_periods=1).max() >= 90).astype(int)
    df["spread_stress_bars_ago"] = _bars_since_event(spread_stress_event)
    df["spread_now_normal"] = (df["spread_percentile"] < 70).astype(int)
    df["post_stress_normalization"] = (
        (df["spread_was_stressed"] == 1)
        & (df["spread_now_normal"] == 1)
        & (df["candle_range_atr"] < 2.0)
        & (df["spread_stress_bars_ago"] >= 3)
    ).astype(int)
    df["session"] = _session_series(df["timestamp"])
    macro_context = resolve_macro_context(usd_bias, risk_sentiment, cb_divergence, macro_evidence)
    df["news_flag"] = int(bool(macro_context.get("news_flag", False)))
    df["sentiment"] = sentiment
    df["usd_bias"] = macro_context["usd_bias"]
    df["risk_sentiment"] = macro_context["risk_sentiment"]
    df["cb_divergence"] = macro_context["cb_divergence"]
    df["macro_source"] = macro_context["source"]
    df["macro_usd_confidence"] = macro_context["confidence"]["usd_bias"]
    df["macro_risk_confidence"] = macro_context["confidence"]["risk_sentiment"]
    df["macro_cb_confidence"] = macro_context["confidence"]["cb_divergence"]
    df["macro_reasons"] = "; ".join(macro_context["reasons"])

    cross = np.sign(df["close"] - df["ema50"]).diff().abs().fillna(0) > 0
    df["ema50_cross_count_30"] = cross.rolling(30, min_periods=5).sum()
    df["ema50_cross_count"] = df["ema50_cross_count_30"]
    df = _add_statistical_regime_features(df)
    df["mtf_conflict_score"] = (
        ((df["htf_bias"] != df["ltf_bias"]) & (df["htf_bias"] != "neutral") & (df["ltf_bias"] != "neutral")).astype(int)
        + (df["adx"] < 18).astype(int)
        + (df["er"] < 0.25).astype(int)
        + (df["ema50_cross_count"] >= 3).astype(int)
    )
    df["bull_pullback_failure"] = (
        (df["htf_bias"] == "bullish")
        & (df["close"] < df["ema20"])
        & (df["close"] < df["open"])
        & (df["plus_di"] > df["minus_di"])
        & (df["er_slope"] < 0)
    ).astype(int)
    df["bear_pullback_failure"] = (
        (df["htf_bias"] == "bearish")
        & (df["close"] > df["ema20"])
        & (df["close"] > df["open"])
        & (df["minus_di"] > df["plus_di"])
        & (df["er_slope"] < 0)
    ).astype(int)

    df["drift_strength"] = df["ema_slope"].abs() * df["er"]
    df["channel_slope"], df["channel_mid"] = _rolling_linear_regression(df["close"], 50, 20)
    df["channel_deviation"] = (df["close"] - df["channel_mid"]).rolling(50, min_periods=20).std()
    df["channel_upper"] = df["channel_mid"] + df["channel_deviation"] * 2
    df["channel_lower"] = df["channel_mid"] - df["channel_deviation"] * 2
    channel_width = (df["channel_upper"] - df["channel_lower"]).replace(0, np.nan)
    df["channel_position"] = (df["close"] - df["channel_lower"]) / channel_width
    df["near_channel_support"] = (df["channel_position"] <= 0.25).astype(int)
    df["near_channel_resistance"] = (df["channel_position"] >= 0.75).astype(int)
    df["near_range_high"] = (df["high"] >= df["prev_swing_high"] - df["atr"] * 0.20).astype(int)
    df["near_range_low"] = (df["low"] <= df["prev_swing_low"] + df["atr"] * 0.20).astype(int)
    df["false_upside_breakout"] = (
        (df["close"].shift(1) > df["prev_swing_high"].shift(1))
        & (df["close"] < df["prev_swing_high"])
        & (df["upper_wick_ratio"] >= 0.35)
    ).astype(int)
    df["false_downside_breakout"] = (
        (df["close"].shift(1) < df["prev_swing_low"].shift(1))
        & (df["close"] > df["prev_swing_low"])
        & (df["lower_wick_ratio"] >= 0.35)
    ).astype(int)
    df = _add_opening_ranges(df, timeframe).copy()

    df["chop_score"] = (
        (df["adx"] <= 18).astype(int)
        + (df["er"] <= 0.20).astype(int)
        + (df["atr_percentile"] >= 75).astype(int)
        + (df["ema50_cross_count"] >= 4).astype(int)
        + (df["candle_range_atr"] >= 1.2).astype(int)
    )
    df["dead_market_score"] = (
        (df["atr_percentile"] < 15).astype(int)
        + (df["bb_width_percentile"] < 15).astype(int)
        + (df["adx"] < 15).astype(int)
        + (df["candle_range_atr"] < 0.70).astype(int)
    )
    df["is_month_end"] = (df["timestamp"].dt.day >= 25).astype(int)
    minutes_since_midnight = df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute
    df["is_fixing_window"] = ((minutes_since_midnight >= 15 * 60) & (minutes_since_midnight <= 16 * 60 + 15)).astype(int)
    df["overlap_trend"] = (
        (df["session"] == "Overlap")
        & (df["htf_bias"] == df["ltf_bias"])
        & (df["htf_bias"] != "neutral")
        & (df["adx"] >= 18)
        & (df["atr_percentile"] >= 25)
        & (df["atr_percentile"] <= 90)
    ).astype(int)
    df["asia_range"] = (
        (df["session"] == "Asia")
        & (df["adx"] <= 18)
        & (df["er"] <= 0.25)
        & (df["atr_percentile"] <= 75)
    ).astype(int)
    session_key = df["timestamp"].dt.date.astype(str) + "_" + df["session"].astype(str)
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    volume = df["tick_volume"].replace(0, np.nan).fillna(1.0)
    pv = typical_price * volume
    # Defragment after the feature build-up so the final research columns remain cheap to add.
    df = df.copy()
    df["session_vwap"] = pv.groupby(session_key).cumsum() / volume.groupby(session_key).cumsum().replace(0, np.nan)
    df["distance_from_vwap_atr"] = (df["close"] - df["session_vwap"]) / df["atr"].replace(0, np.nan)
    df["vwap_extreme_high"] = (df["distance_from_vwap_atr"] >= 1.5).astype(int)
    df["vwap_extreme_low"] = (df["distance_from_vwap_atr"] <= -1.5).astype(int)
    df["gap_bars_ago"] = _bars_since_event(df["gap_flag"] == 1)

    required_features = ["adx", "er", "atr", "atr_percentile", "bb_width_percentile", "prev_swing_high", "prev_swing_low"]
    df["feature_nan_required"] = df[required_features].isna().any(axis=1).astype(int)
    df["data_quality_warmup_flag"] = (df["feature_nan_required"] == 1).astype(int)
    df["data_quality_bad_data_flag"] = (
        (df["missing_ohlc"] == 1)
        | (df["invalid_ohlc"] == 1)
        | (df["zero_range"] == 1)
        | (df["duplicate_timestamp"] == 1)
        | (df["spread_missing"] == 1)
        | (df["htf_unavailable"] == 1)
    ).astype(int)
    df["data_quality_flag"] = (
        (df["data_quality_warmup_flag"] == 1)
        | (df["data_quality_bad_data_flag"] == 1)
    ).astype(int)
    df["data_quality_warmup_reasons"] = np.where(
        df["data_quality_warmup_flag"] == 1,
        "Not enough bars for ATR/ADX/ER/percentile/swing warmup",
        "",
    )
    bad_reasons = pd.Series("", index=df.index, dtype=object)
    for mask, reason in [
        (df["missing_ohlc"] == 1, "Missing OHLC data"),
        (df["invalid_ohlc"] == 1, "Invalid OHLC candle"),
        (df["zero_range"] == 1, "Zero-range candle"),
        (df["duplicate_timestamp"] == 1, "Duplicate timestamp"),
        (df["spread_missing"] == 1, "Spread missing"),
        (df["htf_unavailable"] == 1, "HTF data unavailable"),
    ]:
        bad_reasons = pd.Series(
            np.where(mask & bad_reasons.ne(""), bad_reasons + ", " + reason, np.where(mask, reason, bad_reasons)),
            index=df.index,
            dtype=object,
        )
    df["data_quality_bad_data_reasons"] = bad_reasons
    df["data_quality_category"] = np.select(
        [
            (df["data_quality_bad_data_flag"] == 1) & (df["data_quality_warmup_flag"] == 1),
            df["data_quality_bad_data_flag"] == 1,
            df["data_quality_warmup_flag"] == 1,
        ],
        ["R40-BAD-DATA+WARMUP", "R40-BAD-DATA", "R40-WARMUP"],
        default="OK",
    )
    warmup_reasons = df["data_quality_warmup_reasons"].astype(str)
    df["data_quality_reasons"] = np.where(
        bad_reasons.ne("") & warmup_reasons.ne(""),
        bad_reasons + ", " + warmup_reasons,
        bad_reasons + warmup_reasons,
    )

    return df.copy()
