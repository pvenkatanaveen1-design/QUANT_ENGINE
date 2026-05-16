# Dashboard implementation checklist (Steps 5–7)

Use this list to verify the Quant Cockpit dashboard stack end-to-end.

| Step | Task | Status | Location |
|------|------|--------|----------|
| 5 | `BacktestRun` SQLAlchemy model + SQLite helpers | Done | `core/models/backtest.py` |
| 5 | DB init on startup | Done | `app/main.py` (`init_backtest_db` in lifespan) |
| 5 | Dashboard API router | Done | `systems/regime/dashboard_api.py` — `GET /api/dashboard/current-regime`, `GET /api/dashboard/ranking`, `GET /api/dashboard/backtest-summary/{regime_id}`, `POST /api/dashboard/run-backtest/{regime_id}` |
| 5 | Regime ID list for ranking | Done | `config/regimes.py` (`regimes`) |
| 5 | Strategy helpers | Done | `systems/strategy_router/service.py` — `get_strategies_by_regime` |
| 5 | `get_current_regime` helper | Done | `systems/regime/service.py` |
| 6 | Reference panel (thresholds tree, modifiers, Section 5, formulas, citations) | Done | `systems/regime/templates/dashboard.html` + dynamic thresholds in `app/static/js/dashboard.js` |
| 7 | Failure counters on signal-engine `BacktestResult` | Done | `systems/research/service.py` — `institutional_trap_failures`, `sweep_failures`, `spread_rejections` |
| 7 | Persist extra metrics (optional DuckDB) | Done | `systems/analysis/db.py` — `save_signal_engine_backtest` / `WF_RUN_SUMMARY` payload |
| 7 | Dashboard page + Chart.js | Done | `systems/regime/templates/dashboard.html` |
| 7 | Client logic | Done | `app/static/js/dashboard.js` |
| 7 | Nav link | Done | `app/templates/base.html` → `/dashboard` |
| 7 | Route registration | Done | `systems/regime/ui.py` — `GET /dashboard` |
| 7 | Main app includes dashboard API | Done | `app/main.py` — `dashboard_router` |

## Manual test

1. Start the FastAPI app (e.g. `uvicorn app.main:app --reload`).
2. Open `http://localhost:8000/dashboard` (adjust host/port).
3. Expand **Reference: Key Thresholds & Formulas** and confirm the regime tree / modifier list and loaded YAML thresholds appear.
4. Click **Refresh All** — banner and ranking should load (data requires cleaned MT5 CSVs where applicable).
5. Optional: **Run All Missing Backtests** — confirms SQLite `BacktestRun` rows populate (may take a long time; uses MT5 path).

## Dependencies

- `SQLAlchemy` in `requirements.txt`
- SQLite file (default): `data/analysis/backtest_runs_sa.sqlite`
