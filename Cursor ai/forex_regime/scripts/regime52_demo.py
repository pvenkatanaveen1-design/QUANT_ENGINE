#!/usr/bin/env python3
"""Smoke test: MT5 OHLC -> regime52_id / name / quad value_counts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex_regime.mt5_setup import (  # noqa: E402
    copy_rates_batched,
    initialize_mt5,
    rates_to_dataframe,
    shutdown_mt5,
    timeframe_from_minutes,
)
from forex_regime.regimes52 import Regime52Params, add_regime52_columns  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--tf-minutes", type=int, default=60)
    ap.add_argument("--bars", type=int, default=8000)
    args = ap.parse_args()

    mt5 = None
    try:
        mt5 = initialize_mt5(ROOT)
        if not mt5.symbol_select(args.symbol, True):
            print("symbol_select failed", file=sys.stderr)
            return 1
        tf = timeframe_from_minutes(mt5, args.tf_minutes)
        raw = copy_rates_batched(mt5, args.symbol, tf, args.bars)
        df = rates_to_dataframe(raw).sort_values("time").reset_index(drop=True)
        out = add_regime52_columns(df, Regime52Params())
        print(out[["time", "close", "regime52_id", "regime52_name", "regime52_quad"]].tail(8).to_string(index=False))
        print()
        print("regime52_id counts (sample window):")
        print(out["regime52_id"].value_counts().sort_index().to_string())
        print()
        print("quadrant mix:")
        print(out["regime52_quad"].value_counts().to_string())
        return 0
    except Exception as e:
        print(e, file=sys.stderr)
        return 1
    finally:
        if mt5 is not None:
            shutdown_mt5(mt5)


if __name__ == "__main__":
    raise SystemExit(main())
