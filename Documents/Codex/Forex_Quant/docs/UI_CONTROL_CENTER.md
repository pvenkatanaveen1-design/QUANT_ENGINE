# UI Control Center

The UI is a thin FastAPI/Jinja shell around the systems. It does not contain trading logic.

Pages:

- `/`: system monitor.
- `/data`: CSV loading and data quality.
- `/regimes`: latest regime and feature snapshot.
- `/strategies`: all 208 strategy names and selected regime candidates.
- `/backtester`: staged research page.
- `/risk`: risk and funded-rule visibility.
- `/decisions`: staged journal page.

Safety rules:

- Live trading is visibly disabled.
- MT5 is off.
- Strategy entries are disabled and not tested.
- Risk-rule editing is not enabled in this first build.
- Paper and live execution are separate later phases.

