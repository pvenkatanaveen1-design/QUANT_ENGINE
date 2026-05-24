from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MT5Status(BaseModel):
    available: bool
    connected: bool
    terminal_info: dict[str, Any] | None = None
    account_info: dict[str, Any] | None = None
    server: str | None = None
    currency: str | None = None
    balance: float | None = None
    equity: float | None = None
    margin: float | None = None
    free_margin: float | None = None
    last_error: Any = None
    checked_at: str
    reason: str | None = None


class MT5Symbol(BaseModel):
    symbol: str
    description: str | None = None
    base_currency: str | None = None
    profit_currency: str | None = None
    margin_currency: str | None = None
    digits: int | None = None
    point: float | None = None
    trade_mode: int | str | None = None
    visible: bool | None = None
    spread: int | float | None = None
    selected: bool | None = None


class TimeframeOption(BaseModel):
    key: str
    label: str
    minutes: int
    mt5_constant_name: str


class RatesQuery(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=64)
    timeframe: str = Field("M15", min_length=1, max_length=8)
    bars: int = Field(500, ge=1)


class RateRow(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    tick_volume: int | float
    spread: int | float
    real_volume: int | float = 0


class RatesResult(BaseModel):
    metadata: dict[str, Any]
    rows: list[RateRow]


class TickResult(BaseModel):
    bid: float | None
    ask: float | None
    last: float | None
    spread_points: float | None
    spread_price: float | None
    time: str | None
    symbol: str
    source: str = "mt5"


class TickPayload(BaseModel):
    type: str = "tick"
    symbol: str
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    spread_points: float | None = None
    spread_price: float | None = None
    time: str | None = None
    mt5_connected: bool = False
    ok: bool = True
    error: str | None = None
