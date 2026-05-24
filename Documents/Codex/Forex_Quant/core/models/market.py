from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: float = 0.0
    spread: float = 0.0


@dataclass(frozen=True)
class Tick:
    time: datetime
    bid: float
    ask: float
    volume: float = 0.0


@dataclass
class MarketDataset:
    symbol: str
    timeframe: str
    candles: list[Candle] = field(default_factory=list)
    source: str = "local_csv"


@dataclass
class DataQualityIssue:
    code: str
    severity: str
    message: str
    count: int = 1


@dataclass
class DataQualityReport:
    symbol: str
    timeframe: str
    rows_in: int
    rows_out: int
    issues: list[DataQualityIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        if any(issue.severity == "critical" for issue in self.issues):
            return "critical"
        if self.issues:
            return "warning"
        return "ok"

