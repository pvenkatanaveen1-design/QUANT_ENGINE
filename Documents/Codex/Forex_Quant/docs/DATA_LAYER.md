# Data Layer

The platform starts with data quality because every regime, signal, and risk decision inherits its mistakes.

Required local CSV columns:

```text
time, open, high, low, close, tick_volume, spread
```

Cleaning steps:

- Normalize column names to lowercase.
- Parse timestamps into UTC.
- Sort rows by time.
- Remove exact duplicate rows.
- Remove rows with missing values.
- Remove invalid OHLC rows where `high < low`.
- Remove rows with non-positive prices.
- Flag duplicate timestamps.
- Flag abnormal spread at the 90th percentile.
- Flag large price gaps using a median-range proxy.
- Flag missing intervals from the dominant bar spacing.

Cleaned files are written to `data/cleaned`. Quality reports are saved beside them as JSON.

