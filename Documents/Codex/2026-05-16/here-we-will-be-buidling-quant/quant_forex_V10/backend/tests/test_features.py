import pandas as pd

from backend.common.engines.feature_engine import calculate_features


def test_feature_engine_adds_core_columns():
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=120, freq="15min", tz="UTC"),
            "open": [1.10 + i * 0.0001 for i in range(120)],
            "high": [1.101 + i * 0.0001 for i in range(120)],
            "low": [1.099 + i * 0.0001 for i in range(120)],
            "close": [1.1005 + i * 0.0001 for i in range(120)],
            "tick_volume": [100] * 120,
            "spread": [10] * 120,
            "real_volume": [0] * 120,
        }
    )
    out = calculate_features(df, "M15")
    for col in [
        "atr",
        "er",
        "adx",
        "ema20",
        "ema50",
        "upper_wick_ratio",
        "sweep_high_flag",
        "session",
        "hurst_exponent",
        "fractal_dimension",
        "kalman_price",
        "garch_vol_forecast",
        "structural_break_score",
        "structural_break_flag",
        "hmm_state",
        "stat_regime_vote",
        "stat_regime_confidence",
    ]:
        assert col in out.columns
    assert len(out) == 120


def test_feature_engine_splits_warmup_from_bad_data():
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=60, freq="15min", tz="UTC"),
            "open": [1.10 + i * 0.0001 for i in range(60)],
            "high": [1.101 + i * 0.0001 for i in range(60)],
            "low": [1.099 + i * 0.0001 for i in range(60)],
            "close": [1.1005 + i * 0.0001 for i in range(60)],
            "tick_volume": [100] * 60,
            "spread": [10] * 60,
            "real_volume": [0] * 60,
        }
    )
    out = calculate_features(df, "M15")
    assert out.iloc[0]["data_quality_category"] == "R40-WARMUP"
    assert out.iloc[0]["data_quality_warmup_flag"] == 1
    assert out.iloc[0]["data_quality_bad_data_flag"] == 0

    bad = df.copy()
    bad.loc[10, "high"] = bad.loc[10, "low"] - 0.001
    bad_out = calculate_features(bad, "M15")
    assert "R40-BAD-DATA" in bad_out.loc[10, "data_quality_category"]
    assert bad_out.loc[10, "data_quality_bad_data_flag"] == 1
    assert "Invalid OHLC candle" in bad_out.loc[10, "data_quality_bad_data_reasons"]
