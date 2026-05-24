# Regime System

The Regime System converts cleaned market data into a `regime_id` such as `Q1_M04`.

Regime detection happens before strategy routing so the platform does not evaluate trend strategies in range markets, range strategies in trend markets, or any strategy during no-trade conditions.

- `service.py` owns formulas and classification logic.
- `backend.py` exposes clean operations to the orchestrator and UI.
- `schemas.py` owns typed contracts.
- `ui.py` renders pages and JSON only.

Implemented formulas use only past/current completed rows: true range, ATR, ATR percent, volatility percentile, trend efficiency, simplified ADX, spread percentile, jump z-score, compression percentile, candle wick/body ratios, session label, and liquidity sweep flags.

This system does not own strategy formulas, position sizing, execution, or broker connectivity.

