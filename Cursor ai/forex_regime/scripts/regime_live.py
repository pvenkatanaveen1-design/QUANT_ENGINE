#!/usr/bin/env python3
"""Print latest bar regime from MT5 (same logic as mql5/ForexRegime.mq5)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex_regime.config import RegimeParams  # noqa: E402
from forex_regime.mt5_setup import (  # noqa: E402
    initialize_mt5,
    rates_to_dataframe,
    shutdown_mt5,
    timeframe_from_minutes,
)
from forex_regime.regime import add_regime_columns  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Live regime snapshot from MT5")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--bars", type=int, default=300)
    ap.add_argument("--tf-minutes", type=int, default=60)
    ap.add_argument("--ema-fast", type=int, default=12)
    ap.add_argument("--ema-slow", type=int, default=26)
    ap.add_argument("--atr-period", type=int, default=14)
    ap.add_argument("--trend-atr-mult", type=float, default=0.35)
    ap.add_argument("--range-atr-mult", type=float, default=0.15)
    args = ap.parse_args()

    rp = RegimeParams(
        ema_fast=args.ema_fast,
        ema_slow=args.ema_slow,
        atr_period=args.atr_period,
        trend_atr_mult=args.trend_atr_mult,
        range_atr_mult=args.range_atr_mult,
    )

    mt5 = None
    try:
        mt5 = initialize_mt5(ROOT)
        sym = args.symbol
        if not mt5.symbol_select(sym, True):
            print(f"symbol_select failed for {sym!r}", file=sys.stderr)
            return 1
        tf = timeframe_from_minutes(mt5, args.tf_minutes)
        rates = mt5.copy_rates_from_pos(sym, tf, 0, args.bars)
        df = rates_to_dataframe(rates)
        if df.empty:
            print("No rates", file=sys.stderr)
            return 1
        out = add_regime_columns(df, rp).dropna()
        last = out.iloc[-1]
        n = (last["ema_spread"] / last["atr"]) if last["atr"] else float("nan")
        print(
            f"{sym} | {last['time']} | close={last['close']:.5f} | "
            f"regime={last['regime']} | n={n:.4f} "
            f"(match histogram + Comment on chart indicator)"
        )
        return 0
    except Exception as e:
        print(f"regime_live failed: {e}", file=sys.stderr)
        return 1
    finally:
        if mt5 is not None:
            shutdown_mt5(mt5)


if __name__ == "__main__":
    raise SystemExit(main())
