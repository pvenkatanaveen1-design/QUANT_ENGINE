#!/usr/bin/env python3
"""
Regime × strategy scorecard: when `regime52_id` matches, evaluate each of 4 strategies per regime.
Reports bar counts per regime and win-rates for max excursion >= 1R..4R (ATR stop).

  python scripts/regime_strategy_scorecard.py --symbol EURUSD --tf-minutes 60 --bars 15000
"""

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
from forex_regime.regimes52.strategies.runner import (  # noqa: E402
    build_scorecard_table,
    prepare_regime_and_signals,
    regime_bar_counts,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--tf-minutes", type=int, default=60)
    ap.add_argument("--bars", type=int, default=12_000)
    ap.add_argument("--atr-sl-mult", type=float, default=1.5)
    ap.add_argument("--max-bars", type=int, default=40, help="Forward horizon per trade")
    ap.add_argument("--out", default="", help="Optional CSV path")
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
        if df.empty:
            print("No data", file=sys.stderr)
            return 1

        df = prepare_regime_and_signals(df)
        freq = regime_bar_counts(df)
        print("=== Bars per regime (regime52_id) ===")
        print(freq.to_string())
        print()

        tbl = build_scorecard_table(
            df,
            atr_sl_mult=args.atr_sl_mult,
            max_bars=args.max_bars,
        )
        # Compact view: regimes with at least one trade
        hit = tbl[tbl["trades"] > 0].sort_values(["regime_id", "trades"], ascending=[True, False])
        print("=== Strategy scorecard (rows with trades > 0) ===")
        cols = [
            "regime_id",
            "strategy_key",
            "trades",
            "wr_1r",
            "wr_2r",
            "wr_3r",
            "wr_4r",
        ]
        print(hit[cols].head(60).to_string(index=False))
        if len(hit) > 60:
            print(f"... ({len(hit)} total rows with trades)")

        if args.out:
            tbl.to_csv(args.out, index=False)
            print(f"\nWrote full table: {args.out}")
        return 0
    except Exception as e:
        print(e, file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1
    finally:
        if mt5 is not None:
            shutdown_mt5(mt5)


if __name__ == "__main__":
    raise SystemExit(main())
