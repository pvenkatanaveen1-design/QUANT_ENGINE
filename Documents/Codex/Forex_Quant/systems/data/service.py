from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from core.config_manager import ConfigManager
from core.models.market import DataQualityIssue, DataQualityReport
from core.time_utils import to_utc
from systems.data.schemas import CleanedDatasetInfo, DataLoadResult
from systems.mt5_gateway import backend as mt5_backend


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REQUIRED_COLUMNS = ["time", "open", "high", "low", "close", "tick_volume", "spread"]


def _load_config() -> dict[str, Any]:
    return ConfigManager(PROJECT_ROOT).load_yaml("systems/data/config.yaml")


def _issue(code: str, severity: str, message: str, count: int = 1) -> DataQualityIssue:
    return DataQualityIssue(code=code, severity=severity, message=message, count=count)


def _as_float(value: Any, column: str, row_number: int) -> float:
    if value in (None, ""):
        raise ValueError(f"missing {column} at row {row_number}")
    return float(value)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((percentile / 100.0) * (len(ordered) - 1)))
    return ordered[max(0, min(index, len(ordered) - 1))]


def _infer_expected_delta(times: list[datetime]) -> float | None:
    deltas = [
        (times[index] - times[index - 1]).total_seconds()
        for index in range(1, len(times))
        if times[index] > times[index - 1]
    ]
    if not deltas:
        return None
    counts = Counter(deltas)
    return counts.most_common(1)[0][0]


def _normalize_row(raw: dict[str, Any], row_number: int) -> dict[str, Any]:
    row = {str(key).strip().lower(): value for key, value in raw.items()}
    timestamp = to_utc(row["time"])
    clean = {
        "time": timestamp,
        "open": _as_float(row["open"], "open", row_number),
        "high": _as_float(row["high"], "high", row_number),
        "low": _as_float(row["low"], "low", row_number),
        "close": _as_float(row["close"], "close", row_number),
        "tick_volume": _as_float(row.get("tick_volume", 0), "tick_volume", row_number),
        "spread": _as_float(row.get("spread", 0), "spread", row_number),
    }
    return clean


def read_csv_rows(path: str | Path, required_columns: list[str] | None = None) -> tuple[list[dict[str, Any]], int, list[DataQualityIssue]]:
    required = required_columns or DEFAULT_REQUIRED_COLUMNS
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"CSV file not found: {source}")

    issues: list[DataQualityIssue] = []
    cleaned: list[dict[str, Any]] = []
    seen_exact: set[tuple[Any, ...]] = set()

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = [name.strip().lower() for name in reader.fieldnames or []]
        missing = [column for column in required if column not in fieldnames]
        if missing:
            raise ValueError(f"Missing required CSV columns: {', '.join(missing)}")

        rows_in = 0
        missing_count = 0
        invalid_ohlc = 0
        invalid_price = 0
        duplicate_exact = 0
        parse_errors = 0

        for row_number, raw in enumerate(reader, start=2):
            rows_in += 1
            normalized_keys = {str(key).strip().lower(): value for key, value in raw.items()}
            if any(normalized_keys.get(column) in (None, "") for column in required):
                missing_count += 1
                continue
            exact_key = tuple(normalized_keys.get(column) for column in required)
            if exact_key in seen_exact:
                duplicate_exact += 1
                continue
            seen_exact.add(exact_key)
            try:
                row = _normalize_row(normalized_keys, row_number)
            except (TypeError, ValueError):
                parse_errors += 1
                continue
            if row["high"] < row["low"]:
                invalid_ohlc += 1
                continue
            if any(row[column] <= 0 for column in ("open", "high", "low", "close")):
                invalid_price += 1
                continue
            cleaned.append(row)

    if missing_count:
        issues.append(_issue("missing_values", "warning", "Rows with missing values were removed.", missing_count))
    if duplicate_exact:
        issues.append(_issue("duplicate_exact_rows", "warning", "Exact duplicate rows were removed.", duplicate_exact))
    if parse_errors:
        issues.append(_issue("parse_errors", "warning", "Rows with invalid numeric/timestamp values were removed.", parse_errors))
    if invalid_ohlc:
        issues.append(_issue("invalid_ohlc", "warning", "Rows where high < low were removed.", invalid_ohlc))
    if invalid_price:
        issues.append(_issue("invalid_price", "warning", "Rows with non-positive OHLC prices were removed.", invalid_price))

    return cleaned, rows_in, issues


def build_quality_report(symbol: str, timeframe: str, rows: list[dict[str, Any]], rows_in: int, issues: list[DataQualityIssue]) -> DataQualityReport:
    rows.sort(key=lambda item: item["time"])
    times = [row["time"] for row in rows]
    duplicate_timestamps = len(times) - len(set(times))
    if duplicate_timestamps:
        issues.append(_issue("duplicate_timestamps", "warning", "Duplicate timestamps remain after exact duplicate removal.", duplicate_timestamps))

    spreads = [float(row["spread"]) for row in rows]
    spread_warning_level = _percentile(spreads, 90)
    abnormal_spreads = []
    if spreads and max(spreads) > min(spreads):
        abnormal_spreads = [spread for spread in spreads if spread_warning_level and spread >= spread_warning_level]
    if abnormal_spreads:
        issues.append(_issue("abnormal_spread", "warning", "Rows at or above the 90th spread percentile detected.", len(abnormal_spreads)))

    ranges = [row["high"] - row["low"] for row in rows]
    typical_range = median(ranges) if ranges else 0.0
    gaps = 0
    for index in range(1, len(rows)):
        if typical_range > 0 and abs(rows[index]["open"] - rows[index - 1]["close"]) > 3 * typical_range:
            gaps += 1
    if gaps:
        issues.append(_issue("large_price_gaps", "warning", "Large open-to-previous-close gaps detected.", gaps))

    expected_delta = _infer_expected_delta(times)
    missing_intervals = 0
    if expected_delta:
        for index in range(1, len(times)):
            delta = (times[index] - times[index - 1]).total_seconds()
            if delta > expected_delta * 1.5:
                missing_intervals += int(round(delta / expected_delta)) - 1
    if missing_intervals:
        issues.append(_issue("missing_intervals", "warning", "Missing bar intervals detected.", missing_intervals))

    if not rows:
        issues.append(_issue("empty_dataset", "critical", "No valid rows are available after cleaning."))

    metadata = {
        "spread_p90": spread_warning_level,
        "expected_interval_seconds": expected_delta,
        "first_time": times[0].isoformat() if times else None,
        "latest_time": times[-1].isoformat() if times else None,
    }
    return DataQualityReport(symbol=symbol, timeframe=timeframe, rows_in=rows_in, rows_out=len(rows), issues=issues, metadata=metadata)


def save_cleaned_csv(rows: list[dict[str, Any]], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DEFAULT_REQUIRED_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "time": row["time"].isoformat(),
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "tick_volume": row["tick_volume"],
                    "spread": row["spread"],
                }
            )


def save_report(report: DataQualityReport, report_path: str | Path) -> None:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": report.symbol,
        "timeframe": report.timeframe,
        "rows_in": report.rows_in,
        "rows_out": report.rows_out,
        "status": report.status,
        "issues": [issue.__dict__ for issue in report.issues],
        "metadata": report.metadata,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _clean_rows(
    raw_rows: list[dict[str, Any]],
    symbol: str,
    timeframe: str,
    source: str,
    source_metadata: dict[str, Any] | None = None,
) -> DataLoadResult:
    rows_in = len(raw_rows)
    issues: list[DataQualityIssue] = []
    cleaned: list[dict[str, Any]] = []
    seen_exact: set[tuple[Any, ...]] = set()
    missing_count = 0
    duplicate_exact = 0
    parse_errors = 0
    invalid_ohlc = 0
    invalid_price = 0

    for row_number, raw in enumerate(raw_rows, start=1):
        normalized_keys = {str(key).strip().lower(): value for key, value in raw.items()}
        if any(normalized_keys.get(column) in (None, "") for column in DEFAULT_REQUIRED_COLUMNS):
            missing_count += 1
            continue
        exact_key = tuple(normalized_keys.get(column) for column in DEFAULT_REQUIRED_COLUMNS)
        if exact_key in seen_exact:
            duplicate_exact += 1
            continue
        seen_exact.add(exact_key)
        try:
            row = _normalize_row(normalized_keys, row_number)
        except (TypeError, ValueError):
            parse_errors += 1
            continue
        if row["high"] < row["low"]:
            invalid_ohlc += 1
            continue
        if any(row[column] <= 0 for column in ("open", "high", "low", "close")):
            invalid_price += 1
            continue
        cleaned.append(row)

    if missing_count:
        issues.append(_issue("missing_values", "warning", "Rows with missing values were removed.", missing_count))
    if duplicate_exact:
        issues.append(_issue("duplicate_exact_rows", "warning", "Exact duplicate rows were removed.", duplicate_exact))
    if parse_errors:
        issues.append(_issue("parse_errors", "warning", "Rows with invalid numeric/timestamp values were removed.", parse_errors))
    if invalid_ohlc:
        issues.append(_issue("invalid_ohlc", "warning", "Rows where high < low were removed.", invalid_ohlc))
    if invalid_price:
        issues.append(_issue("invalid_price", "warning", "Rows with non-positive OHLC prices were removed.", invalid_price))

    report = build_quality_report(symbol, timeframe, cleaned, rows_in, issues)
    config = _load_config()
    minimum_rows = int(config.get("minimum_regime_rows", 120))
    latest_time = report.metadata.get("latest_time")
    if cleaned and latest_time:
        stale_minutes = float(config.get("stale_data_minutes", 60))
        latest_dt = to_utc(latest_time)
        age_minutes = (datetime.now(timezone.utc) - latest_dt).total_seconds() / 60.0
        report.metadata["latest_bar_age_minutes"] = round(age_minutes, 2)
        if age_minutes > stale_minutes:
            report.issues.append(_issue("stale_market_data", "warning", "Latest bar is older than the configured stale threshold. Market may be closed.", 1))
    report.metadata.update(
        {
            "source": source,
            "source_metadata": source_metadata or {},
            "safe_for_regime_testing": report.status != "critical" and report.rows_out >= minimum_rows,
        }
    )

    cleaned_dir = PROJECT_ROOT / config.get("cleaned_path", "data/cleaned")
    cleaned_path = cleaned_dir / f"{symbol}_{timeframe}_cleaned.csv"
    report_path = cleaned_dir / f"{symbol}_{timeframe}_quality.json"
    save_cleaned_csv(cleaned, cleaned_path)
    save_report(report, report_path)

    return DataLoadResult(
        symbol=symbol,
        timeframe=timeframe,
        source_path=source,
        cleaned_path=str(cleaned_path),
        report_path=str(report_path),
        rows_in=report.rows_in,
        rows_out=report.rows_out,
        quality_status=report.status,
        issues=report.issues,
        metadata=report.metadata,
    )


def clean_dataset(input_path: str | Path, symbol: str = "UNKNOWN", timeframe: str = "UNKNOWN") -> DataLoadResult:
    config = _load_config()
    rows, rows_in, issues = read_csv_rows(input_path, config.get("required_columns", DEFAULT_REQUIRED_COLUMNS))
    report = build_quality_report(symbol, timeframe, rows, rows_in, issues)

    cleaned_dir = PROJECT_ROOT / config.get("cleaned_path", "data/cleaned")
    cleaned_path = cleaned_dir / f"{symbol}_{timeframe}_cleaned.csv"
    report_path = cleaned_dir / f"{symbol}_{timeframe}_quality.json"
    save_cleaned_csv(rows, cleaned_path)
    save_report(report, report_path)

    return DataLoadResult(
        symbol=symbol,
        timeframe=timeframe,
        source_path=str(Path(input_path)),
        cleaned_path=str(cleaned_path),
        report_path=str(report_path),
        rows_in=report.rows_in,
        rows_out=report.rows_out,
        quality_status=report.status,
        issues=report.issues,
        metadata=report.metadata,
    )


def clean_market_rows(
    rows: list[dict[str, Any]],
    symbol: str,
    timeframe: str,
    source: str = "mt5_demo",
    source_metadata: dict[str, Any] | None = None,
) -> DataLoadResult:
    return _clean_rows(rows, symbol=symbol, timeframe=timeframe, source=source, source_metadata=source_metadata)


def fetch_mt5_dataset(symbol: str, timeframe: str, bars: int | None = None, save_cleaned: bool = True) -> DataLoadResult:
    config = _load_config()
    requested_bars = int(bars or config.get("default_bars", 672))
    rates = mt5_backend.get_rates(symbol=symbol, timeframe=timeframe, bars=requested_bars)
    result = _clean_rows(
        rates.get("rows", []),
        symbol=str(rates.get("metadata", {}).get("symbol") or symbol).upper(),
        timeframe=str(rates.get("metadata", {}).get("timeframe") or timeframe).upper(),
        source="mt5_demo",
        source_metadata=rates.get("metadata", {}),
    )
    if not save_cleaned:
        return result
    return result


def get_market_options() -> dict[str, Any]:
    config = _load_config()
    status = mt5_backend.get_status()
    symbols = mt5_backend.get_symbols()
    symbol_items = symbols.get("symbols", [])
    popular = [item for item in symbol_items if item.get("popular")]
    limit = int(config.get("ui_symbol_limit", 160))
    display_symbols = popular or symbol_items[:limit]
    return {
        "sources": config.get("source_options", []),
        "default_source": config.get("default_source", "mt5_demo"),
        "default_bars": int(config.get("default_bars", 672)),
        "mt5_status": status,
        "symbols": {**symbols, "symbols": display_symbols, "total_symbols": len(symbol_items)},
        "timeframes": mt5_backend.get_timeframes(),
    }


def get_latest_tick(symbol: str) -> dict[str, Any]:
    return mt5_backend.get_tick(symbol)


def load_cleaned_rows(symbol: str, timeframe: str) -> list[dict[str, Any]]:
    config = _load_config()
    path = PROJECT_ROOT / config.get("cleaned_path", "data/cleaned") / f"{symbol}_{timeframe}_cleaned.csv"
    rows, _, _ = read_csv_rows(path, DEFAULT_REQUIRED_COLUMNS)
    rows.sort(key=lambda item: item["time"])
    return rows


def list_cleaned_datasets() -> list[CleanedDatasetInfo]:
    config = _load_config()
    cleaned_dir = PROJECT_ROOT / config.get("cleaned_path", "data/cleaned")
    datasets: list[CleanedDatasetInfo] = []
    for path in sorted(cleaned_dir.glob("*_cleaned.csv")):
        stem = path.stem.removesuffix("_cleaned")
        if "_" in stem:
            symbol, timeframe = stem.split("_", 1)
        else:
            symbol, timeframe = stem, "UNKNOWN"
        rows, _, _ = read_csv_rows(path, DEFAULT_REQUIRED_COLUMNS)
        latest = max((row["time"] for row in rows), default=None)
        datasets.append(CleanedDatasetInfo(symbol=symbol, timeframe=timeframe, path=str(path), rows=len(rows), latest_time=latest.isoformat() if latest else None))
    return datasets
