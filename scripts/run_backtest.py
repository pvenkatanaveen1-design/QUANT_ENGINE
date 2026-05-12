#!/usr/bin/env python3
"""
Fetch OHLC from MT5 and run a minimal regime-labeled backtest.

Usage (from `forex_regime` folder):
  pip install -r requirements.txt
  python scripts/run_backtest.py

Pass parameters to test thresholds:
  python scripts/run_backtest.py --symbol EURUSD --bars 8000 --tf-minutes 60 \\
    --ema-fast 12 --ema-slow 26 --trend-atr-mult 0.35 --range-atr-mult 0.15 \\
    --spread-points 15 --no-short
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex_regime.backtest import run_backtest_on_ohlc  # noqa: E402
from forex_regime.config import BacktestParams, RegimeParams  # noqa: E402
from forex_regime.mt5_setup import (  # noqa: E402
    initialize_mt5,
    rates_to_dataframe,
    shutdown_mt5,
    timeframe_from_minutes,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Regime + simple strategy backtest on MT5 history")
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--bars", type=int, default=5000)
    p.add_argument("--tf-minutes", type=int, default=60)
    p.add_argument("--ema-fast", type=int, default=12)
    p.add_argument("--ema-slow", type=int, default=26)
    p.add_argument("--atr-period", type=int, default=14)
    p.add_argument("--trend-atr-mult", type=float, default=0.35)
    p.add_argument("--range-atr-mult", type=float, default=0.15)
    p.add_argument("--spread-points", type=float, default=2.0)
    p.add_argument("--no-short", action="store_true", help="Only long / flat")
    args = p.parse_args()

    regime_params = RegimeParams(
        ema_fast=args.ema_fast,
        ema_slow=args.ema_slow,
        atr_period=args.atr_period,
        trend_atr_mult=args.trend_atr_mult,
        range_atr_mult=args.range_atr_mult,
    )
    backtest_params = BacktestParams(
        symbol=args.symbol,
        timeframe_minutes=args.tf_minutes,
        bars=args.bars,
        spread_points=args.spread_points,
        allow_short=not args.no_short,
    )

    mt5 = None
    try:
        mt5 = initialize_mt5(ROOT)
        sym = backtest_params.symbol
        if not mt5.symbol_select(sym, True):
            print(f"symbol_select failed for {sym!r} | {mt5.last_error()}", file=sys.stderr)
            return 1
        si = mt5.symbol_info(sym)
        if si is None:
            print(f"symbol_info None for {sym}", file=sys.stderr)
            return 1
        point = float(si.point)

        tf = timeframe_from_minutes(mt5, backtest_params.timeframe_minutes)
        rates = mt5.copy_rates_from_pos(sym, tf, 0, backtest_params.bars)
        df = rates_to_dataframe(rates)
        if df.empty:
            print("No rate data — check symbol and history on server", file=sys.stderr)
            return 1

        bars_per_year = (365.0 * 24.0 * 60.0) / float(backtest_params.timeframe_minutes)
        out, meta = run_backtest_on_ohlc(
            df,
            regime_params=regime_params,
            backtest_params=backtest_params,
            point_size=point,
            sharpe_bars_per_year=bars_per_year,
        )

        last = out.iloc[-1]
        print(f"symbol={sym} bars_used={meta.n_bars} point={point}")
        print(
            f"result | total_return={meta.total_return:.4f} max_dd={meta.max_drawdown:.4f} "
            f"sharpe~={meta.sharpe_approx:.4f} trades~={meta.trades}"
        )
        print(
            f"last bar | time={last.get('time')} close={last.get('close')} "
            f"regime={last.get('regime')} position={last.get('position')}"
        )
        regime_counts = out["regime"].value_counts().to_dict()
        print(f"regime mix | {regime_counts}")
        print("Backtest loop completed successfully.")
        return 0
    except Exception as e:
        print(f"run_backtest failed: {e}", file=sys.stderr)
        return 1
    finally:
        if mt5 is not None:
            shutdown_mt5(mt5)


if __name__ == "__main__":
    raise SystemExit(main())
