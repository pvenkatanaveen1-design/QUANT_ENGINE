from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.models.market import Candle, DataQualityIssue, DataQualityReport, Tick


@dataclass(frozen=True)
class DataLoadRequest:
    symbol: str
    timeframe: str
    source: str = "local_csv"
    input_path: str | None = None


@dataclass
class CleanedDatasetInfo:
    symbol: str
    timeframe: str
    path: str
    rows: int
    latest_time: str | None = None


@dataclass
class DataLoadResult:
    symbol: str
    timeframe: str
    source_path: str
    cleaned_path: str
    report_path: str
    rows_in: int
    rows_out: int
    quality_status: str
    issues: list[DataQualityIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "Candle",
    "Tick",
    "DataLoadRequest",
    "DataLoadResult",
    "DataQualityIssue",
    "DataQualityReport",
    "CleanedDatasetInfo",
]

