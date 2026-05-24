from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def load_dotenv_optional(project_root: Path | None = None) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = project_root or Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")


def initialize_mt5(project_root: Path | None = None) -> Any:
    """
    Connect to the running MT5 terminal.

    If MT5_LOGIN / MT5_PASSWORD / MT5_SERVER are set in `.env`, uses them;
    otherwise relies on an already-logged-in terminal session.
    """
    import MetaTrader5 as mt5

    load_dotenv_optional(project_root)

    login_raw = os.getenv("MT5_LOGIN", "").strip()
    server = os.getenv("MT5_SERVER", "").strip()
    password = os.getenv("MT5_PASSWORD", "")

    login = int(login_raw) if login_raw else None

    if login is None:
        ok = mt5.initialize()
    else:
        ok = mt5.initialize(login=login, password=password, server=server)

    if not ok:
        raise RuntimeError(f"mt5.initialize() failed: {mt5.last_error()}")
    if mt5.terminal_info() is None:
        mt5.shutdown()
        raise RuntimeError("terminal_info() is None after initialize()")

    return mt5


def shutdown_mt5(mt5_module: Any) -> None:
    try:
        mt5_module.shutdown()
    except Exception:
        pass


def timeframe_from_minutes(mt5: Any, minutes: int) -> int:
    m = int(minutes)
    # String names so missing constants fail with a clear build error.
    names: dict[int, str] = {
        1: "TIMEFRAME_M1",
        2: "TIMEFRAME_M2",
        5: "TIMEFRAME_M5",
        10: "TIMEFRAME_M10",
        15: "TIMEFRAME_M15",
        30: "TIMEFRAME_M30",
        60: "TIMEFRAME_H1",
        120: "TIMEFRAME_H2",
        180: "TIMEFRAME_H3",
        240: "TIMEFRAME_H4",
        1440: "TIMEFRAME_D1",
    }
    if m not in names:
        raise ValueError(f"Unsupported timeframe_minutes={minutes}; use one of {sorted(names)}")
    c = getattr(mt5, names[m], None)
    if c is None:
        raise ValueError(
            f"MT5 build has no {names[m]}; update MetaTrader 5 / MetaTrader5 package for sub-hour frames."
        )
    return int(c)


_DEFAULT_CHUNK = 90_000


def copy_rates_batched(mt5: Any, symbol: str, tf: int, max_bars: int, chunk_size: int = _DEFAULT_CHUNK):
    """
    Concatenate copy_rates_from_pos slices (newest-first order from MT5) into one structured array.
    """
    parts: list = []
    start = 0
    remaining = int(max_bars)
    while remaining > 0:
        take = min(int(chunk_size), remaining)
        rates = mt5.copy_rates_from_pos(symbol, tf, start, take)
        if rates is None or len(rates) == 0:
            break
        parts.append(rates)
        got = len(rates)
        start += got
        remaining -= got
        if got < take:
            break
    if not parts:
        return None
    return np.concatenate(parts)


def rates_to_dataframe(rates) -> pd.DataFrame:
    """Convert MT5 copy_rates_* numpy structured array to DataFrame."""
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    # time is UNIX seconds
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df
