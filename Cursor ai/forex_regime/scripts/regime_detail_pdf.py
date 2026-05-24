#!/usr/bin/env python3
"""
Per-regime PDF report: yearly + monthly frequency charts, strategy table ranked by rank_score.

  One regime:
    python scripts/regime_detail_pdf.py --regime-id 7 --out reports/R07_detail.pdf

  All 52 (writes reports/by_regime/R01.pdf … R52.pdf, skipping empty if --skip-empty):
    python scripts/regime_detail_pdf.py --all --out-dir reports/by_regime
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
from forex_regime.regimes52.classify import Regime52Params  # noqa: E402
from forex_regime.regimes52.reporting.regime_pdf import write_regime_detail_pdf  # noqa: E402
from forex_regime.regimes52.strategies.runner import (  # noqa: E402
    build_scorecard_table,
    prepare_regime_and_signals,
)


def _tf_label(minutes: int) -> str:
    if minutes < 60:
        return f"M{minutes}"
    if minutes % 60 == 0:
        return f"H{minutes // 60}"
    return f"{minutes}m"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--tf-minutes", type=int, default=60)
    ap.add_argument("--bars", type=int, default=25_000)
    ap.add_argument("--regime-id", type=int, default=0, help="Single regime 1–52 (use with --out)")
    ap.add_argument("--out", default="", help="Output PDF path for single regime")
    ap.add_argument("--all", action="store_true", help="Write 52 PDFs under --out-dir")
    ap.add_argument("--out-dir", default=str(ROOT / "reports" / "by_regime"))
    ap.add_argument("--skip-empty", action="store_true", help="With --all: skip regimes with zero bars")
    ap.add_argument("--atr-sl-mult", type=float, default=1.5)
    ap.add_argument("--max-bars", type=int, default=40)
    args = ap.parse_args()

    mt5 = None
    try:
        mt5 = initialize_mt5(ROOT)
        if not mt5.symbol_select(args.symbol, True):
            print("symbol_select failed", file=sys.stderr)
            return 1
        tf = timeframe_from_minutes(mt5, args.tf_minutes)
        r52p = Regime52Params()
        raw = copy_rates_batched(mt5, args.symbol, tf, args.bars)
        df = rates_to_dataframe(raw).sort_values("time").reset_index(drop=True)
        if df.empty:
            print("No data", file=sys.stderr)
            return 1

        df = prepare_regime_and_signals(df, r52p)
        score = build_scorecard_table(df, p=r52p, atr_sl_mult=args.atr_sl_mult, max_bars=args.max_bars)
        tf_lab = _tf_label(args.tf_minutes)
        n_all = len(df)

        if args.all:
            out_dir = Path(args.out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            written = 0
            for rid in range(1, 53):
                sub = df["regime52_id"] == rid
                if args.skip_empty and sub.sum() == 0:
                    continue
                outp = out_dir / f"R{rid:02d}_regime_detail.pdf"
                write_regime_detail_pdf(
                    outp,
                    df=df,
                    scorecard=score,
                    regime_id=rid,
                    symbol=args.symbol,
                    tf_label=tf_lab,
                    total_bars=n_all,
                    p=r52p,
                    tf_minutes=args.tf_minutes,
                )
                written += 1
                print(f"Wrote {outp}")
            print(f"Done. PDFs written: {written}")
            return 0

        if args.regime_id < 1 or args.regime_id > 52:
            print("Set --regime-id 1..52 or use --all", file=sys.stderr)
            return 1
        outp = Path(args.out or ROOT / "reports" / f"R{args.regime_id:02d}_regime_detail.pdf")
        write_regime_detail_pdf(
            outp,
            df=df,
            scorecard=score,
            regime_id=args.regime_id,
            symbol=args.symbol,
            tf_label=tf_lab,
            total_bars=n_all,
            p=r52p,
            tf_minutes=args.tf_minutes,
        )
        print(f"Wrote {outp.resolve()}")
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
