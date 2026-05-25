from backend.common.engines.regime_engine import detect_regime


def test_detect_r01_clean_bullish_trend():
    row = {
        "htf_bias": "bullish",
        "ltf_bias": "bullish",
        "adx": 24,
        "plus_di": 30,
        "minus_di": 15,
        "er": 0.31,
        "atr_percentile": 55,
        "atr": 0.001,
        "ema_slope": 0.2,
        "spread_percentile": 20,
        "distance_from_ema20_atr": 0.5,
        "news_flag": 0,
        "session": "London",
        "bb_width_percentile": 50,
        "candle_range_atr": 0.8,
        "prev_swing_high": 1.2,
        "prev_swing_low": 1.1,
    }
    result = detect_regime(row)
    assert result["regime_id"] == "R01"
    assert result["is_active"] is True


def test_detect_r40_warmup_subtype():
    result = detect_regime(
        {
            "feature_nan_required": 1,
            "data_quality_flag": 1,
            "data_quality_warmup_flag": 1,
            "data_quality_bad_data_flag": 0,
            "data_quality_category": "R40-WARMUP",
            "data_quality_warmup_reasons": "Not enough bars for ATR/ADX/ER/percentile/swing warmup",
            "missing_ohlc": 0,
            "invalid_ohlc": 0,
            "zero_range": 0,
            "duplicate_timestamp": 0,
            "spread_missing": 0,
            "htf_unavailable": 0,
        }
    )
    assert result["regime_id"] == "R40"
    assert result["regime_subtype"] == "R40-WARMUP"
    assert "Warmup only" in result["reason"]


def test_detect_r40_bad_data_subtype():
    result = detect_regime(
        {
            "feature_nan_required": 0,
            "data_quality_flag": 1,
            "data_quality_warmup_flag": 0,
            "data_quality_bad_data_flag": 1,
            "data_quality_category": "R40-BAD-DATA",
            "data_quality_bad_data_reasons": "Invalid OHLC candle",
            "data_quality_reasons": "Invalid OHLC candle",
            "missing_ohlc": 0,
            "invalid_ohlc": 1,
            "zero_range": 0,
            "duplicate_timestamp": 0,
            "spread_missing": 0,
            "htf_unavailable": 0,
        }
    )
    assert result["regime_id"] == "R40"
    assert result["regime_subtype"] == "R40-BAD-DATA"
    assert "Manual review required" in result["reason"]


def test_macro_regime_requires_evidence_confidence_not_manual_bias():
    row = {
        "symbol": "EURUSD",
        "htf_bias": "bearish",
        "ltf_bias": "bearish",
        "usd_bias": "USD_BULLISH",
        "risk_sentiment": "NEUTRAL",
        "cb_divergence": "NEUTRAL",
        "macro_source": "manual",
        "macro_usd_confidence": 0.25,
        "macro_risk_confidence": 0,
        "macro_cb_confidence": 0,
        "adx": 24,
        "plus_di": 12,
        "minus_di": 30,
        "er": 0.31,
        "atr": 0.001,
        "atr_percentile": 55,
        "bb_width_percentile": 50,
        "ema_slope": -0.2,
        "spread_percentile": 20,
        "distance_from_ema20_atr": -0.5,
        "news_flag": 0,
        "session": "London",
        "candle_range_atr": 0.8,
        "prev_swing_high": 1.2,
        "prev_swing_low": 1.1,
    }
    result = detect_regime(row)
    assert result["regime_id"] != "R25"


def test_macro_regime_activates_with_evidence_confidence():
    row = {
        "symbol": "EURUSD",
        "htf_bias": "bearish",
        "ltf_bias": "bearish",
        "usd_bias": "USD_BULLISH",
        "risk_sentiment": "NEUTRAL",
        "cb_divergence": "NEUTRAL",
        "macro_source": "evidence",
        "macro_usd_confidence": 0.75,
        "macro_risk_confidence": 0,
        "macro_cb_confidence": 0,
        "adx": 24,
        "plus_di": 12,
        "minus_di": 30,
        "er": 0.31,
        "atr": 0.001,
        "atr_percentile": 55,
        "bb_width_percentile": 50,
        "ema_slope": -0.2,
        "spread_percentile": 20,
        "distance_from_ema20_atr": -0.5,
        "news_flag": 0,
        "session": "London",
        "candle_range_atr": 0.8,
        "prev_swing_high": 1.2,
        "prev_swing_low": 1.1,
    }
    result = detect_regime(row)
    assert result["regime_id"] == "R25"
    assert result["direction"] == "short"


def test_detect_r44_trend_day_before_generic_clean_trend():
    row = {
        "symbol": "EURUSD",
        "timestamp": None,
        "open": 1.18,
        "high": 1.19,
        "low": 1.179,
        "close": 1.188,
        "htf_bias": "bullish",
        "ltf_bias": "bullish",
        "adx": 31,
        "plus_di": 34,
        "minus_di": 12,
        "er": 0.36,
        "atr": 0.001,
        "atr_percentile": 65,
        "bb_width_percentile": 60,
        "ema_slope": 0.25,
        "spread_percentile": 25,
        "distance_from_ema20_atr": 1.2,
        "news_flag": 0,
        "session": "London",
        "candle_range_atr": 1.2,
        "prev_swing_high": 1.25,
        "prev_swing_low": 1.14,
    }
    result = detect_regime(row)
    assert result["regime_id"] == "R44"
    assert result["direction"] == "long"


def test_detect_r50_execution_cost_sensitive_market():
    row = {
        "symbol": "EURUSD",
        "open": 1.10,
        "high": 1.101,
        "low": 1.0995,
        "close": 1.1005,
        "htf_bias": "neutral",
        "ltf_bias": "neutral",
        "adx": 16,
        "plus_di": 18,
        "minus_di": 17,
        "er": 0.22,
        "atr": 0.001,
        "atr_percentile": 35,
        "bb_width_percentile": 50,
        "ema_slope": 0.0,
        "spread_percentile": 75,
        "distance_from_ema20_atr": 0.2,
        "news_flag": 0,
        "session": "Asia",
        "candle_range_atr": 0.7,
        "prev_swing_high": 1.12,
        "prev_swing_low": 1.09,
    }
    result = detect_regime(row)
    assert result["regime_id"] == "R50"
    assert result["is_active"] is True
