from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from systems.data import service
from systems.data.schemas import DataLoadResult


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_symbol_data(symbol: str, timeframe: str, source: str = "local_csv") -> DataLoadResult:
    if source != "local_csv":
        raise ValueError("Only local_csv source is supported in this phase.")
    input_path = PROJECT_ROOT / "data" / "raw" / f"{symbol}_{timeframe}.csv"
    return service.clean_dataset(input_path, symbol=symbol, timeframe=timeframe)


def clean_dataset(input_path: str, symbol: str = "UNKNOWN", timeframe: str = "UNKNOWN") -> DataLoadResult:
    return service.clean_dataset(input_path, symbol=symbol, timeframe=timeframe)


def load_csv(symbol: str, timeframe: str, input_path: str | None = None, source: str = "local_csv") -> DataLoadResult:
    if input_path:
        return clean_dataset(input_path, symbol=symbol, timeframe=timeframe)
    return load_symbol_data(symbol, timeframe, source=source)


def get_dataset_status(symbol: str | None = None, timeframe: str | None = None) -> dict[str, Any]:
    datasets = service.list_cleaned_datasets()
    if symbol and timeframe:
        for dataset in datasets:
            if dataset.symbol == symbol and dataset.timeframe == timeframe:
                return dataset.__dict__
        return {"symbol": symbol, "timeframe": timeframe, "status": "missing"}
    return {"datasets": [dataset.__dict__ for dataset in datasets], "count": len(datasets)}


def get_data_config() -> dict[str, Any]:
    return service._load_config()


def get_quality_report(symbol: str, timeframe: str) -> dict[str, Any]:
    path = PROJECT_ROOT / "data" / "cleaned" / f"{symbol}_{timeframe}_quality.json"
    if not path.exists():
        return {"symbol": symbol, "timeframe": timeframe, "status": "missing", "issues": []}
    return json.loads(path.read_text(encoding="utf-8"))
