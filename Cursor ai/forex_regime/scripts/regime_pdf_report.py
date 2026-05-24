#!/usr/bin/env python3
"""
Build a PDF: for each timeframe (1,2,5,10,15,30,60,120,180,240 minutes),
count how often each operational regime occurred per calendar year (UTC).

Usage:
  pip install -r requirements.txt
  python scripts/regime_pdf_report.py --symbol EURUSD --max-bars 80000 --out reports/regimes.pdf

MT5 terminal must be running. Lower --max-bars for a quick test.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
from forex_regime.pdf_report import (  # noqa: E402
    sections_from_ohlc,
    write_regime_year_pdf,
)

DEFAULT_TFS = [1, 2, 5, 10, 15, 30, 60, 120, 180, 240]


def main() -> int:
    ap = argparse.ArgumentParser(description="PDF: regime counts per year for multiple MT5 timeframes")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument(
        "--timeframes",
        default=",".join(str(x) for x in DEFAULT_TFS),
        help="Comma-separated minutes, e.g. 1,2,5,10,15,30,60,120,180,240",
    )
    ap.add_argument("--max-bars", type=int, default=100_000, help="Max bars to fetch per timeframe")
    ap.add_argument("--out", default=str(ROOT / "reports" / "regime_yearly_by_timeframe.pdf"))
    ap.add_argument("--ema-fast", type=int, default=12)
    ap.add_argument("--ema-slow", type=int, default=26)
    ap.add_argument("--atr-period", type=int, default=14)
    ap.add_argument("--trend-atr-mult", type=float, default=0.35)
    ap.add_argument("--range-atr-mult", type=float, default=0.15)
    args = ap.parse_args()

    tfs = [int(x.strip()) for x in args.timeframes.split(",") if x.strip()]
    rp = RegimeParams(
        ema_fast=args.ema_fast,
        ema_slow=args.ema_slow,
        atr_period=args.atr_period,
        trend_atr_mult=args.trend_atr_mult,
        range_atr_mult=args.range_atr_mult,
    )
    out_path = Path(args.out)

    mt5 = None
    try:
        mt5 = initialize_mt5(ROOT)
        sym = args.symbol
        if not mt5.symbol_select(sym, True):
            print(f"symbol_select failed for {sym!r}", file=sys.stderr)
            return 1

        sections = []
        for minutes in tfs:
            try:
                tf = timeframe_from_minutes(mt5, minutes)
            except ValueError as e:
                print(f"Skip {minutes}m: {e}", file=sys.stderr)
                continue
            raw = copy_rates_batched(mt5, sym, tf, args.max_bars)
            df = rates_to_dataframe(raw)
            if df.empty:
                sections.append(sections_from_ohlc(minutes, args.max_bars, df, rp))
                continue
            df = df.sort_values("time").reset_index(drop=True)
            sections.append(sections_from_ohlc(minutes, args.max_bars, df, rp))
            s = sections[-1]
            print(
                f"OK {minutes}m | loaded={s.bars_loaded} valid={s.bars_after_warmup} | "
                f"{s.utc_first} .. {s.utc_last}"
            )

        write_regime_year_pdf(
            out_path,
            symbol=sym,
            regime_params=rp,
            sections=sections,
            title=f"{sym} — regime frequency by year and timeframe",
        )
        print(f"Wrote PDF: {out_path.resolve()}")
        return 0
    except Exception as e:
        print(f"regime_pdf_report failed: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1
    finally:
        if mt5 is not None:
            shutdown_mt5(mt5)


if __name__ == "__main__":
    raise SystemExit(main())
