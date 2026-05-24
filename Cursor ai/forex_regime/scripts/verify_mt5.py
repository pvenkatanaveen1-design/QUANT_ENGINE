#!/usr/bin/env python3
"""
Verify MT5 is reachable and market data flows.

Prerequisites:
  - MetaTrader 5 terminal installed and running (logged in).
  - Optional: `.env` in project root with MT5_LOGIN, MT5_PASSWORD, MT5_SERVER.

Usage (from `forex_regime` folder):
  python scripts/verify_mt5.py
  python scripts/verify_mt5.py --symbol GBPUSD
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python scripts/verify_mt5.py` without installing the package
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex_regime.mt5_setup import (  # noqa: E402
    initialize_mt5,
    rates_to_dataframe,
    shutdown_mt5,
    timeframe_from_minutes,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="MT5 connection and last-tick check")
    parser.add_argument("--symbol", default="EURUSD", help="Symbol as in MT5 Market Watch")
    parser.add_argument("--bars", type=int, default=20, help="Historical bars to pull (sanity check)")
    parser.add_argument("--tf-minutes", type=int, default=60, help="Timeframe in minutes (e.g. 60=H1)")
    args = parser.parse_args()

    mt5 = None
    try:
        mt5 = initialize_mt5(ROOT)
        ti = mt5.terminal_info()
        print(f"terminal connected | build={getattr(ti, 'build', None)} | path={getattr(ti, 'path', None)}")

        sym = args.symbol
        if not mt5.symbol_select(sym, True):
            print(f"symbol_select failed for {sym!r} | {mt5.last_error()}", file=sys.stderr)
            return 1

        si = mt5.symbol_info(sym)
        if si is None:
            print(f"symbol_info None for {sym}", file=sys.stderr)
            return 1

        tick = mt5.symbol_info_tick(sym)
        if tick is None:
            print(f"No tick yet for {sym} | {mt5.last_error()}", file=sys.stderr)
            return 1

        print(
            f"tick | bid={tick.bid} ask={tick.ask} | last={getattr(tick, 'last', None)} "
            f"| time={getattr(tick, 'time', None)}"
        )

        tf = timeframe_from_minutes(mt5, args.tf_minutes)
        rates = mt5.copy_rates_from_pos(sym, tf, 0, args.bars)
        df = rates_to_dataframe(rates)
        if df.empty:
            print("copy_rates returned no rows", file=sys.stderr)
            return 1

        print(f"history | rows={len(df)} | columns={list(df.columns)}")
        print(df.tail(3).to_string(index=False))
        print("OK - MT5 data path looks healthy.")
        return 0
    except Exception as e:
        print(f"verify_mt5 failed: {e}", file=sys.stderr)
        return 1
    finally:
        if mt5 is not None:
            shutdown_mt5(mt5)


if __name__ == "__main__":
    raise SystemExit(main())
