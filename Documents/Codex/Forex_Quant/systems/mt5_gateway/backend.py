from __future__ import annotations

from systems.mt5_gateway import service


def get_status() -> dict:
    return service.get_status()


def get_symbols() -> dict:
    return service.get_symbols()


def resolve_symbol(symbol: str) -> str:
    return service.resolve_symbol(symbol)


def get_timeframes() -> list[dict]:
    return service.get_timeframes()


def get_rates(symbol: str, timeframe: str, bars: int) -> dict:
    return service.get_rates(symbol=symbol, timeframe=timeframe, bars=bars)


def get_tick(symbol: str) -> dict:
    return service.get_tick(symbol=symbol)
