# quant_forex_V10 App Usage Guide

This guide describes the real app as implemented now. It is written for quantitative Forex research, semi-manual review, and MT5 Strategy Tester validation.

## System Picture

```text
MT5 candles / imported data
-> Feature engine
-> Regime detection R01-R50
-> Strategy eligibility
-> Pattern engine and modifiers
-> Alpha/final score
-> Python backtest
-> Optimizer/OOS/walk-forward/Monte Carlo
-> MT5 tester config and parity packet
-> MT5 report import and model comparison
-> Final approval review
```

The app is not an execution robot. It is a research console that tells you what regime/strategy/pattern combinations deserve more testing.

## Page Sections

### Research Controls

Use this section to set the main candidate:

- Mode Preset: Discovery, Strict Validation, or Final Approval.
- Symbol and timeframe.
- Date range.
- Regime filter: ALL or one regime like R01.
- Strategy filter: ALL or a strategy valid for the selected regime.
- Risk %, RR, investment, sentiment, USD bias, risk tone, and central-bank divergence.

Best practice:

- Use ALL/ALL in Discovery to find candidates.
- Use one regime and one strategy in Strict Validation.
- Use exact final settings in Final Approval.

### Macro Evidence Layer

This feeds R25-R29 and news-aware logic.

Modes:

- manual: use the manual bias dropdowns.
- evidence: use the fields typed into the page.
- database: use the latest imported macro_data row for the symbol/date.

Inputs:

- DXY % change and USD basket % change for broad USD regimes.
- US yield and Fed expectation changes for USD pressure.
- SPX, VIX, gold, JPY, CHF for risk-on/risk-off.
- Base/quote rate expectation BP for central-bank divergence.
- News timing and high-impact flag for news blocking.

Imports:

- Import Macro CSV: app-native CSV schema.
- Import Feed Text: normalized CSV or JSON feed text.
- Import URL Feed: normalized CSV or JSON feed URL.
- Build Cross-Pair Evidence: calculates USD basket, JPY/CHF safe-haven, and risk proxy from saved candles.

Practical usage:

- For R25/R26, use USD basket, DXY, yields, and Fed expectations.
- For R27/R28, use SPX/VIX/gold plus JPY/CHF.
- For R29, use base-vs-quote central-bank expectation change.
- For news regimes, use event impact and minutes_to_news/minutes_since_news.

### Pattern Engine

These are optional confluence switches:

- ICT
- FVG
- Order blocks
- BOS
- MSS
- Liquidity pools
- Round numbers
- VWAP
- MVWAP
- Session VWAP

Important:

- These are measurable OHLC/tick-volume approximations.
- They are not magic signals and not true interbank order flow.
- Use them as confirmation, scoring, or hard minimum filters depending on the selected mode.

Default research logic:

```text
pattern_score >= min_pattern_score
```

Use `score_only` for discovery and `minimum_required` or strict logic for validation.

### Strict Controls

Use these to keep regimes pure:

- Strict Regime Validation.
- Reject Trend Weakening.
- Reject Low ER.
- Reject ADX Outside Band.
- Reject MTF Conflict.
- Min Alpha Score.
- Max Spread Percentile.
- Killzone Mode.
- Spread Mode.

Recommended values:

```text
Discovery:
Min Alpha 5-6, Spread 70-80, score_only filters

Strict Validation:
Min Alpha 7, Spread 70, hard filters

Final Approval:
Min Alpha 8-9, Spread 65, hard filters, real-tick validation
```

Avoid making every filter maximum strict in the first run. That can create zero trades and no learning.

### Current Regime

Use Detect Latest after candles/features exist. If it shows WAITING:

- No candles are saved for the selected symbol/timeframe.
- Features have not been calculated.
- The selected date/symbol does not match saved data.
- MT5 connection/fetch did not complete.

Correct flow:

```text
Connect MT5
Fetch Candles
Calculate Features
Detect Latest
```

### Backtest Results

Review:

- Summary cards.
- Regime performance.
- Strategy performance.
- Pattern performance.
- Session/monthly performance.
- Combination performance.
- Skipped setup reasons.
- Trade list.
- Data health.

For a strategy to be interesting:

```text
Trades: enough for the timeframe and date range
PF: above 1.10 in research, above 1.20 preferred
Expectancy_R: positive
Drawdown: acceptable for funded constraints
Results stable across sessions/months
Pattern contribution is positive
```

### Optimizer

Use optimizer for permutation/combinations:

- Regimes.
- Strategies.
- Pattern switches.
- Min alpha score.
- Spread threshold.
- ER/ADX thresholds.
- Risk/RR values.
- Calibration profile values.

Good optimizer use:

```text
Start broad with small max combinations.
Keep only candidates with enough trades.
Validate survivors out-of-sample.
Do not approve optimizer-only winners.
```

### MT5 Tester And Real-Tick Workflow

Use MT5 validation after Python backtest finds a candidate.

Flow:

```text
Run Python backtest
Export parity packet
Prepare MT5 tester config
Run MT5 Strategy Tester
Import report
Compare Python vs MT5
Import 1-Min OHLC / Every Tick / Real Ticks reports
Review model comparison
```

Meaning of models:

- 1-Min OHLC: fast research validation.
- Every Tick: execution sensitivity check.
- Every Tick Based On Real Ticks: final validation.

Do not trust a tight-SL or scalping strategy until real-tick results are stable.

### Ollama Review

The local LLM reviewer can summarize:

- Backtest weakness.
- Insufficient data.
- Model comparison drift.
- Optimizer overfit risk.
- Walk-forward and Monte Carlo blockers.

It is a reviewer, not the trading authority. Final approval is still rule-based.

## Regime And Strategy Usage

### Trend Regimes

Use when:

- HTF and LTF align.
- ADX/ER support trend structure.
- Spread is normal.
- Price is not overextended.

Useful confirmations:

- Pullback to EMA20/EMA50.
- BOS in direction.
- VWAP reclaim.
- FVG retest in trend direction.

Avoid:

- Trend weakening.
- Low ER.
- ADX outside clean band if testing R01/R02.
- MTF conflict.
- High spread/off-session.

### Range And Sweep Regimes

Use when:

- ADX and ER are low.
- Price is near range high/low.
- Liquidity sweep and reclaim appears.

Useful confirmations:

- Equal highs/lows.
- Asia high/low.
- Round number rejection.
- VWAP mean reversion.

Avoid:

- Strong displacement against the fade.
- News shock.
- Spread stress.

### Breakout Regimes

Use when:

- Compression resolves into expansion.
- ATR percentile supports movement.
- Retest holds.

Useful confirmations:

- BOS.
- Displacement candle.
- FVG continuation.
- Session impulse.

Avoid:

- False breakout wick.
- Weak ER.
- Poor session.

### Macro Regimes R25-R29

Use only with evidence:

- Imported macro/feed row.
- Direct evidence mode.
- Cross-pair confirmation.

Manual bias alone is not enough for serious macro regime activation.

### Defensive Regimes

R09, R10, R23, R24, R30, R38, R39, R40, R50 should usually block or reduce trading.

R40 means data/manual review. Do not trade those rows.

## Semi-Manual Trading Answer

You can use the app for semi-manual trading research only after a candidate passes:

```text
Python backtest
Strict Validation mode
Out-of-sample
Walk-forward
Monte Carlo
MT5 model comparison
Real-tick validation
Manual chart review
Funded risk limits
```

The app can support trade selection, but it should not be used as a live execution authority.

## Common Failure Reasons

If win rate is low or many trades fail, inspect:

- Regime purity.
- Low ER.
- ADX outside band.
- MTF conflict.
- Trend weakening.
- High spread.
- Off-session execution.
- News/rollover.
- Pattern score too low.
- Same-candle SL/TP assumption.
- Difference between Python and MT5 real ticks.
- Too few trades.
- Optimizer overfit.

## Practical Approval Checklist

Minimum research gate:

```text
Trades >= 50
PF > 1.10
Expectancy_R > 0
No major data-quality issues
```

Preferred validation gate:

```text
Trades >= 100
PF >= 1.20
Positive OOS
Walk-forward pass rate >= 60%
Monte Carlo drawdown risk acceptable
Real-tick result positive
No large model drift
```

Funded-style behavior:

```text
Risk per trade: 0.25% to 0.50%
Max trades per day: 1-3
Avoid news/rollover
Prefer London, New York, Overlap
Stop after max loss streak
Only trade validated regimes/strategies
```

## Data Requirements

For better research:

- At least 6-12 months for intraday tests.
- More data for low-frequency strategies.
- Real spread/tick validation for scalping.
- Separate in-sample and out-of-sample periods.
- Cross-pair candles for macro/risk confirmation.
- News/calendar feed for event blocking.

## Developer Notes

Important modules:

- `backend/common/engines/feature_engine.py`: feature calculation.
- `backend/common/engines/regime_engine.py`: R01-R50 detection.
- `backend/common/engines/strategy_engine.py`: strategy signals.
- `backend/backtest_engine.py`: Python research backtest.
- `backend/pattern_engine.py`: pattern detection/scoring.
- `backend/optimizer_engine.py`: grid/permutation testing.
- `backend/mt5_tester_runner.py`: MT5 tester config/launch workflow.
- `backend/mt5_report_importer.py`: MT5 report import and model comparison.
- `backend/mt5_parity_packet.py`: Python signal export for MT5 parity.
- `backend/macro_data_engine.py`: macro/news/cross-pair evidence.
- `frontend/index.html` and `frontend/app.js`: one-page UI.

Always keep backend logic and UI wording aligned. If an API prepares config only, the UI must not imply that it already completed a true real-tick MT5 test.
