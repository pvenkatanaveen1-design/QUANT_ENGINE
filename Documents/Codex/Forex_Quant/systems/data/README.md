# Data System

The Data System owns local market data loading, validation, cleaning, quality reporting, and cleaned CSV output.

- `service.py` contains business logic.
- `backend.py` exposes clean operations for other systems.
- `ui.py` translates HTTP requests to backend calls and renders templates.

Accepted columns:

```text
time, open, high, low, close, tick_volume, spread
```

Quality checks include missing values, invalid OHLC rows, duplicate rows, duplicate timestamps, abnormal spread, large price gaps, missing intervals, and empty datasets.

This system does not detect regimes, evaluate strategies, calculate risk, or place orders.

