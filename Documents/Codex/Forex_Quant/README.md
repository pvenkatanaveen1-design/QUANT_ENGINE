# Quanta Forex Control Center

Quanta Forex Control Center is a local-first Forex quant research platform. It is designed to load broker/CSV market data, classify market regimes, route only regime-approved strategy candidates, and keep live trading disabled until backtests, forward demo checks, and funded-account rules approve it.

Current phase: foundation plus first end-to-end safety flow.

- Data system: CSV loading, cleaning, quality reports, cleaned output files.
- Regime system: Q1-Q4 base regimes plus M01-M13 modifiers.
- Strategy router: canonical 208 strategy names from the 52-regime blueprint.
- Risk layer: cost, funded-rule, kill-switch, and position-size checks.
- UI shell: FastAPI + Jinja + Tailwind CDN + HTMX CDN.
- Execution: intentionally disabled. MT5 is not connected in this phase.

## Install

Python 3.11+ is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If Python is installed but not on PATH, this workspace has been tested with `C:\Python312\python.exe`.

## Run Tests

```powershell
pytest
```

## Run Web UI

```powershell
.\scripts\run_web.ps1
```

Then open `http://127.0.0.1:8000`.

## Safety Defaults

Live trading is disabled in every config file. Strategy entries are name-only, not tested, and disabled by default. MT5 support is represented only by `config/broker.yaml.example`; real order sending is not implemented here.

## Data Input

Put local CSV files in `data/raw`. Required columns:

```text
time, open, high, low, close, tick_volume, spread
```

Expected naming for convenience:

```text
data/raw/EURUSD_M15.csv
```

The Data page can load a symbol/timeframe pair and write cleaned data to `data/cleaned`.
