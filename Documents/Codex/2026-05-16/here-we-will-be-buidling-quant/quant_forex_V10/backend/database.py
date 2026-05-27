from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "forex_regime.db"
DEFAULT_DATA_SOURCE = "mt5_retail_candles"
DEFAULT_PROVIDER_NAME = "MT5 / SQLite"


def normalize_data_source(data_source: str | None = None) -> str:
    value = str(data_source or DEFAULT_DATA_SOURCE).strip().lower()
    aliases = {
        "mt5": DEFAULT_DATA_SOURCE,
        "sqlite": DEFAULT_DATA_SOURCE,
        "sqlite_mt5_candles": DEFAULT_DATA_SOURCE,
        "retail_broker_candles": DEFAULT_DATA_SOURCE,
    }
    return aliases.get(value, value or DEFAULT_DATA_SOURCE)


def storage_symbol(symbol: str, data_source: str | None = None) -> str:
    public = str(symbol or "").strip().upper()
    source = normalize_data_source(data_source)
    if source == DEFAULT_DATA_SOURCE:
        return public
    safe_source = "".join(ch if ch.isalnum() else "_" for ch in source.upper()).strip("_")
    return f"{public}__SRC__{safe_source}"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS candles (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                timeframe TEXT,
                timestamp TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                tick_volume REAL,
                spread REAL,
                real_volume REAL,
                display_symbol TEXT,
                data_source TEXT,
                provider TEXT,
                UNIQUE(symbol, timeframe, timestamp)
            );

            CREATE TABLE IF NOT EXISTS features (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                timeframe TEXT,
                timestamp TEXT,
                ema20 REAL,
                ema50 REAL,
                htf_ema50 REAL,
                adx REAL,
                plus_di REAL,
                minus_di REAL,
                er REAL,
                atr REAL,
                atr_percent REAL,
                atr_percentile REAL,
                bb_width REAL,
                bb_width_percentile REAL,
                ema_slope REAL,
                distance_from_ema20_atr REAL,
                distance_from_ema50_atr REAL,
                upper_wick_ratio REAL,
                lower_wick_ratio REAL,
                candle_range REAL,
                candle_range_atr REAL,
                prev_swing_high REAL,
                prev_swing_low REAL,
                prev_day_high REAL,
                prev_day_low REAL,
                range_midpoint REAL,
                spread_percentile REAL,
                session TEXT,
                htf_bias TEXT,
                ltf_bias TEXT,
                compression_flag INTEGER,
                volatility_expansion_flag INTEGER,
                sweep_high_flag INTEGER,
                sweep_low_flag INTEGER,
                news_flag INTEGER,
                sentiment TEXT,
                usd_bias TEXT,
                risk_sentiment TEXT,
                cb_divergence TEXT,
                previous_close REAL,
                gap_size REAL,
                gap_atr REAL,
                gap_flag INTEGER,
                gap_fill_percent REAL,
                gap_bars_ago REAL,
                adx_slope REAL,
                er_slope REAL,
                ema_slope_change REAL,
                trend_weakening INTEGER,
                mtf_conflict_score REAL,
                bull_pullback_failure INTEGER,
                bear_pullback_failure INTEGER,
                drift_strength REAL,
                channel_slope REAL,
                channel_mid REAL,
                channel_upper REAL,
                channel_lower REAL,
                channel_position REAL,
                near_channel_support INTEGER,
                near_channel_resistance INTEGER,
                near_range_high INTEGER,
                near_range_low INTEGER,
                false_upside_breakout INTEGER,
                false_downside_breakout INTEGER,
                opening_range_high REAL,
                opening_range_low REAL,
                opening_range_mid REAL,
                orb_up INTEGER,
                orb_down INTEGER,
                asia_high REAL,
                asia_low REAL,
                asia_midpoint REAL,
                chop_score REAL,
                dead_market_score REAL,
                is_month_end INTEGER,
                is_fixing_window INTEGER,
                overlap_trend INTEGER,
                asia_range INTEGER,
                session_vwap REAL,
                distance_from_vwap_atr REAL,
                vwap_extreme_high INTEGER,
                vwap_extreme_low INTEGER,
                spread_was_stressed INTEGER,
                spread_stress_bars_ago REAL,
                spread_now_normal INTEGER,
                post_stress_normalization INTEGER,
                missing_ohlc INTEGER,
                invalid_ohlc INTEGER,
                zero_range INTEGER,
                duplicate_timestamp INTEGER,
                spread_missing INTEGER,
                htf_unavailable INTEGER,
                feature_nan_required INTEGER,
                data_quality_warmup_flag INTEGER,
                data_quality_bad_data_flag INTEGER,
                data_quality_flag INTEGER,
                data_quality_category TEXT,
                data_quality_warmup_reasons TEXT,
                data_quality_bad_data_reasons TEXT,
                data_quality_reasons TEXT,
                display_symbol TEXT,
                data_source TEXT,
                provider TEXT,
                UNIQUE(symbol, timeframe, timestamp)
            );

            CREATE TABLE IF NOT EXISTS feature_cache (
                cache_key TEXT PRIMARY KEY,
                symbol TEXT,
                timeframe TEXT,
                start_date TEXT,
                end_date TEXT,
                data_source TEXT,
                provider TEXT,
                params_hash TEXT,
                candle_fingerprint TEXT,
                candle_count INTEGER,
                feature_count INTEGER,
                first_candle_time TEXT,
                last_candle_time TEXT,
                created_at TEXT,
                status TEXT,
                reason TEXT
            );

            CREATE TABLE IF NOT EXISTS backtest_runs (
                run_id TEXT PRIMARY KEY,
                symbol TEXT,
                timeframe TEXT,
                start_date TEXT,
                end_date TEXT,
                regime_filter TEXT,
                strategy_filter TEXT,
                risk_percent REAL,
                rr REAL,
                initial_equity REAL,
                created_at TEXT,
                summary_json TEXT,
                regime_performance_json TEXT,
                strategy_performance_json TEXT,
                combination_performance_json TEXT,
                unique_combination_performance_json TEXT,
                modifier_impact_json TEXT,
                session_performance_json TEXT,
                monthly_performance_json TEXT,
                pattern_performance_json TEXT,
                pattern_summary_json TEXT,
                mae_mfe_analysis_json TEXT,
                mt5_model_comparison_json TEXT,
                cost_summary_json TEXT,
                calibration_summary_json TEXT,
                spread_slippage_diagnostics_json TEXT,
                institutional_data_quality_json TEXT,
                data_health_json TEXT,
                feature_summary_json TEXT,
                regime_confidence_json TEXT,
                skipped_setups_json TEXT,
                equity_curve_json TEXT,
                drawdown_curve_json TEXT,
                approval_checklist_json TEXT,
                explanation_json TEXT
            );

            CREATE TABLE IF NOT EXISTS backtest_trades (
                id INTEGER PRIMARY KEY,
                run_id TEXT,
                symbol TEXT,
                timeframe TEXT,
                entry_time TEXT,
                exit_time TEXT,
                regime_id TEXT,
                regime_name TEXT,
                modifiers TEXT,
                strategy_id TEXT,
                strategy_name TEXT,
                direction TEXT,
                entry REAL,
                sl REAL,
                tp REAL,
                exit_price REAL,
                initial_risk REAL,
                mae_price REAL,
                mfe_price REAL,
                mae_r REAL,
                mfe_r REAL,
                mae_percent_of_stop REAL,
                mfe_to_mae_ratio REAL,
                max_adverse_price REAL,
                max_favorable_price REAL,
                bars_held INTEGER,
                stop_distance REAL,
                gross_result_r REAL,
                gross_profit REAL,
                total_cost_r REAL,
                cost_model TEXT,
                cost_breakdown TEXT,
                spread_at_entry REAL,
                spread_percentile REAL,
                estimated_slippage_r REAL,
                estimated_slippage_points REAL,
                result_r REAL,
                profit REAL,
                alpha_score REAL,
                alpha_components TEXT,
                alpha_reason TEXT,
                patterns_detected TEXT,
                pattern_score REAL,
                pattern_decision TEXT,
                pattern_summary TEXT,
                final_score REAL,
                setup_context TEXT,
                entry_reason TEXT,
                exit_reason TEXT,
                session TEXT
            );

            CREATE TABLE IF NOT EXISTS mt5_report_imports (
                import_id TEXT PRIMARY KEY,
                run_id TEXT,
                created_at TEXT,
                file_name TEXT,
                test_model TEXT,
                symbol TEXT,
                timeframe TEXT,
                start_date TEXT,
                end_date TEXT,
                initial_equity REAL,
                risk_percent REAL,
                raw_row_count INTEGER,
                summary_json TEXT,
                model_comparison_row_json TEXT,
                warnings_json TEXT
            );

            CREATE TABLE IF NOT EXISTS mt5_report_deals (
                id INTEGER PRIMARY KEY,
                import_id TEXT,
                time TEXT,
                symbol TEXT,
                deal_type TEXT,
                direction TEXT,
                volume REAL,
                price REAL,
                commission REAL,
                swap REAL,
                profit REAL,
                balance REAL,
                comment TEXT,
                raw_json TEXT
            );

            CREATE TABLE IF NOT EXISTS macro_data (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                symbol TEXT,
                scope TEXT,
                source TEXT,
                dxy_change_percent REAL,
                usd_basket_change_percent REAL,
                us_yield_change_bp REAL,
                fed_rate_expectation_change_bp REAL,
                spx_change_percent REAL,
                vix_change_percent REAL,
                gold_change_percent REAL,
                jpy_strength_score REAL,
                chf_strength_score REAL,
                base_rate_expectation_change_bp REAL,
                quote_rate_expectation_change_bp REAL,
                cb_divergence_bp REAL,
                high_impact_news INTEGER,
                minutes_to_news REAL,
                minutes_since_news REAL,
                event_currency TEXT,
                event_name TEXT,
                event_impact TEXT,
                notes TEXT,
                evidence_json TEXT,
                resolved_json TEXT,
                created_at TEXT,
                UNIQUE(timestamp, symbol, scope, source)
            );

            CREATE TABLE IF NOT EXISTS ab_experiments (
                experiment_id TEXT PRIMARY KEY,
                name TEXT,
                hypothesis TEXT,
                symbol TEXT,
                timeframe TEXT,
                start_date TEXT,
                end_date TEXT,
                regime_filter TEXT,
                strategy_filter TEXT,
                baseline_label TEXT,
                best_variant_label TEXT,
                status TEXT,
                created_at TEXT,
                request_json TEXT,
                summary_json TEXT,
                baseline_json TEXT,
                variants_json TEXT,
                comparison_json TEXT,
                warnings_json TEXT
            );

            CREATE TABLE IF NOT EXISTS validation_runs (
                validation_run_id TEXT PRIMARY KEY,
                validation_type TEXT,
                status TEXT,
                symbol TEXT,
                timeframe TEXT,
                start_date TEXT,
                end_date TEXT,
                regime_filter TEXT,
                strategy_filter TEXT,
                source_run_id TEXT,
                created_at TEXT,
                request_json TEXT,
                summary_json TEXT,
                result_json TEXT,
                warnings_json TEXT
            );

            CREATE TABLE IF NOT EXISTS favorites (
                item_type TEXT,
                item_id TEXT,
                is_favorite INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT,
                PRIMARY KEY (item_type, item_id)
            );
            """
        )
        for table, columns in {
            "backtest_runs": {
                "unique_combination_performance_json": "TEXT",
                "modifier_impact_json": "TEXT",
                "session_performance_json": "TEXT",
                "monthly_performance_json": "TEXT",
                "pattern_performance_json": "TEXT",
                "pattern_summary_json": "TEXT",
                "mae_mfe_analysis_json": "TEXT",
                "mt5_model_comparison_json": "TEXT",
                "cost_summary_json": "TEXT",
                "calibration_summary_json": "TEXT",
                "spread_slippage_diagnostics_json": "TEXT",
                "institutional_data_quality_json": "TEXT",
                "data_health_json": "TEXT",
                "feature_summary_json": "TEXT",
                "regime_confidence_json": "TEXT",
                "skipped_setups_json": "TEXT",
                "equity_curve_json": "TEXT",
                "drawdown_curve_json": "TEXT",
                "approval_checklist_json": "TEXT",
            },
            "backtest_trades": {
                "alpha_components": "TEXT",
                "alpha_reason": "TEXT",
                "patterns_detected": "TEXT",
                "pattern_score": "REAL",
                "pattern_decision": "TEXT",
                "pattern_summary": "TEXT",
                "final_score": "REAL",
                "gross_result_r": "REAL",
                "gross_profit": "REAL",
                "total_cost_r": "REAL",
                "cost_model": "TEXT",
                "cost_breakdown": "TEXT",
                "spread_at_entry": "REAL",
                "spread_percentile": "REAL",
                "estimated_slippage_r": "REAL",
                "estimated_slippage_points": "REAL",
                "session": "TEXT",
                "setup_context": "TEXT",
                "mae_price": "REAL",
                "mfe_price": "REAL",
                "mae_r": "REAL",
                "mfe_r": "REAL",
                "mae_percent_of_stop": "REAL",
                "mfe_to_mae_ratio": "REAL",
                "max_adverse_price": "REAL",
                "max_favorable_price": "REAL",
                "bars_held": "INTEGER",
                "stop_distance": "REAL",
            },
            "mt5_report_imports": {
                "warnings_json": "TEXT",
            },
            "macro_data": {
                "gold_change_percent": "REAL",
                "event_currency": "TEXT",
                "event_name": "TEXT",
                "event_impact": "TEXT",
                "notes": "TEXT",
                "evidence_json": "TEXT",
                "resolved_json": "TEXT",
                "created_at": "TEXT",
            },
            "features": {
                "display_symbol": "TEXT",
                "data_source": "TEXT",
                "provider": "TEXT",
                "usd_bias": "TEXT",
                "risk_sentiment": "TEXT",
                "cb_divergence": "TEXT",
                "macro_source": "TEXT",
                "macro_usd_confidence": "REAL",
                "macro_risk_confidence": "REAL",
                "macro_cb_confidence": "REAL",
                "macro_reasons": "TEXT",
                "previous_close": "REAL",
                "gap_size": "REAL",
                "gap_atr": "REAL",
                "gap_flag": "INTEGER",
                "gap_fill_percent": "REAL",
                "gap_bars_ago": "REAL",
                "adx_slope": "REAL",
                "er_slope": "REAL",
                "ema_slope_change": "REAL",
                "trend_weakening": "INTEGER",
                "mtf_conflict_score": "REAL",
                "bull_pullback_failure": "INTEGER",
                "bear_pullback_failure": "INTEGER",
                "drift_strength": "REAL",
                "channel_slope": "REAL",
                "channel_mid": "REAL",
                "channel_upper": "REAL",
                "channel_lower": "REAL",
                "channel_position": "REAL",
                "near_channel_support": "INTEGER",
                "near_channel_resistance": "INTEGER",
                "near_range_high": "INTEGER",
                "near_range_low": "INTEGER",
                "false_upside_breakout": "INTEGER",
                "false_downside_breakout": "INTEGER",
                "opening_range_high": "REAL",
                "opening_range_low": "REAL",
                "opening_range_mid": "REAL",
                "orb_up": "INTEGER",
                "orb_down": "INTEGER",
                "asia_high": "REAL",
                "asia_low": "REAL",
                "asia_midpoint": "REAL",
                "chop_score": "REAL",
                "dead_market_score": "REAL",
                "is_month_end": "INTEGER",
                "is_fixing_window": "INTEGER",
                "overlap_trend": "INTEGER",
                "asia_range": "INTEGER",
                "session_vwap": "REAL",
                "distance_from_vwap_atr": "REAL",
                "vwap_extreme_high": "INTEGER",
                "vwap_extreme_low": "INTEGER",
                "spread_was_stressed": "INTEGER",
                "spread_stress_bars_ago": "REAL",
                "spread_now_normal": "INTEGER",
                "post_stress_normalization": "INTEGER",
                "hurst_exponent": "REAL",
                "hurst_state": "TEXT",
                "fractal_dimension": "REAL",
                "fractal_dimension_state": "TEXT",
                "kalman_price": "REAL",
                "kalman_slope": "REAL",
                "kalman_trend_state": "TEXT",
                "garch_vol_forecast": "REAL",
                "garch_vol_percentile": "REAL",
                "garch_vol_state": "TEXT",
                "structural_break_score": "REAL",
                "structural_break_flag": "INTEGER",
                "structural_break_direction": "TEXT",
                "hmm_trend_probability": "REAL",
                "hmm_range_probability": "REAL",
                "hmm_stress_probability": "REAL",
                "hmm_state": "TEXT",
                "hmm_state_probability": "REAL",
                "stat_regime_vote": "TEXT",
                "stat_regime_confidence": "REAL",
                "stat_regime_direction": "TEXT",
                "stat_regime_disagreement": "INTEGER",
                "stat_regime_summary": "TEXT",
                "missing_ohlc": "INTEGER",
                "invalid_ohlc": "INTEGER",
                "zero_range": "INTEGER",
                "duplicate_timestamp": "INTEGER",
                "spread_missing": "INTEGER",
                "htf_unavailable": "INTEGER",
                "feature_nan_required": "INTEGER",
                "data_quality_warmup_flag": "INTEGER",
                "data_quality_bad_data_flag": "INTEGER",
                "data_quality_flag": "INTEGER",
                "data_quality_category": "TEXT",
                "data_quality_warmup_reasons": "TEXT",
                "data_quality_bad_data_reasons": "TEXT",
                "data_quality_reasons": "TEXT",
            },
            "candles": {
                "display_symbol": "TEXT",
                "data_source": "TEXT",
                "provider": "TEXT",
            },
            "feature_cache": {
                "data_source": "TEXT",
                "provider": "TEXT",
            },
        }.items():
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, sql_type in columns.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")


def save_macro_rows(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    columns = [
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
        "evidence_json",
        "resolved_json",
        "created_at",
    ]
    values = []
    for row in rows:
        values.append(tuple(row.get(col) for col in columns))
    placeholders = ",".join(["?"] * len(columns))
    update_clause = ",".join([f"{col}=excluded.{col}" for col in columns if col not in {"timestamp", "symbol", "scope", "source"}])
    with get_connection() as conn:
        conn.executemany(
            f"""
            INSERT INTO macro_data ({",".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(timestamp, symbol, scope, source)
            DO UPDATE SET {update_clause}
            """,
            values,
        )
    return len(values)


def load_macro_rows(
    symbol: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 250,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM macro_data WHERE 1=1"
    params: list[Any] = []
    if symbol:
        query += " AND (symbol = ? OR symbol = 'GLOBAL' OR symbol IS NULL OR symbol = '')"
        params.append(symbol.upper())
    if start_date:
        query += " AND timestamp >= ?"
        params.append(start_date)
    if end_date:
        query += " AND timestamp <= ?"
        params.append(end_date)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(max(1, min(int(limit or 250), 5000)))
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["evidence"] = json.loads(item.pop("evidence_json") or "{}")
        item["resolved"] = json.loads(item.pop("resolved_json") or "{}")
        result.append(item)
    return result


def load_latest_macro_row(symbol: str | None = None, as_of: str | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM macro_data WHERE 1=1"
    params: list[Any] = []
    if symbol:
        query += " AND (symbol = ? OR symbol = 'GLOBAL' OR symbol IS NULL OR symbol = '')"
        params.append(symbol.upper())
    if as_of:
        query += " AND timestamp <= ?"
        params.append(as_of)
    query += """
        ORDER BY
            CASE WHEN symbol = ? THEN 0 WHEN symbol = 'GLOBAL' THEN 1 ELSE 2 END,
            timestamp DESC
        LIMIT 1
    """
    params.append((symbol or "GLOBAL").upper())
    with get_connection() as conn:
        row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["evidence"] = json.loads(item.pop("evidence_json") or "{}")
    item["resolved"] = json.loads(item.pop("resolved_json") or "{}")
    return item


def save_candles(
    symbol: str,
    timeframe: str,
    candles: list[dict[str, Any]],
    data_source: str | None = None,
    provider: str | None = None,
) -> int:
    if not candles:
        return 0
    init_db()
    source = normalize_data_source(data_source)
    stored_symbol = storage_symbol(symbol, source)
    public_symbol = str(symbol or "").strip().upper()
    provider_name = str(provider or DEFAULT_PROVIDER_NAME).strip() or DEFAULT_PROVIDER_NAME
    rows = [
        (
            stored_symbol,
            timeframe,
            str(row["timestamp"]),
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
            float(row.get("tick_volume", 0) or 0),
            float(row.get("spread", 0) or 0),
            float(row.get("real_volume", 0) or 0),
            public_symbol,
            source,
            provider_name,
        )
        for row in candles
    ]
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO candles
            (symbol, timeframe, timestamp, open, high, low, close, tick_volume, spread, real_volume, display_symbol, data_source, provider)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def load_candles(
    symbol: str,
    timeframe: str,
    start_date: str | None = None,
    end_date: str | None = None,
    data_source: str | None = None,
) -> pd.DataFrame:
    source = normalize_data_source(data_source)
    stored_symbol = storage_symbol(symbol, source)
    query = "SELECT * FROM candles WHERE symbol = ? AND timeframe = ?"
    params: list[Any] = [stored_symbol, timeframe]
    if start_date:
        query += " AND timestamp >= ?"
        params.append(start_date)
    if end_date:
        query += " AND timestamp <= ?"
        params.append(end_date)
    query += " ORDER BY timestamp ASC"
    with get_connection() as conn:
        df = pd.read_sql_query(query, conn, params=params)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df["symbol"] = str(symbol or "").strip().upper()
        df["display_symbol"] = df.get("display_symbol").fillna(df["symbol"]) if "display_symbol" in df else df["symbol"]
        df["data_source"] = df.get("data_source").fillna(source) if "data_source" in df else source
        df["provider"] = df.get("provider").fillna(DEFAULT_PROVIDER_NAME) if "provider" in df else DEFAULT_PROVIDER_NAME
    return df


def load_features(
    symbol: str,
    timeframe: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = 250,
    data_source: str | None = None,
) -> pd.DataFrame:
    source = normalize_data_source(data_source)
    stored_symbol = storage_symbol(symbol, source)
    query = "SELECT * FROM features WHERE symbol = ? AND timeframe = ?"
    params: list[Any] = [stored_symbol, timeframe]
    if start_date:
        query += " AND timestamp >= ?"
        params.append(start_date)
    if end_date:
        query += " AND timestamp <= ?"
        params.append(end_date)
    query += " ORDER BY timestamp DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(max(1, min(int(limit or 250), 5000)))
    with get_connection() as conn:
        df = pd.read_sql_query(query, conn, params=params)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df["symbol"] = str(symbol or "").strip().upper()
        df["display_symbol"] = df.get("display_symbol").fillna(df["symbol"]) if "display_symbol" in df else df["symbol"]
        df["data_source"] = df.get("data_source").fillna(source) if "data_source" in df else source
        df["provider"] = df.get("provider").fillna(DEFAULT_PROVIDER_NAME) if "provider" in df else DEFAULT_PROVIDER_NAME
        df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def load_features_for_cache(symbol: str, timeframe: str, start_date: str, end_date: str, data_source: str | None = None) -> pd.DataFrame:
    return load_features(symbol, timeframe, start_date, end_date, limit=None, data_source=data_source)


def save_feature_cache_metadata(metadata: dict[str, Any]) -> None:
    columns = [
        "cache_key",
        "symbol",
        "timeframe",
        "start_date",
        "end_date",
        "data_source",
        "provider",
        "params_hash",
        "candle_fingerprint",
        "candle_count",
        "feature_count",
        "first_candle_time",
        "last_candle_time",
        "created_at",
        "status",
        "reason",
    ]
    with get_connection() as conn:
        conn.execute(
            f"""
            INSERT INTO feature_cache ({",".join(columns)})
            VALUES ({",".join(["?"] * len(columns))})
            ON CONFLICT(cache_key)
            DO UPDATE SET
                symbol=excluded.symbol,
                timeframe=excluded.timeframe,
                start_date=excluded.start_date,
                end_date=excluded.end_date,
                params_hash=excluded.params_hash,
                candle_fingerprint=excluded.candle_fingerprint,
                candle_count=excluded.candle_count,
                feature_count=excluded.feature_count,
                first_candle_time=excluded.first_candle_time,
                last_candle_time=excluded.last_candle_time,
                created_at=excluded.created_at,
                status=excluded.status,
                reason=excluded.reason
            """,
            tuple(metadata.get(col) for col in columns),
        )


def load_feature_cache_metadata(cache_key: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM feature_cache WHERE cache_key = ?", (cache_key,)).fetchone()
    return dict(row) if row else None


def save_features(
    symbol: str,
    timeframe: str,
    features: pd.DataFrame,
    data_source: str | None = None,
    provider: str | None = None,
) -> int:
    if features.empty:
        return 0
    init_db()
    source = normalize_data_source(data_source)
    stored_symbol = storage_symbol(symbol, source)
    public_symbol = str(symbol or "").strip().upper()
    provider_name = str(provider or DEFAULT_PROVIDER_NAME).strip() or DEFAULT_PROVIDER_NAME
    columns = [
        "ema20",
        "ema50",
        "htf_ema50",
        "adx",
        "plus_di",
        "minus_di",
        "er",
        "atr",
        "atr_percent",
        "atr_percentile",
        "bb_width",
        "bb_width_percentile",
        "ema_slope",
        "distance_from_ema20_atr",
        "distance_from_ema50_atr",
        "upper_wick_ratio",
        "lower_wick_ratio",
        "candle_range",
        "candle_range_atr",
        "prev_swing_high",
        "prev_swing_low",
        "prev_day_high",
        "prev_day_low",
        "range_midpoint",
        "spread_percentile",
        "session",
        "htf_bias",
        "ltf_bias",
        "compression_flag",
        "volatility_expansion_flag",
        "sweep_high_flag",
        "sweep_low_flag",
        "news_flag",
        "sentiment",
        "usd_bias",
        "risk_sentiment",
        "cb_divergence",
        "macro_source",
        "macro_usd_confidence",
        "macro_risk_confidence",
        "macro_cb_confidence",
        "macro_reasons",
        "previous_close",
        "gap_size",
        "gap_atr",
        "gap_flag",
        "gap_fill_percent",
        "gap_bars_ago",
        "adx_slope",
        "er_slope",
        "ema_slope_change",
        "trend_weakening",
        "mtf_conflict_score",
        "bull_pullback_failure",
        "bear_pullback_failure",
        "drift_strength",
        "channel_slope",
        "channel_mid",
        "channel_upper",
        "channel_lower",
        "channel_position",
        "near_channel_support",
        "near_channel_resistance",
        "near_range_high",
        "near_range_low",
        "false_upside_breakout",
        "false_downside_breakout",
        "opening_range_high",
        "opening_range_low",
        "opening_range_mid",
        "orb_up",
        "orb_down",
        "asia_high",
        "asia_low",
        "asia_midpoint",
        "chop_score",
        "dead_market_score",
        "is_month_end",
        "is_fixing_window",
        "overlap_trend",
        "asia_range",
        "session_vwap",
        "distance_from_vwap_atr",
        "vwap_extreme_high",
        "vwap_extreme_low",
        "spread_was_stressed",
        "spread_stress_bars_ago",
        "spread_now_normal",
        "post_stress_normalization",
        "hurst_exponent",
        "hurst_state",
        "fractal_dimension",
        "fractal_dimension_state",
        "kalman_price",
        "kalman_slope",
        "kalman_trend_state",
        "garch_vol_forecast",
        "garch_vol_percentile",
        "garch_vol_state",
        "structural_break_score",
        "structural_break_flag",
        "structural_break_direction",
        "hmm_trend_probability",
        "hmm_range_probability",
        "hmm_stress_probability",
        "hmm_state",
        "hmm_state_probability",
        "stat_regime_vote",
        "stat_regime_confidence",
        "stat_regime_direction",
        "stat_regime_disagreement",
        "stat_regime_summary",
        "missing_ohlc",
        "invalid_ohlc",
        "zero_range",
        "duplicate_timestamp",
        "spread_missing",
        "htf_unavailable",
        "feature_nan_required",
        "data_quality_warmup_flag",
        "data_quality_bad_data_flag",
        "data_quality_flag",
        "data_quality_category",
        "data_quality_warmup_reasons",
        "data_quality_bad_data_reasons",
        "data_quality_reasons",
    ]
    frame = features.reindex(columns=["timestamp", *columns]).copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).map(lambda value: value.isoformat())
    frame["display_symbol"] = public_symbol
    frame["data_source"] = source
    frame["provider"] = provider_name
    frame.insert(0, "timeframe", timeframe)
    frame.insert(0, "symbol", stored_symbol)
    rows = list(frame.itertuples(index=False, name=None))
    source_columns = ["display_symbol", "data_source", "provider"]
    placeholders = ",".join(["?"] * (3 + len(columns) + len(source_columns)))
    update_clause = ",".join([f"{col}=excluded.{col}" for col in [*columns, *source_columns]])
    with get_connection() as conn:
        conn.executemany(
            f"""
            INSERT INTO features
            (symbol, timeframe, timestamp, {",".join(columns)}, {",".join(source_columns)})
            VALUES ({placeholders})
            ON CONFLICT(symbol, timeframe, timestamp)
            DO UPDATE SET {update_clause}
            """,
            rows,
        )
    return len(rows)


def save_backtest_result(result: dict[str, Any]) -> None:
    init_db()
    run = result["request"]
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO backtest_runs
            (run_id, symbol, timeframe, start_date, end_date, regime_filter, strategy_filter,
             risk_percent, rr, initial_equity, created_at, summary_json, regime_performance_json,
             strategy_performance_json, combination_performance_json, unique_combination_performance_json,
             modifier_impact_json, session_performance_json, monthly_performance_json, pattern_performance_json,
             pattern_summary_json, mae_mfe_analysis_json, mt5_model_comparison_json, cost_summary_json, calibration_summary_json, spread_slippage_diagnostics_json, institutional_data_quality_json, data_health_json, feature_summary_json, regime_confidence_json, skipped_setups_json, equity_curve_json,
             drawdown_curve_json, approval_checklist_json, explanation_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["run_id"],
                run["symbol"],
                run["timeframe"],
                run["start_date"],
                run["end_date"],
                run["regime_filter"],
                run["strategy_filter"],
                run["risk_percent"],
                run["rr"],
                run["initial_equity"],
                result["created_at"],
                json.dumps(result["summary"]),
                json.dumps(result["regime_performance"]),
                json.dumps(result["strategy_performance"]),
                json.dumps(result["combination_performance"]),
                json.dumps(result.get("unique_combination_performance", [])),
                json.dumps(result.get("modifier_impact", [])),
                json.dumps(result.get("session_performance", [])),
                json.dumps(result.get("monthly_performance", [])),
                json.dumps(result.get("pattern_performance", [])),
                json.dumps(result.get("pattern_summary", {})),
                json.dumps(result.get("mae_mfe_analysis", {})),
                json.dumps(result.get("mt5_model_comparison", [])),
                json.dumps(result.get("cost_summary", {})),
                json.dumps(result.get("calibration_summary", {})),
                json.dumps(result.get("spread_slippage_diagnostics", {})),
                json.dumps(result.get("institutional_data_quality", {})),
                json.dumps(result.get("data_health", {})),
                json.dumps(result.get("feature_summary", {})),
                json.dumps(result.get("regime_confidence", [])),
                json.dumps(result.get("skipped_setups", [])),
                json.dumps(result.get("equity_curve", [])),
                json.dumps(result.get("drawdown_curve", [])),
                json.dumps(result.get("approval_checklist", [])),
                json.dumps(result["explanation"]),
            ),
        )
        conn.execute("DELETE FROM backtest_trades WHERE run_id = ?", (result["run_id"],))
        for trade in result["trades"]:
            conn.execute(
                """
                INSERT INTO backtest_trades
                (run_id, symbol, timeframe, entry_time, exit_time, regime_id, regime_name, modifiers,
                 strategy_id, strategy_name, direction, entry, sl, tp, exit_price, initial_risk,
                 mae_price, mfe_price, mae_r, mfe_r, mae_percent_of_stop, mfe_to_mae_ratio,
                 max_adverse_price, max_favorable_price, bars_held, stop_distance,
                 gross_result_r, gross_profit, total_cost_r, cost_model, cost_breakdown,
                 spread_at_entry, spread_percentile, estimated_slippage_r, estimated_slippage_points,
                 result_r, profit, alpha_score, alpha_components, alpha_reason, patterns_detected,
                 pattern_score, pattern_decision, pattern_summary, final_score, setup_context, entry_reason, exit_reason, session)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result["run_id"],
                    trade["symbol"],
                    trade["timeframe"],
                    trade["entry_time"],
                    trade["exit_time"],
                    trade["regime_id"],
                    trade["regime_name"],
                    json.dumps(trade["modifiers"]),
                    trade["strategy_id"],
                    trade["strategy_name"],
                    trade["direction"],
                    trade["entry"],
                    trade["sl"],
                    trade["tp"],
                    trade["exit_price"],
                    trade["initial_risk"],
                    trade.get("mae_price", 0),
                    trade.get("mfe_price", 0),
                    trade.get("mae_R", 0),
                    trade.get("mfe_R", 0),
                    trade.get("mae_percent_of_stop", 0),
                    trade.get("mfe_to_mae_ratio", 0),
                    trade.get("max_adverse_price", trade.get("entry", 0)),
                    trade.get("max_favorable_price", trade.get("entry", 0)),
                    trade.get("bars_held", 0),
                    trade.get("stop_distance", 0),
                    trade.get("gross_result_R", trade.get("result_R")),
                    trade.get("gross_profit", trade.get("profit")),
                    trade.get("total_cost_R", 0),
                    trade.get("cost_model", ""),
                    json.dumps(trade.get("cost_breakdown", {})),
                    trade.get("spread_at_entry", 0),
                    trade.get("spread_percentile", 0),
                    trade.get("estimated_slippage_R", 0),
                    trade.get("estimated_slippage_points", 0),
                    trade["result_R"],
                    trade["profit"],
                    trade["alpha_score"],
                    json.dumps(trade.get("alpha_components", {})),
                    trade.get("alpha_reason", ""),
                    json.dumps(trade.get("patterns_detected", [])),
                    trade.get("pattern_score", 0),
                    trade.get("pattern_decision", ""),
                    trade.get("pattern_summary", ""),
                    trade.get("final_score", trade.get("alpha_score", 0)),
                    json.dumps(trade.get("setup_context", {})),
                    trade["entry_reason"],
                    trade["exit_reason"],
                    trade.get("session", ""),
                ),
            )


def set_favorite(item_type: str, item_id: str, is_favorite: bool = True) -> dict[str, Any]:
    init_db()
    kind = str(item_type or "").strip().lower()
    ident = str(item_id or "").strip()
    if not kind or not ident:
        raise ValueError("item_type and item_id are required.")
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO favorites (item_type, item_id, is_favorite, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(item_type, item_id)
            DO UPDATE SET is_favorite = excluded.is_favorite, updated_at = excluded.updated_at
            """,
            (kind, ident, 1 if is_favorite else 0, now, now),
        )
    return {"item_type": kind, "item_id": ident, "is_favorite": bool(is_favorite), "updated_at": now}


def list_favorites(item_type: str | None = None) -> list[dict[str, Any]]:
    init_db()
    params: list[Any] = []
    where = "WHERE is_favorite = 1"
    if item_type:
        where += " AND item_type = ?"
        params.append(str(item_type).strip().lower())
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT item_type, item_id, is_favorite, created_at, updated_at
            FROM favorites
            {where}
            ORDER BY updated_at DESC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def list_backtest_runs(limit: int = 25) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 25), 200))
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT backtest_runs.run_id, backtest_runs.symbol, backtest_runs.timeframe, backtest_runs.start_date,
                   backtest_runs.end_date, backtest_runs.regime_filter, backtest_runs.strategy_filter,
                   backtest_runs.risk_percent, backtest_runs.rr, backtest_runs.initial_equity,
                   backtest_runs.created_at, summary_json, regime_confidence_json,
                   COALESCE(f.is_favorite, 0) AS is_favorite
            FROM backtest_runs
            LEFT JOIN favorites f ON f.item_type = 'backtest' AND f.item_id = backtest_runs.run_id AND f.is_favorite = 1
            ORDER BY is_favorite DESC, backtest_runs.created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    runs = []
    for row in rows:
        summary = json.loads(row["summary_json"] or "{}")
        regimes = json.loads(row["regime_confidence_json"] or "[]")
        item = dict(row)
        item.pop("summary_json", None)
        item.pop("regime_confidence_json", None)
        item.update(
            {
                "total_trades": summary.get("total_trades", 0),
                "win_rate": summary.get("win_rate", 0),
                "profit_factor": summary.get("profit_factor", 0),
                "expectancy_R": summary.get("expectancy_R", 0),
                "net_profit": summary.get("net_profit", 0),
                "ending_equity": summary.get("ending_equity", row["initial_equity"]),
                "skipped_setups": summary.get("skipped_setups", 0),
                "regimes_detected": len(regimes),
            }
        )
        runs.append(item)
    return runs


def load_backtest(run_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM backtest_runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    return {
        "run_id": row["run_id"],
        "request": {
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "regime_filter": row["regime_filter"],
            "strategy_filter": row["strategy_filter"],
            "risk_percent": row["risk_percent"],
            "rr": row["rr"],
            "initial_equity": row["initial_equity"],
        },
        "summary": json.loads(row["summary_json"]),
        "regime_performance": json.loads(row["regime_performance_json"]),
        "strategy_performance": json.loads(row["strategy_performance_json"]),
        "combination_performance": json.loads(row["combination_performance_json"]),
        "unique_combination_performance": json.loads(row["unique_combination_performance_json"] or "[]"),
        "modifier_impact": json.loads(row["modifier_impact_json"] or "[]"),
        "session_performance": json.loads(row["session_performance_json"] or "[]"),
        "monthly_performance": json.loads(row["monthly_performance_json"] or "[]"),
        "pattern_performance": json.loads(row["pattern_performance_json"] or "[]"),
        "pattern_summary": json.loads(row["pattern_summary_json"] or "{}"),
        "mae_mfe_analysis": json.loads(row["mae_mfe_analysis_json"] or "{}"),
        "mt5_model_comparison": json.loads(row["mt5_model_comparison_json"] or "[]"),
        "cost_summary": json.loads(row["cost_summary_json"] or "{}"),
        "calibration_summary": json.loads(row["calibration_summary_json"] or "{}"),
        "spread_slippage_diagnostics": json.loads(row["spread_slippage_diagnostics_json"] or "{}"),
        "institutional_data_quality": json.loads(row["institutional_data_quality_json"] or "{}"),
        "data_health": json.loads(row["data_health_json"] or "{}"),
        "feature_summary": json.loads(row["feature_summary_json"] or "{}"),
        "regime_confidence": json.loads(row["regime_confidence_json"] or "[]"),
        "skipped_setups": json.loads(row["skipped_setups_json"] or "[]"),
        "equity_curve": json.loads(row["equity_curve_json"] or "[]"),
        "drawdown_curve": json.loads(row["drawdown_curve_json"] or "[]"),
        "approval_checklist": json.loads(row["approval_checklist_json"] or "[]"),
        "explanation": json.loads(row["explanation_json"]),
    }


def load_backtest_trades(run_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM backtest_trades WHERE run_id = ? ORDER BY entry_time", (run_id,)).fetchall()
    trades = []
    for row in rows:
        item = dict(row)
        item["modifiers"] = json.loads(item["modifiers"] or "[]")
        item["alpha_components"] = json.loads(item.get("alpha_components") or "{}")
        item["patterns_detected"] = json.loads(item.get("patterns_detected") or "[]")
        item["pattern_score"] = item.get("pattern_score") or 0
        item["pattern_decision"] = item.get("pattern_decision") or ""
        item["pattern_summary"] = item.get("pattern_summary") or ""
        item["final_score"] = item.get("final_score") or item.get("alpha_score") or 0
        item["gross_result_R"] = item.pop("gross_result_r", item.get("result_r"))
        item["gross_profit"] = item.get("gross_profit", item.get("profit"))
        item["total_cost_R"] = item.pop("total_cost_r", 0) or 0
        item["cost_model"] = item.get("cost_model") or ""
        item["cost_breakdown"] = json.loads(item.get("cost_breakdown") or "{}")
        item["spread_at_entry"] = item.get("spread_at_entry") or 0
        item["spread_percentile"] = item.get("spread_percentile") or 0
        item["estimated_slippage_R"] = item.pop("estimated_slippage_r", 0) or 0
        item["estimated_slippage_points"] = item.get("estimated_slippage_points") or 0
        item["mae_R"] = item.pop("mae_r", 0) or 0
        item["mfe_R"] = item.pop("mfe_r", 0) or 0
        item["mae_price"] = item.get("mae_price") or 0
        item["mfe_price"] = item.get("mfe_price") or 0
        item["mae_percent_of_stop"] = item.get("mae_percent_of_stop") or 0
        item["mfe_to_mae_ratio"] = item.get("mfe_to_mae_ratio") or 0
        item["max_adverse_price"] = item.get("max_adverse_price") or item.get("entry") or 0
        item["max_favorable_price"] = item.get("max_favorable_price") or item.get("entry") or 0
        item["bars_held"] = item.get("bars_held") or 0
        item["stop_distance"] = item.get("stop_distance") or 0
        item["session"] = item.get("session") or ""
        item["setup_context"] = json.loads(item.get("setup_context") or "{}")
        item["result_R"] = item.pop("result_r")
        trades.append(item)
    return trades


def save_ab_experiment(result: dict[str, Any]) -> None:
    request = result.get("request", {})
    base = request.get("base_payload", {})
    summary = result.get("summary", {})
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO ab_experiments
            (experiment_id, name, hypothesis, symbol, timeframe, start_date, end_date, regime_filter,
             strategy_filter, baseline_label, best_variant_label, status, created_at, request_json,
             summary_json, baseline_json, variants_json, comparison_json, warnings_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["experiment_id"],
                request.get("name", "A/B Experiment"),
                request.get("hypothesis", ""),
                base.get("symbol"),
                base.get("timeframe"),
                base.get("start_date"),
                base.get("end_date"),
                base.get("regime_filter", "ALL"),
                base.get("strategy_filter", "ALL"),
                result.get("baseline", {}).get("label", "Baseline"),
                summary.get("best_variant_label"),
                summary.get("status", "UNKNOWN"),
                result.get("created_at"),
                json.dumps(request),
                json.dumps(summary),
                json.dumps(result.get("baseline", {})),
                json.dumps(result.get("variants", [])),
                json.dumps(result.get("comparison", [])),
                json.dumps(result.get("warnings", [])),
            ),
        )


def list_ab_experiments(limit: int = 25) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 25), 200))
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ab_experiments.experiment_id, ab_experiments.name, ab_experiments.hypothesis,
                   ab_experiments.symbol, ab_experiments.timeframe, ab_experiments.start_date,
                   ab_experiments.end_date, ab_experiments.regime_filter, ab_experiments.strategy_filter,
                   ab_experiments.baseline_label, ab_experiments.best_variant_label, ab_experiments.status,
                   ab_experiments.created_at, summary_json, COALESCE(f.is_favorite, 0) AS is_favorite
            FROM ab_experiments
            LEFT JOIN favorites f ON f.item_type = 'experiment' AND f.item_id = ab_experiments.experiment_id AND f.is_favorite = 1
            ORDER BY is_favorite DESC, ab_experiments.created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        summary = json.loads(item.pop("summary_json") or "{}")
        item.update(
            {
                "variants_tested": summary.get("variants_tested", 0),
                "accepted_variants": summary.get("accepted_variants", 0),
                "baseline_trades": summary.get("baseline_trades", 0),
                "best_delta_expectancy_R": summary.get("best_delta_expectancy_R", 0),
                "best_delta_profit_factor": summary.get("best_delta_profit_factor", 0),
            }
        )
        items.append(item)
    return items


def load_ab_experiment(experiment_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM ab_experiments WHERE experiment_id = ?", (experiment_id,)).fetchone()
    if row is None:
        return None
    return {
        "experiment_id": row["experiment_id"],
        "created_at": row["created_at"],
        "request": json.loads(row["request_json"] or "{}"),
        "summary": json.loads(row["summary_json"] or "{}"),
        "baseline": json.loads(row["baseline_json"] or "{}"),
        "variants": json.loads(row["variants_json"] or "[]"),
        "comparison": json.loads(row["comparison_json"] or "[]"),
        "warnings": json.loads(row["warnings_json"] or "[]"),
    }


def save_mt5_report_import(result: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO mt5_report_imports
            (import_id, run_id, created_at, file_name, test_model, symbol, timeframe, start_date, end_date,
             initial_equity, risk_percent, raw_row_count, summary_json, model_comparison_row_json, warnings_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["import_id"],
                result.get("run_id"),
                result["created_at"],
                result.get("file_name"),
                result.get("test_model"),
                result.get("symbol"),
                result.get("timeframe"),
                result.get("start_date"),
                result.get("end_date"),
                result.get("initial_equity"),
                result.get("risk_percent"),
                result.get("raw_row_count", 0),
                json.dumps(result.get("summary", {})),
                json.dumps(result.get("model_comparison_row", {})),
                json.dumps(result.get("warnings", [])),
            ),
        )
        conn.execute("DELETE FROM mt5_report_deals WHERE import_id = ?", (result["import_id"],))
        for deal in result.get("deals", []):
            conn.execute(
                """
                INSERT INTO mt5_report_deals
                (import_id, time, symbol, deal_type, direction, volume, price, commission, swap, profit, balance, comment, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result["import_id"],
                    deal.get("time"),
                    deal.get("symbol"),
                    deal.get("deal_type"),
                    deal.get("direction"),
                    deal.get("volume"),
                    deal.get("price"),
                    deal.get("commission"),
                    deal.get("swap"),
                    deal.get("profit"),
                    deal.get("balance"),
                    deal.get("comment"),
                    json.dumps(deal.get("raw", {})),
                ),
            )


def list_mt5_report_imports(limit: int = 25) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 25), 200))
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT mt5_report_imports.*, COALESCE(f.is_favorite, 0) AS is_favorite
            FROM mt5_report_imports
            LEFT JOIN favorites f ON f.item_type = 'mt5_report' AND f.item_id = mt5_report_imports.import_id AND f.is_favorite = 1
            ORDER BY is_favorite DESC, mt5_report_imports.created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["summary"] = json.loads(item.pop("summary_json") or "{}")
        item["model_comparison_row"] = json.loads(item.pop("model_comparison_row_json") or "{}")
        item["warnings"] = json.loads(item.pop("warnings_json") or "[]")
        items.append(item)
    return items


def load_mt5_report_import(import_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM mt5_report_imports WHERE import_id = ?", (import_id,)).fetchone()
        deal_rows = conn.execute("SELECT * FROM mt5_report_deals WHERE import_id = ? ORDER BY time", (import_id,)).fetchall()
    if row is None:
        return None
    item = dict(row)
    item["summary"] = json.loads(item.pop("summary_json") or "{}")
    item["model_comparison_row"] = json.loads(item.pop("model_comparison_row_json") or "{}")
    item["warnings"] = json.loads(item.pop("warnings_json") or "[]")
    deals = []
    for deal_row in deal_rows:
        deal = dict(deal_row)
        deal["raw"] = json.loads(deal.pop("raw_json") or "{}")
        deals.append(deal)
    item["deals"] = deals
    return item


def _validation_request(result: dict[str, Any], request: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(request, dict) and request:
        return request
    for key in ("request", "payload_received", "payload"):
        value = result.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _validation_summary(validation_type: str, result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    if summary:
        return summary
    if validation_type == "mt5_tester":
        bridge = result.get("bridge") if isinstance(result.get("bridge"), dict) else {}
        tester = bridge.get("mt5_strategy_tester") if isinstance(bridge.get("mt5_strategy_tester"), dict) else {}
        return {
            "status": result.get("status"),
            "order_execution": result.get("order_execution", False),
            "tester_status": tester.get("runner_layer_status") or result.get("status"),
            "terminal_path": result.get("terminal_path"),
            "report_found_path": result.get("report_found_path"),
        }
    if validation_type == "mt5_model_comparison":
        return {
            "status": result.get("status"),
            "symbol": result.get("symbol"),
            "timeframe": result.get("timeframe"),
            "missing_models": result.get("missing_models", []),
            "checks_passed": sum(1 for row in result.get("checks", []) if row.get("passed")),
            "checks_total": len(result.get("checks", [])),
        }
    return {"status": result.get("status", "UNKNOWN")}


def _validation_status(validation_type: str, result: dict[str, Any], summary: dict[str, Any]) -> str:
    status = summary.get("status") or result.get("status")
    if status:
        return str(status)
    if validation_type == "walk_forward":
        return "PASS" if summary.get("stable") else "FAIL"
    if validation_type == "out_of_sample":
        return "PASS" if summary.get("stable") else "WATCHLIST"
    return "UNKNOWN"


def save_validation_result(validation_type: str, result: dict[str, Any], request: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    req = _validation_request(result, request)
    if "payload" in req and isinstance(req.get("payload"), dict):
        base_req = req["payload"]
    else:
        base_req = req
    summary = _validation_summary(validation_type, result)
    warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
    validation_run_id = str(result.get("validation_run_id") or result.get("comparison_id") or result.get("run_id") or uuid.uuid4())
    created_at = str(result.get("created_at") or datetime.now(timezone.utc).isoformat())
    status = _validation_status(validation_type, result, summary)
    backtest = result.get("backtest") if isinstance(result.get("backtest"), dict) else {}
    source_run_id = result.get("run_id") or result.get("python_run_id") or backtest.get("run_id")
    row = {
        "validation_run_id": validation_run_id,
        "validation_type": validation_type,
        "status": status,
        "symbol": base_req.get("symbol"),
        "timeframe": base_req.get("timeframe"),
        "start_date": base_req.get("start_date"),
        "end_date": base_req.get("end_date"),
        "regime_filter": base_req.get("regime_filter", "ALL"),
        "strategy_filter": base_req.get("strategy_filter", "ALL"),
        "source_run_id": source_run_id,
        "created_at": created_at,
        "request": req,
        "summary": summary,
        "result": result,
        "warnings": warnings,
    }
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO validation_runs
            (validation_run_id, validation_type, status, symbol, timeframe, start_date, end_date,
             regime_filter, strategy_filter, source_run_id, created_at, request_json, summary_json,
             result_json, warnings_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["validation_run_id"],
                row["validation_type"],
                row["status"],
                row["symbol"],
                row["timeframe"],
                row["start_date"],
                row["end_date"],
                row["regime_filter"],
                row["strategy_filter"],
                row["source_run_id"],
                row["created_at"],
                json.dumps(row["request"]),
                json.dumps(row["summary"]),
                json.dumps(row["result"]),
                json.dumps(row["warnings"]),
            ),
        )
    result["validation_run_id"] = validation_run_id
    result["validation_saved"] = True
    return row


def list_validation_runs(limit: int = 25, validation_type: str | None = None) -> list[dict[str, Any]]:
    init_db()
    safe_limit = max(1, min(int(limit or 25), 200))
    params: list[Any] = []
    where = ""
    if validation_type:
        where = "WHERE validation_type = ?"
        params.append(validation_type)
    params.append(safe_limit)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT validation_runs.validation_run_id, validation_runs.validation_type, validation_runs.status,
                   validation_runs.symbol, validation_runs.timeframe, validation_runs.start_date, validation_runs.end_date,
                   validation_runs.regime_filter, validation_runs.strategy_filter, validation_runs.source_run_id,
                   validation_runs.created_at, summary_json, warnings_json,
                   COALESCE(f.is_favorite, 0) AS is_favorite
            FROM validation_runs
            LEFT JOIN favorites f ON f.item_type = 'validation' AND f.item_id = validation_runs.validation_run_id AND f.is_favorite = 1
            {where}
            ORDER BY is_favorite DESC, validation_runs.created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["summary"] = json.loads(item.pop("summary_json") or "{}")
        item["warnings"] = json.loads(item.pop("warnings_json") or "[]")
        items.append(item)
    return items


def load_validation_run(validation_run_id: str) -> dict[str, Any] | None:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM validation_runs WHERE validation_run_id = ?", (validation_run_id,)).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["request"] = json.loads(item.pop("request_json") or "{}")
    item["summary"] = json.loads(item.pop("summary_json") or "{}")
    item["result"] = json.loads(item.pop("result_json") or "{}")
    item["warnings"] = json.loads(item.pop("warnings_json") or "[]")
    return item
