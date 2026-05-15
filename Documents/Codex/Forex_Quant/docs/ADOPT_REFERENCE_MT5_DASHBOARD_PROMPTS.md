# Prompts To Adopt MT5 Dashboard Ideas Without Replacing Forex_Quant

Use these prompts inside `C:/Users/p venkata naveen/Documents/Codex/Forex_Quant`.

Reference app:

```text
C:/Users/p venkata naveen/Cursor ai/forex_regime
```

Important rule: use the reference app for ideas, API shape, color behavior, and MT5 patterns. Do not replace the `Forex_Quant` architecture. Keep our vertical system folders.

Current `Forex_Quant` architecture:

```text
app/
  main.py
  templates/base.html
  static/css/app.css
  static/js/app.js

systems/
  data/
    backend.py
    service.py
    schemas.py
    ui.py
    templates/
    partials/
    config.yaml
  regime/
  strategy_router/
  research/
  risk/
  journal/
  monitoring/
  settings/
```

Target adoption:

```text
MT5 demo data -> snapshot API -> regime analytics -> strategy playbook -> risk gate -> UI
```

Keep real-money live trading disabled.

## Prompt A0 - Audit Current App And Reference Before Editing

```text
You are working in:
C:/Users/p venkata naveen/Documents/Codex/Forex_Quant

Reference app is:
C:/Users/p venkata naveen/Cursor ai/forex_regime

Task:
Audit both codebases before editing.

Read these current Forex_Quant files:
- app/main.py
- app/templates/base.html
- app/static/css/app.css
- systems/data/backend.py
- systems/data/service.py
- systems/data/ui.py
- systems/regime/backend.py
- systems/regime/service.py
- systems/regime/ui.py
- systems/strategy_router/service.py
- systems/strategy_router/ui.py
- systems/risk/backend.py
- systems/risk/shield.py
- systems/research/ui.py
- systems/journal/ui.py
- config/app.yaml
- config/symbols.yaml
- config/strategy_registry.yaml

Read these reference files only as inspiration:
- C:/Users/p venkata naveen/Cursor ai/forex_regime/dashboard-lite/assets/dashboard.css
- C:/Users/p venkata naveen/Cursor ai/forex_regime/dashboard-lite/assets/app.js
- C:/Users/p venkata naveen/Cursor ai/forex_regime/dashboard-lite/index.html
- C:/Users/p venkata naveen/Cursor ai/forex_regime/dashboard_api/server.py
- C:/Users/p venkata naveen/Cursor ai/forex_regime/forex_regime/snapshot_core.py
- C:/Users/p venkata naveen/Cursor ai/forex_regime/forex_regime/mt5_setup.py

Report before editing:
1. What Forex_Quant already has.
2. What is missing compared to the MT5 snapshot dashboard.
3. What should be adopted.
4. What should not be copied.

Do not edit files in this prompt.
```

## Prompt A1 - Adopt Dark Operational Theme

```text
Use the audit from Prompt A0.

Goal:
Adopt the reference app's GitHub-style dark operational theme into Forex_Quant without replacing the app.

Do not copy the whole reference CSS. Rebuild our CSS cleanly in app/static/css/app.css using the same functional color logic.

Design tokens to add:
- --bg: #0d1117
- --bg-elev: #161b22
- --bg-card: #21262d
- --border: #30363d
- --text: #e6edf3
- --text-muted: #8b949e
- --accent: #58a6ff
- --accent-dim: rgba(88, 166, 255, 0.15)
- --success: #3fb950
- --warning: #d29922
- --danger: #f85149
- --radius: 12px
- --shadow: 0 4px 24px rgba(0, 0, 0, 0.35)

Functional color rules:
- Blue = selected / clickable / current location / active regime.
- Green = allowed / healthy / selected strategy / bullish or favorable.
- Amber = caution / live data / reduced risk / waiting.
- Red = blocked / danger / kill switch / execution denied.
- Gray = disabled / not tested / unavailable.

Update:
- app/templates/base.html
- app/static/css/app.css
- systems/monitoring/templates/dashboard.html
- systems/data/templates/data.html
- systems/regime/templates/regimes.html
- systems/strategy_router/templates/strategies.html
- systems/research/templates/backtester.html
- systems/risk/templates/risk.html
- systems/journal/templates/decisions.html
- systems/settings/templates/settings.html if needed

UI behavior:
- Keep FastAPI + Jinja + Tailwind CDN + HTMX.
- Keep system folders.
- Keep app/main.py as shell/router registration only.
- No Streamlit.
- No React/Vue/Next.
- No huge landing page.
- No trading logic in HTML.

Add/revise CSS classes:
- panel
- panel-elev
- nav-link
- nav-link-active
- status-pill
- status-green
- status-amber
- status-red
- status-blue
- status-gray
- metric-card
- metric-label
- metric-value
- table-compact
- input
- button
- button-danger
- quadrant-card
- quadrant-card-active
- regime-card
- regime-card-active
- strategy-card
- strategy-card-selected
- chart-card
- empty-state
- error-state

Acceptance:
- All existing tests pass.
- Pages still render.
- Live Trading Disabled is always visible.
- UI is dark and colored by function.
- No page becomes a static copy of dashboard-lite.
```

## Prompt A2 - Dynamic Options From Backend

```text
Goal:
Remove hardcoded UI options where possible. The UI should ask backend systems for symbols, timeframes, regimes, strategies, and available data.

Current issue:
Some templates hardcode symbols and timeframes. That is okay for a shell, but not for MT5/backtesting.

Implement:

1. systems/data/backend.py
Add:
- get_available_symbols()
- get_available_timeframes()
- get_data_source_options()
- get_available_datasets()

Sources:
- config/symbols.yaml
- config/timeframes.yaml if it exists
- cleaned datasets in data/cleaned
- later MT5 gateway symbols when available

2. config/timeframes.yaml
Add:
- M1: 1
- M5: 5
- M15: 15
- M30: 30
- H1: 60
- H4: 240
- D1: 1440
Each entry includes:
- label
- minutes
- enabled
- mt5_constant placeholder or mapping key

3. systems/regime/backend.py
Add:
- get_regime_options()
- get_quadrant_options()
- get_modifier_options()
Return Q1-Q4 and M01-M13 from config/regimes.yaml.

4. systems/strategy_router/backend.py
Add:
- get_strategy_filter_options()
- get_regime_playbook_options()
Return families, statuses, slots, and regimes from config/strategy_registry.yaml.

5. Update templates:
- systems/data/templates/data.html
- systems/regime/templates/regimes.html
- systems/strategy_router/templates/strategies.html
- systems/research/templates/backtester.html

Replace hardcoded lists with backend-provided options.

6. Tests:
- options endpoints return JSON envelope.
- data page renders when no MT5 exists.
- symbols/timeframes come from config, not hardcoded list.

Acceptance:
- UI options are backend-driven.
- Missing MT5 does not crash the UI.
- Existing tests pass.
```

## Prompt A3 - Add MT5 Gateway System In Safe Demo/Data Mode

```text
Goal:
Add MT5 API usage for demo account data and account status, but do not enable real order sending.

Create a new vertical system:

systems/mt5_gateway/
  __init__.py
  backend.py
  service.py
  schemas.py
  ui.py
  config.yaml
  templates/mt5_gateway.html
  partials/mt5_status.html
  README.md

Reference:
Use concepts from:
C:/Users/p venkata naveen/Cursor ai/forex_regime/forex_regime/mt5_setup.py
C:/Users/p venkata naveen/Cursor ai/forex_regime/dashboard_api/server.py

Do not copy the old stdlib HTTPServer. We are using FastAPI.

Important:
MetaTrader5 Python binding is not thread-safe. Add a global RLock in systems/mt5_gateway/service.py:
- MT5_CALL_LOCK = threading.RLock()
- all MT5 calls must run inside this lock

config:
systems/mt5_gateway/config.yaml
Fields:
- enabled: false by default
- mode: demo_data
- terminal_path: optional
- default_symbol: EURUSD
- default_tf_minutes: 60
- default_bars: 12000
- allow_order_send: false
- allow_live_trading: false
- max_bars_per_request: 50000
- chunk_size: 5000

schemas.py:
- MT5Status
- MT5SymbolInfo
- MT5AccountInfo
- MT5RatesRequest
- MT5RatesResult
- MT5Tick
- MT5Error

service.py:
Implement:
- is_mt5_package_available()
- initialize_mt5()
- shutdown_mt5()
- timeframe_from_minutes(tf_minutes)
- copy_rates_batched(symbol, tf_minutes, bars)
- rates_to_rows(raw)
- get_latest_tick(symbol)
- get_account_info()
- get_symbol_info(symbol)
- get_available_symbols(search=None)
- get_health()

Safety:
- If MetaTrader5 package is missing, return clear disabled status.
- If terminal is not open/logged in, return clear error.
- Never place orders in this phase.
- Do not store account password in code.

backend.py:
Expose:
- health()
- status()
- fetch_rates(symbol, tf_minutes, bars)
- latest_tick(symbol)
- account_summary()
- available_symbols(search=None)

ui.py:
Routes:
- GET /mt5
- GET /api/mt5/status
- GET /api/mt5/account
- GET /api/mt5/symbols
- GET /api/mt5/tick/{symbol}
- POST /api/mt5/rates
- GET /partials/mt5-status

templates:
Show:
- package available
- terminal connected
- account mode demo/live/unknown
- balance/equity if available
- selected symbol
- latest bid/ask/spread
- fetched bars count
- warning: real orders disabled

Tests:
Mock MetaTrader5 if package is unavailable.
Tests must pass without MT5 installed/open.

Acceptance:
- Existing tests pass.
- MT5 system does not crash when MT5 is unavailable.
- Demo data fetch works if MT5 terminal is connected.
- Real order sending is not implemented.
```

## Prompt A4 - Connect Data System To MT5 Source

```text
Goal:
Let Data System load market bars from either CSV or MT5, using systems/mt5_gateway.

Do not remove CSV support.

Update:
- systems/data/schemas.py
- systems/data/service.py
- systems/data/backend.py
- systems/data/ui.py
- systems/data/templates/data.html
- systems/data/partials/data_load_result.html
- systems/data/partials/data_quality.html

Add source options:
- csv
- mt5_demo

Data flow:
1. User chooses source=mt5_demo.
2. User selects symbol, timeframe, bars.
3. Data backend calls mt5_gateway.backend.fetch_rates().
4. Rows are normalized to:
   time, open, high, low, close, tick_volume, spread
5. Existing cleaning and quality report runs.
6. Cleaned CSV is saved to data/cleaned.
7. Quality report is saved.

UI behavior:
- If MT5 unavailable, show amber/red status and exact reason.
- If source=csv, show path input.
- If source=mt5_demo, show bars input and MT5 status panel.
- Load button should show loading state.
- After load, refresh Data Quality and Available Datasets partials.

Acceptance:
- CSV tests still pass.
- New mocked MT5 data test passes.
- No order execution exists.
- Data page is dynamic and colored.
```

## Prompt A5 - Build FastAPI Snapshot Endpoint

```text
Goal:
Add a canonical /api/snapshot endpoint inspired by the reference app, but implemented in Forex_Quant's vertical architecture.

Do not use the old stdlib HTTPServer.
Do not replace existing regime/risk systems.

Create:

systems/snapshot/
  __init__.py
  backend.py
  service.py
  schemas.py
  ui.py
  config.yaml
  README.md

service.py responsibilities:
- parse snapshot request
- get data from source:
  - mt5_demo preferred if available
  - cleaned CSV fallback
- clean/normalize rows
- run regime detection
- load strategy playbook for selected regime
- build regime counts by Q1-Q4 and by regime_id
- build selected regime_detail if regime_id is provided
- run risk preview/gate using systems/risk
- include MT5/account/tick status if available
- return one JSON payload for UI

Endpoint:
GET /api/snapshot

Query parameters:
- symbol default EURUSD
- tf_minutes default 60
- bars default 12000
- regime_id optional
- strategy_key optional
- atr_sl_mult default 1.5
- max_bars default 40
- source default mt5_demo

Response shape:
{
  "meta": {},
  "source": "mt5_demo|csv",
  "mt5": {},
  "account": {},
  "live": {},
  "latest_regime": {},
  "regime_counts": {},
  "quadrant_bars": {},
  "total_bars": 0,
  "regime_detail": null_or_object,
  "strategy_playbook": {},
  "strategy_scores": [],
  "current_signal": null,
  "signal_checks": [],
  "risk_gate": {},
  "lot_size": 0.0,
  "warnings": []
}

regime_detail should include:
- regime_id
- regime_name
- quadrant
- bars_in_regime
- pct_of_sample
- pie_three_way
- monthly
- line_series
- strategies

At this phase:
- strategies can still be name-only.
- signal can be null.
- risk_gate can be preview/block until strategy formulas exist.

Tests:
- /api/snapshot returns envelope.
- /api/snapshot works from cleaned CSV fallback.
- /api/snapshot with regime_id returns regime_detail.
- /api/snapshot without regime_id returns no regime_detail but still returns live/meta/counts.
- MT5 unavailable returns warning and uses CSV if available.

Acceptance:
- Existing tests pass.
- Snapshot endpoint is the single JSON source for Regime Engine UI.
- No real execution.
```

## Prompt A6 - Regime Engine Wizard UI

```text
Goal:
Upgrade systems/regime UI into an interactive Regime Engine wizard similar in behavior to the reference app, but using FastAPI + HTMX + our /api/snapshot.

Keep it in:
systems/regime/
  ui.py
  templates/regimes.html
  partials/

Page flow:

Step 0 - Context bar:
- symbol select
- timeframe select
- bars input
- source select: mt5_demo or csv
- refresh snapshot button
- MT5 status pill
- Live Trading Disabled pill

Step 1 - Quadrant:
- Q1 Trend Low/Normal Vol
- Q2 Trend High Vol
- Q3 Range Low/Normal Vol
- Q4 Chaos/No Trade
Cards use colors:
- active card blue border/glow
- Q4 red/gray no-trade language

Step 2 - Regime in quadrant:
- show only regimes belonging to selected quadrant
- cards load from backend definitions, not hardcoded JS
- clicking a regime calls /api/snapshot with regime_id

Step 3 - Regime analytics:
- current selected regime
- confidence
- tradable true/false
- bars in regime
- pct of sample
- regime reasons
- feature snapshot

Step 4 - Visual analytics:
- pie_three_way
- line_series
- monthly bars
- CSS heatmap
- if chart library is not added yet, render table/placeholder with data and clear note

Step 5 - Strategy playbook:
- show only selected regime's 4 strategies
- selected strategy card gets green border/glow
- not_tested strategies are gray/locked

Step 6 - Risk gate / signal:
- current_signal if available
- signal_checks
- risk_gate approved/blocked
- lot_size
- no execute button until paper/demo execution phase

Step 7 - Backtest/scorecard:
- show scorecard rows when available
- otherwise show "Backtester not built yet" with next build path

HTMX behavior:
- quadrant selection updates regime grid
- regime selection updates snapshot panels
- symbol/timeframe/bars changes refresh context
- 10s polling optional only when MT5 source is active

Add endpoints/partials:
- GET /partials/regime-quadrants
- GET /partials/regime-grid?quadrant=Q1
- GET /partials/regime-snapshot?symbol=...&tf_minutes=...&bars=...&regime_id=...
- GET /partials/regime-charts?...
- GET /partials/regime-strategy-playbook?...
- GET /partials/regime-risk-gate?...

Acceptance:
- UI is colored dark cockpit style.
- Options are backend-driven.
- Selected regime fetches /api/snapshot.
- Strategies shown are only from selected regime.
- Missing MT5 falls back gracefully.
- No real execution button yet.
```

## Prompt A7 - Backtest/Scorecard From Snapshot Data

```text
Goal:
Start adopting the reference scorecard idea, but keep it simple and testable.

Create/extend:
- systems/research/service.py
- systems/research/backend.py
- systems/research/schemas.py
- systems/research/ui.py

For now, build scorecard-style analytics, not full broker execution:
- total bars
- regime counts
- quadrant counts
- selected regime count
- monthly counts
- strategy rows from registry
- placeholder MFE fields until strategy formulas exist

Then add true backtest later.

Endpoint:
- POST /api/backtests/run

Inputs:
- symbol
- tf_minutes
- bars
- source
- regime_id optional
- strategy_id optional
- atr_sl_mult
- max_bars

Output:
- run_id
- meta
- regime_counts
- quadrant_bars
- regime_detail
- strategy_rows
- warnings

UI:
- systems/research/templates/backtester.html uses dynamic symbols/timeframes/regimes/strategies.
- Show colored result cards.
- Show no fake profit if not calculated.
- Label MFE/scorecard clearly if not dollar P&L.

Acceptance:
- Works with CSV fallback.
- Works with MT5 demo data if available.
- Does not claim real profitability.
- Existing tests pass.
```

## Prompt A8 - Execution Safe Path Later

```text
Goal:
Prepare execution endpoints only after snapshot, risk gate, and paper trading are stable.

Do not implement real order sending yet unless explicitly asked later.

Add:
- systems/execution/backend.py
- systems/execution/service.py
- systems/execution/schemas.py
- systems/execution/ui.py

Endpoint:
POST /api/execute

For now:
- accept approval metadata
- reject with code execution_disabled
- show what checks would be required

Required future checks:
- MT5 connected
- demo account confirmed
- current signal exists
- signal not stale
- risk_gate.approved true
- kill switch clear
- no duplicate open position
- allowed_order_send true in config
- allow_live_trading false still blocks real live

Acceptance:
- /api/execute exists but refuses safely.
- UI shows disabled state.
- No real order sending.
```

## Suggested Build Order

```text
1. Prompt A0 - audit
2. Prompt A1 - dark theme/colors
3. Prompt A2 - dynamic backend options
4. Prompt A3 - MT5 gateway safe demo/data mode
5. Prompt A4 - Data System source=mt5_demo
6. Prompt A5 - /api/snapshot
7. Prompt A6 - Regime Engine wizard
8. Prompt A7 - scorecard/backtest analytics
9. Prompt A8 - disabled execution endpoint
```

Do not jump to execution before snapshot and risk UI are correct.

