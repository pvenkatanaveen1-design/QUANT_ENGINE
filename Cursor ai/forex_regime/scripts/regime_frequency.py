#!/usr/bin/env python3
"""
How often each regime appeared in MT5 history (counts + %), including per calendar year.

Usage:
  python scripts/regime_frequency.py --symbol EURUSD --tf-minutes 60 --bars 50000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex_regime.config import RegimeParams  # noqa: E402
from forex_regime.mt5_setup import (  # noqa: E402
    copy_rates_batched,
    initialize_mt5,
    rates_to_dataframe,
    shutdown_mt5,
    timeframe_from_minutes,
)
from forex_regime.regime import (  # noqa: E402
    REGIME_RANGE,
    REGIME_TREND_DOWN,
    REGIME_TREND_UP,
    add_regime_columns,
)

def _pct(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return 100.0 * count / total


def main() -> int:
    ap = argparse.ArgumentParser(description="Regime frequency over MT5 history (by year)")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--tf-minutes", type=int, default=60)
    ap.add_argument("--bars", type=int, default=50_000, help="Max bars to load (older = more past)")
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
        raw = copy_rates_batched(mt5, sym, tf, args.bars)
        df = rates_to_dataframe(raw)
        if df.empty:
            print("No rates returned — check symbol and history on server", file=sys.stderr)
            return 1

        # Oldest row is last in MT5 series? rates_to_dataframe preserves order from numpy.
        # copy_rates_from_pos: pos 0 is current; increasing pos goes into the past.
        # Concatenated order: first rows = newest ... need chronological order for clarity.
        df = df.sort_values("time").reset_index(drop=True)
        t0, t1 = df["time"].iloc[0], df["time"].iloc[-1]

        out = add_regime_columns(df, rp).dropna(subset=["regime", "atr"]).reset_index(drop=True)
        valid = len(out)
        if valid == 0:
            print("No rows after regime warmup (need more history)", file=sys.stderr)
            return 1

        print(
            f"{sym} | tf={args.tf_minutes}m | bars_loaded={len(df)} | bars_after_warmup={valid} | "
            f"range={t0} .. {t1} (UTC)"
        )
        print()

        order = [REGIME_TREND_UP, REGIME_RANGE, REGIME_TREND_DOWN]
        vc = out["regime"].value_counts()
        total = int(vc.sum())
        print("ALL (warmup window)")
        for label in order:
            c = int(vc.get(label, 0))
            print(f"  {label:12s}  {c:7d}  ({_pct(c, total):5.1f}%)")
        print(f"  {'TOTAL':12s}  {total:7d}")
        print()

        out["year"] = out["time"].dt.year
        years = sorted(out["year"].unique())
        print("BY YEAR (UTC calendar year of bar time)")
        for y in years:
            sub = out.loc[out["year"] == y, "regime"]
            vt = sub.value_counts()
            tot_y = int(len(sub))
            up = int(vt.get(REGIME_TREND_UP, 0))
            rg = int(vt.get(REGIME_RANGE, 0))
            dn = int(vt.get(REGIME_TREND_DOWN, 0))
            print(
                f"  {int(y):4d}  "
                f"TREND_UP {up:6d} ({_pct(up, tot_y):4.1f}%)  "
                f"RANGE {rg:6d} ({_pct(rg, tot_y):4.1f}%)  "
                f"TREND_DOWN {dn:6d} ({_pct(dn, tot_y):4.1f}%)  "
                f"TOTAL {tot_y:6d}"
            )

        return 0
    except Exception as e:
        print(f"regime_frequency failed: {e}", file=sys.stderr)
        return 1
    finally:
        if mt5 is not None:
            shutdown_mt5(mt5)


if __name__ == "__main__":
    raise SystemExit(main())
