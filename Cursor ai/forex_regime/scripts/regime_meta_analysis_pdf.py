#!/usr/bin/env python3
"""
Cross-timeframe meta-analysis: load MT5 history for several bar sizes, score all regime×strategy rows,
then build a PDF ranking best regimes and strategies across TFs (medians / modes — descriptive).

  python scripts/regime_meta_analysis_pdf.py --symbol EURUSD --bars 12000 ^
    --tf-list 15,30,60,120,240 --out reports/meta_regime_strategy.pdf

PowerShell line continuation: use backtick ` or separate arguments on one line.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

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
from forex_regime.regimes52.analysis.cross_tf import (  # noqa: E402
    best_strategy_per_regime_tf,
    regime_cross_tf_summary,
    strategy_pairs_cross_tf,
)
from forex_regime.regimes52.analysis.scoring import add_rank_columns  # noqa: E402
from forex_regime.regimes52.classify import Regime52Params  # noqa: E402
from forex_regime.regimes52.reporting.meta_analysis_pdf import write_meta_analysis_pdf  # noqa: E402
from forex_regime.regimes52.strategies.runner import (  # noqa: E402
    build_scorecard_table,
    prepare_regime_and_signals,
)


def _parse_tf_list(s: str) -> list[int]:
    out: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        v = int(part)
        if v <= 0:
            raise ValueError(f"Invalid tf minutes: {v}")
        out.append(v)
    if not out:
        raise ValueError("empty --tf-list")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-TF meta PDF for regime/strategy ranking")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--bars", type=int, default=12_000)
    ap.add_argument(
        "--tf-list",
        default="15,30,60,120,240",
        help="Comma-separated bar periods in minutes (e.g. 15,30,60,120,240)",
    )
    ap.add_argument("--min-trades", type=int, default=5, help="Per spec row, per TF")
    ap.add_argument("--atr-sl-mult", type=float, default=1.5)
    ap.add_argument("--max-bars", type=int, default=40)
    ap.add_argument("--out", default=str(ROOT / "reports" / "meta_regime_strategy.pdf"))
    ap.add_argument(
        "--csv",
        default="",
        help="Optional: also write long-form scorecard (all TFs) to this CSV path",
    )
    args = ap.parse_args()

    try:
        tf_list = _parse_tf_list(args.tf_list)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    r52p = Regime52Params()
    frames: list = []
    mt5 = None
    try:
        mt5 = initialize_mt5(ROOT)
        if not mt5.symbol_select(args.symbol, True):
            print("symbol_select failed", file=sys.stderr)
            return 1

        for tfm in tf_list:
            tf = timeframe_from_minutes(mt5, tfm)
            raw = copy_rates_batched(mt5, args.symbol, tf, args.bars)
            df = rates_to_dataframe(raw).sort_values("time").reset_index(drop=True)
            if df.empty:
                print(f"No data for tf={tfm}m", file=sys.stderr)
                continue
            df = prepare_regime_and_signals(df, r52p)
            tbl = build_scorecard_table(
                df,
                p=r52p,
                atr_sl_mult=args.atr_sl_mult,
                max_bars=args.max_bars,
            )
            tbl["tf_minutes"] = tfm
            frames.append(tbl)

        if not frames:
            print("No timeframe produced data", file=sys.stderr)
            return 1

        multi = add_rank_columns(pd.concat(frames, ignore_index=True))
        best_per_tf = best_strategy_per_regime_tf(multi, args.min_trades)
        regime_summary = regime_cross_tf_summary(best_per_tf)
        pairs_summary = strategy_pairs_cross_tf(multi, args.min_trades)

        outp = Path(args.out)
        write_meta_analysis_pdf(
            outp,
            multi=multi,
            best_per_tf=best_per_tf,
            regime_summary=regime_summary,
            pairs_summary=pairs_summary,
            symbol=args.symbol,
            bars=args.bars,
            tf_minutes_list=tf_list,
            min_trades=args.min_trades,
        )
        print(f"Wrote {outp.resolve()}")

        if args.csv:
            csvp = Path(args.csv)
            csvp.parent.mkdir(parents=True, exist_ok=True)
            multi.to_csv(csvp, index=False)
            print(f"Wrote long-form scorecard: {csvp.resolve()}")

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
