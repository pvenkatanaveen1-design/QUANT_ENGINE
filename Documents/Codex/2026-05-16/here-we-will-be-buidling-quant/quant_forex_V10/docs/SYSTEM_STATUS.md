# System Status

Last updated for the current local codebase.

## Working

- One-page UI loads from FastAPI.
- Health endpoint confirms research-only scope.
- MT5 read-only connection and symbol/candle fetch path.
- SQLite candle, feature, backtest, macro evidence, and MT5 report storage.
- Feature engine with cache support.
- R01-R50 regime reference and detection.
- Regime-specific strategy filtering in UI.
- Python local backtest.
- Pattern engine controls and output fields.
- Pattern performance table.
- Strict controls and mode presets.
- Optimizer grid.
- Portfolio research.
- Out-of-sample validation.
- Walk-forward validation.
- Monte Carlo validation.
- Final approval gate.
- Ollama review endpoint with deterministic fallback.
- MT5 tester config generation.
- Python parity packet export.
- MT5 report import.
- MT5 model comparison import.
- Real-tick workflow coordinator.
- Macro/news/cross-pair evidence import.
- Data-quality regime R40 and skipped setup reasons.

## Partial Or Environment-Dependent

- MT5 Strategy Tester automation requires:
  - Installed MT5 terminal.
  - Correct terminal path.
  - Compiled `QuantForexV10_ResearchEA.ex5`.
  - Tester permissions and broker history.
  - Imported reports for full validation.
- `/api/mt5/backtest/run` is a bridge/config response, not a complete tester run.
- `/api/mt5/tester/run` prepares and can launch MT5, but the terminal/report environment controls whether a report is produced.
- Pattern engine is OHLC/tick-volume based. It does not use true order book or institutional flow.
- Macro/news import is generic CSV/JSON. Provider-specific connectors are not bundled.
- Cross-pair evidence needs candles already saved for the selected pairs.

## Not Present By Design

- Live order execution.
- Account trade copying.
- Position close/modify endpoints.
- Guaranteed profitable strategy logic.
- Automatic funded-account challenge execution.

## Recommended Next Work

1. Add provider-specific macro/news connectors:
   - FRED or central-bank data for rates/yields.
   - Economic calendar import template.
   - DXY/risk proxy feed template.
2. Improve MT5 closed-loop automation:
   - Confirm generated tester INI files.
   - Compile/check EA version.
   - Watch report path and import automatically.
3. Expand parity diagnostics:
   - Per-trade mismatch visual table.
   - Signal missing in MT5.
   - Extra MT5 trade not in Python.
4. Add optimizer result explainability:
   - Which parameter changed the result.
   - Sensitivity heatmaps.
   - Overfit warning.
5. Add documentation screenshots after UI stabilizes.

## Approval Reality

A candidate is not approved just because local backtest is profitable.

Approval needs:

```text
Backtest positive
OOS positive
Walk-forward stable
Monte Carlo acceptable
MT5 1-Min OHLC positive
MT5 Every Tick positive
MT5 Real Ticks positive
Python/MT5 parity acceptable
Drawdown acceptable for account rules
Enough trades
```

Until then, status should remain:

```text
Research candidate
Watchlist
Manual review
```
