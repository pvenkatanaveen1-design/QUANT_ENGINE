# quant_forex_V10

One-page Forex regime, strategy, pattern, and MT5 validation research console.

This project is a research and validation system. It is designed to classify market regimes, test strategy logic, inspect pattern confluence, prepare MT5 Strategy Tester runs, import MT5 reports, compare test models, and review candidates. It does not place live orders.

## What Is Implemented

- FastAPI backend with one-page browser UI.
- SQLite storage for candles, features, backtests, macro evidence, and MT5 report imports.
- R01-R50 regime reference, detection, UI cards, and strategy mapping.
- Feature engine for ADX, DI, ER, ATR, ATR percentile, Bollinger width, sessions, spread percentile, gap, VWAP, session VWAP, sweeps, trend weakening, MTF conflict, channel/range context, and data quality.
- Pattern engine switches for ICT, FVG, order blocks, BOS, MSS, liquidity pools, round numbers, VWAP, MVWAP, and session VWAP.
- Trade filters for killzone, spread, alpha score, sweeps, strict clean trend, trend weakening, ER/ADX clean trend gates, MTF conflict, news, rollover, and regime hysteresis.
- Mode presets: Discovery, Strict Validation, Final Approval.
- Local Python backtest, optimizer grid, out-of-sample, walk-forward, Monte Carlo, final approval gate, and local Ollama review with fallback rules.
- MT5 Strategy Tester config generation through `/api/mt5/tester/run`.
- Python signal CSV export for MT5 parity through `/api/backtest/{run_id}/mt5-parity-packet`.
- MT5 report import with trade-level R, initial risk, alpha score, pattern score, final score, and pattern detail columns when present.
- MT5 model comparison for 1-Min OHLC, Every Tick, and Every Tick Based On Real Ticks.
- Macro/news/cross-pair evidence layer using manual controls, pasted CSV/JSON, URL CSV/JSON, database mode, and saved-candle cross-pair evidence.

## What Is Not Implemented

- No live MT5 order placement, modify, close, copy-trading, or execution endpoints.
- `/api/mt5/backtest/run` is a bridge/config style response for UI/API testing, not full MT5 Strategy Tester automation.
- `/api/mt5/tester/run` can prepare tester files and optionally launch MT5, but final validation still depends on the MT5 terminal, compiled EA, tester environment, and imported reports.
- Real macro/news providers are not hardcoded. The app imports normalized CSV/JSON feeds that you provide.
- ICT, FVG, OB, BOS, MSS, liquidity pools, and VWAP logic are measurable OHLC/tick-volume research approximations, not true order-book or interbank flow.

## Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

For exact environment reproduction:

```powershell
pip install -r requirements.lock.txt
```

Copy `.env.example` to `.env` and fill MT5 details when needed:

```text
MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=
MT5_PATH=
```

Run the app:

```powershell
python run.py
```

Open:

```text
http://127.0.0.1:8000
```

API docs:

```text
http://127.0.0.1:8000/docs
```

If port 8000 is occupied:

```powershell
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8765
```

## Main Workflow

1. Select symbol, timeframe, date range, regime, strategy, risk, RR, and mode preset.
2. Use Macro Evidence Layer when testing R25-R29 or news-sensitive regimes.
3. Choose pattern filters and strict controls.
4. Fetch MT5 candles or use candles already saved in SQLite.
5. Calculate features and detect latest regime.
6. Run local Python backtest or optimizer.
7. Validate candidate with out-of-sample, walk-forward, Monte Carlo, and final approval.
8. Prepare MT5 Strategy Tester config and parity packet.
9. Run/import MT5 reports for 1-Min OHLC, Every Tick, and Real Ticks.
10. Compare model stability and review trade-level reasons, patterns, alpha, final score, and risk.

## Important Endpoints

Core:

- `GET /api/health`
- `POST /api/mt5/connect`
- `POST /api/candles/fetch`
- `GET /api/candles`
- `POST /api/features/calculate`
- `GET /api/features`
- `GET /api/features/cache-status`
- `POST /api/regime/detect-latest`
- `POST /api/backtest/run`

Research validation:

- `POST /api/optimizer/grid`
- `POST /api/out-of-sample/run`
- `POST /api/walk-forward/run`
- `POST /api/monte-carlo/run`
- `POST /api/final-approval/review`
- `POST /api/llm/review`

MT5 validation:

- `POST /api/mt5/backtest/run`
- `POST /api/mt5/tester/run`
- `GET /api/backtest/{run_id}/mt5-parity-packet`
- `POST /api/mt5/parity/check`
- `POST /api/mt5/parity/check-run-report`
- `POST /api/mt5/report/import`
- `POST /api/mt5/model-comparison/import`
- `POST /api/mt5/real-tick-workflow`
- `GET /api/mt5/report/imports`

Macro evidence:

- `POST /api/macro/evidence`
- `POST /api/macro/import-csv`
- `POST /api/macro/import-feed`
- `POST /api/macro/import-url`
- `POST /api/macro/cross-pair/import`
- `GET /api/macro/data`

Reference:

- `GET /api/reference/regimes`
- `GET /api/reference/strategies`
- `GET /api/reference/modifiers`
- `GET /api/reference/formulas`
- `GET /api/reference/market`
- `GET /api/reference/api-structure`

## Mode Presets

- Discovery: broader scan, score-only style controls, useful for finding candidates.
- Strict Validation: balanced filtering for realistic research, lower false-positive rate.
- Final Approval: funded-style hard filters, stricter spread, alpha, clean trend, and real-tick validation assumptions.

Do not jump directly from Discovery to live trading. A candidate must survive strict filtering, OOS, walk-forward, Monte Carlo, and MT5 real-tick comparison before demo or semi-manual review.

## MT5 Model Meaning

- Candle Close: rough exploratory testing only.
- 1-Min OHLC: fast research pass for many combinations.
- Every Tick: validation pass for execution sensitivity.
- Every Tick Based On Real Ticks: final approval pass, especially for scalping, tight SL, VWAP, spread-sensitive, or news-sensitive systems.

## Safety

This app is research-only. It has no live order execution API. Use results for research, review, demo validation, and semi-manual decision support only after independent risk controls.

Detailed usage guide: [docs/APP_USAGE.md](docs/APP_USAGE.md).
