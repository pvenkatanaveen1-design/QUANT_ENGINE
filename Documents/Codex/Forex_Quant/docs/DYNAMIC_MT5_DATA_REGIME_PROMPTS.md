# Dynamic MT5 Data And Regime Tab Prompts

Use these prompts for the next build stage of `Forex_Quant`.

Important direction:

```text
Use the old/non-working dashboard only as a product reference.
Do not copy its architecture.
Do not replace our FastAPI vertical-system codebase.
Write this in our style.
Keep real-money execution disabled.
Focus now on Data Tab and Regime Tab.
```

The target behavior is:

```text
MT5 demo account data
-> dynamic symbol/timeframe/options from backend
-> live values via FastAPI WebSockets
-> one-week regime analysis
-> selected active regime
-> selected strategy playbook for that regime
-> scenario/backtest analysis with kill zone on/off
-> output: trades, P/L, fail reasons, sweep/alpha/institutional-impact flags
```

Do not use hardcoded UI lists except as fallback when MT5 is unavailable.

## Prompt D0 - Re-Align Scope Before Editing

```text
We are not rebuilding from the reference dashboard.
We are improving our existing FastAPI vertical-system architecture.

Current priority:
1. Data Tab must use MT5 demo account data dynamically.
2. Regime Tab must use MT5 data and display live/current regime plus one-week analysis.
3. UI options must come from backend/MT5/config, not static hardcoded lists.
4. Live values should update through FastAPI WebSockets.
5. Real order execution must remain disabled.

Before editing, inspect the current systems:
- data
- regime
- strategy_router
- risk
- monitoring
- research
- app shell

Then report:
- what already supports this
- what must change
- what can stay as-is
- what must remain disabled for safety

Do not edit in this prompt.
```

## Prompt D1 - Add MT5 Gateway As Dynamic Data Source

```text
Build a new MT5 Gateway system using our vertical system pattern:

systems/mt5_gateway/
  backend.py
  service.py
  schemas.py
  ui.py
  config.yaml
  templates/
  partials/
  README.md

Purpose:
The MT5 Gateway is the only system allowed to talk directly to the MetaTrader5 Python package.

Rules:
- Use MT5 demo account data.
- Do not send real orders.
- Do not store account passwords.
- Protect all MT5 calls with a global thread lock because the MT5 Python binding is not safe for concurrent access.
- If MT5 is unavailable, return a clear disabled status instead of crashing.

Implement:
- check whether MetaTrader5 package is installed
- initialize MT5
- shutdown MT5
- get terminal/account status
- get account balance/equity/demo/live mode
- get available symbols from MT5
- get symbol info from MT5
- get latest tick bid/ask/spread
- map timeframes from minutes to MT5 constants
- fetch OHLC bars from MT5
- normalize MT5 bars to: time, open, high, low, close, tick_volume, spread

Dynamic symbols:
- symbol list must come from MT5 `symbols_get()` when MT5 is available
- include metadata where possible:
  - symbol
  - description
  - path/category
  - currency_base
  - currency_profit
  - trade_mode
  - visible
  - spread
  - digits
  - point
- UI should allow search/filter, not hardcoded fixed pairs

Dynamic timeframes:
- backend exposes supported timeframe options
- UI consumes backend response
- no hardcoded select options in template

API routes:
- GET /api/mt5/status
- GET /api/mt5/account
- GET /api/mt5/symbols
- GET /api/mt5/symbol/{symbol}
- GET /api/mt5/tick/{symbol}
- POST /api/mt5/rates

WebSocket routes:
- WS /ws/mt5/tick?symbol=EURUSD
- WS /ws/mt5/status

Tests:
- pass when MT5 package is missing
- pass with mocked MT5 module
- verify no order_send function is exposed
- verify symbols come from MT5 mock, not constants

Acceptance:
- Data Tab can ask MT5 Gateway for symbols/timeframes/ticks/bars.
- Existing tests pass.
- Real order sending is impossible.
```

## Prompt D2 - Make Data Tab Fully Dynamic And MT5-First

```text
Update Data Tab so it no longer behaves like a CSV-first static page.

Primary source:
- MT5 demo account

Fallback:
- CSV only when MT5 is unavailable or user intentionally selects CSV fallback

Data Tab UI behavior:
- top status strip shows MT5 connected/disconnected
- account mode: demo/live/unknown
- balance/equity if available
- selected symbol latest bid/ask/spread
- selected timeframe
- bars requested
- latest fetched bar time
- data quality status

Controls:
- source select: mt5_demo, csv_fallback
- symbol search/select populated from backend
- timeframe select populated from backend
- bars input
- date range optional
- fetch live bars button
- refresh tick button
- save cleaned dataset toggle

Live behavior:
- latest tick/spread updates via WebSocket
- if WebSocket disconnects, show amber state and retry
- no page reload needed for tick updates

Backend behavior:
- Data backend calls MT5 Gateway for data when source=mt5_demo
- clean and quality-check MT5 bars exactly like CSV bars
- save cleaned MT5 dataset with source metadata
- store quality report
- expose available datasets to Regime Tab

No hardcoded UI values:
- symbols from backend
- timeframes from backend
- data source options from backend
- latest tick from backend/WebSocket

Data quality:
- missing bars
- duplicate timestamps
- abnormal spread
- large gaps
- stale tick
- market closed warning

Data Tab outputs:
- cleaned rows
- removed rows
- quality status
- first/last bar time
- spread percentile
- latest bid/ask/spread
- whether data is safe for regime testing

Tests:
- mocked MT5 bars can be fetched and cleaned
- WebSocket payload schema is valid
- symbol dropdown data comes from backend
- no static symbol list remains in template
- CSV fallback still works

Acceptance:
- Data Tab is live/dynamic from MT5.
- It can fetch one week of bars for selected symbol/timeframe.
- It does not fake values when MT5 is down.
```

## Prompt D3 - Build One-Week Regime Test Engine

```text
Add a Regime Test Engine used by Data Tab and Regime Tab.

Goal:
Given selected symbol, timeframe, bar count or date range, classify all bars into regimes and summarize what happened during the last week.

Inputs:
- source: mt5_demo or csv_fallback
- symbol
- timeframe
- start/end OR bars
- killzone_enabled true/false
- include_spread_filter true/false
- include_sweep_detection true/false
- include_alpha_features true/false

Default test:
- last 7 calendar days from MT5
- selected timeframe
- selected symbol

Engine must calculate:
- regime per bar
- current/present regime
- previous regime
- regime transitions
- time spent in each regime
- Q1/Q2/Q3/Q4 distribution
- M01-M13 modifier distribution
- killzone vs non-killzone distribution
- spread stress periods
- sweep events
- compression events
- trend exhaustion events
- data quality warnings

Output:
- current_regime
- previous_regime
- active_since
- bars_by_regime
- bars_by_quadrant
- regime_timeline
- regime_transition_table
- killzone_summary
- spread_summary
- sweep_summary
- alpha_feature_summary
- no_trade_periods

Important:
- If no regime appears in a week, show "not observed in selected period"; do not fabricate.
- If current regime is Q4/no-trade, show why.
- If data is too thin, return warning.

Tests:
- synthetic one-week data classifies regimes
- missing MT5 data returns clear error
- killzone on/off changes summary
- transition table is generated

Acceptance:
- Regime Tab can display one-week regime history from MT5.
- Present active regime is shown from latest MT5 data.
- Previous regime and time-in-regime are shown.
```

## Prompt D3A - Full Regime Scanner And Trade-Ready Regime State

```text
Add the missing operational Regime Scanner layer.

Goal:
The Regime Tab must not only detect one selected regime. It must scan the full 52-regime library against MT5 history, identify the current active regime, estimate how often regimes usually change for the selected timeframe, and return the exact values that would be sent to the strategy/risk/trade-preparation layer.

Important:
- Keep existing regime formulas unless they are clearly wrong.
- Do not create a second regime engine.
- Use the existing classifier per bar, then aggregate across all 52 regimes.
- Do not fake a regime. If a regime is not observed, mark it as not_observed.
- Do not send live orders. This is trade-preparation only.

API links to build:
- GET /api/regimes/scan?symbol=EURUSD&timeframe=M15&lookback_days=7&bars=0&killzone_enabled=true
- GET /api/regimes/current?symbol=EURUSD&timeframe=M15
- GET /api/regimes/change-stats?symbol=EURUSD&timeframe=M15&lookback_days=7
- GET /api/regimes/{regime_id}/trade-state?symbol=EURUSD&timeframe=M15
- WS /ws/regime/live?symbol=EURUSD&timeframe=M15

Scanner behavior:
1. Pull MT5 bars through mt5_gateway only.
2. Classify every bar into one regime_id.
3. Build a 52-regime scan table.
4. Mark which regime is current/present active.
5. Mark previous regime.
6. Calculate active_since and active_duration_minutes.
7. Calculate how often regimes changed in the selected lookback.
8. Calculate typical regime duration for the selected timeframe.
9. Return trade-ready values for the current selected regime.

The 52-regime scan table must include for every regime:
- regime_id
- quadrant
- modifier
- observed true/false
- bars_count
- pct_of_period
- first_seen
- last_seen
- avg_duration_minutes
- median_duration_minutes
- last_duration_minutes
- transition_count
- tradable_count
- no_trade_count
- killzone_count
- spread_stress_count
- sweep_count
- confidence_avg
- confidence_latest_if_current
- status: current, previous, observed, not_observed

Current regime payload must include:
- symbol
- timeframe
- current_regime_id
- current_quadrant
- current_modifier
- confidence
- tradable true/false
- active_since
- active_duration_minutes
- latest_bar_time
- latest_close
- spread
- session
- killzone true/false
- reason list
- formula_values/features used by detector
- risk_posture
- no_trade_reason when blocked

Change statistics must include:
- total_transitions
- changes_per_day
- avg_minutes_between_changes
- median_minutes_between_changes
- fastest_change_minutes
- slowest_change_minutes
- current_regime_age_minutes
- current_regime_age_vs_typical: young, normal, extended
- by_timeframe explanation

Multi-timeframe scan:
The endpoint should support one timeframe first. Add service design so later we can call:
- M1/M5/M15/M30/H1/H4/D1
and compare current regimes across timeframes.

Trade-ready regime state:
When a regime is selected, return the values the next layer needs:
- selected_regime_id
- selected_strategy_candidates from strategy router
- allowed_strategy_keys
- blocked_strategy_keys
- regime_tradable true/false
- regime_block_reasons
- current_market_values:
  - bid
  - ask
  - spread_points
  - latest_close
  - atr
  - adx
  - trend_efficiency
  - volatility_percentile
  - spread_percentile
  - sweep_high
  - sweep_low
  - session
  - killzone
- proposed_trade_context:
  - symbol
  - timeframe
  - regime_id
  - risk_mode
  - live_trading_enabled false
  - real_order_enabled false
  - reason: research_or_demo_only

UI behavior:
- Default selected regime is the present active regime.
- Show a table/grid for all 52 regimes.
- Current regime should be visually highlighted.
- Previous regime should be visible.
- Not-observed regimes should stay selectable but muted.
- When user selects any regime, update the strategy playbook and trade-ready values panel.
- Show "these are values prepared for strategy/risk analysis, not order execution."

Tests:
- scan returns 52 regime rows even if only a few are observed
- current regime is marked exactly once
- previous regime is detected when transitions exist
- active_duration_minutes is calculated
- avg_minutes_between_changes is calculated
- not observed regimes are marked not_observed
- trade-state returns 4 strategies for selected regime
- trade-state never exposes order_send or live order approval

Acceptance:
- User can see all regimes one by one in a complete table.
- User can immediately see which regime is current.
- User can see how many minutes the current regime has been active.
- User can see how often regimes usually change for the selected timeframe.
- Selecting a regime shows the values that will be sent to strategy/risk/scenario layers.
- No live trading is enabled.
```

## Prompt D4 - Regime Tab Dynamic Wizard

```text
Rebuild the Regime Tab as a dynamic operational wizard, not a static explanation page.

Top controls:
- source
- symbol from backend/MT5
- timeframe from backend
- bars/date range
- killzone toggle
- spread filter toggle
- sweep/alpha toggle
- refresh snapshot button

Live top strip:
- MT5 status
- account mode
- latest bid/ask/spread
- current timeframe
- current regime
- previous regime
- kill switch status
- live trading disabled

Step 1 - Current Regime:
Show:
- current regime id
- base quadrant
- modifier
- confidence
- tradable true/false
- active since
- active duration in minutes
- usual regime change minutes for this timeframe
- reason list with formula values

Step 2 - One-Week Regime Map:
Show:
- Q1/Q2/Q3/Q4 distribution
- M01-M13 distribution
- full 52-regime scan table
- current/previous/observed/not-observed status for every regime
- regime timeline
- transition table
- regime change statistics
- killzone vs non-killzone comparison
- spread stress windows
- no-trade windows

Step 3 - Regime Selector:
User can select:
- present active regime
- previous regime
- any observed regime from week
- any full 52-regime library item

Selection behavior:
- present active regime selected by default
- selecting a regime updates strategies and analysis
- if selected regime was not observed this week, show "not observed in selected period"

Step 4 - Strategy Playbook:
For selected regime show only its 4 mapped strategies:
- primary
- secondary
- confirmation
- fallback

Each strategy card shows:
- name
- status
- enabled/live allowed
- formula availability
- backtest availability
- allowed/not allowed reason
- exact regime values that strategy will receive
- exact risk/trade-preparation values that would be sent next

Step 5 - Scenario Controls:
User can choose:
- strategy
- timeframe
- range/bars
- killzone on/off
- breakout logic on/off
- sweep logic on/off
- alpha filter on/off
- investment amount, default 10000 USD

Step 6 - Scenario Output:
Show:
- number of candidate trades
- wins/losses
- gross P/L estimate
- net P/L estimate after spread/slippage
- max drawdown estimate
- profit factor
- expectancy
- fail reasons
- institutional-impact flags:
  - liquidity sweep
  - spread stress
  - news placeholder
  - low liquidity
  - false breakout
  - trend exhaustion
- alpha notes:
  - trend alpha
  - range alpha
  - breakout alpha
  - sweep alpha

Important:
- If selected strategy has no executable formula yet, show "logic not implemented" and do not calculate fake P/L.
- For strategies with formulas, calculate using historical bars only.
- P/L must be labeled as backtest/scenario estimate, not guaranteed.

Live behavior:
- WebSocket updates latest tick/current regime.
- WebSocket can update active duration and regime change status.
- Snapshot refresh updates regime panels.
- Strategy/scenario output updates after user changes controls.

Tests:
- page renders without MT5
- page uses backend options
- present active regime is default selected
- strategy cards come from selected regime only
- scenario blocks P/L when strategy logic missing

Acceptance:
- Regime Tab is dynamic and explains why.
- No hardcoded symbol/timeframe/regime lists in template.
- Current MT5 regime and one-week regime history are visible.
- Full 52-regime scan is visible and selectable.
- Selected regime exposes trade-ready values but does not execute orders.
```

## Prompt D5 - Scenario Backtest For Selected Regime + Strategy

```text
Build a small scenario backtest engine focused only on the selected regime and selected strategy.

Inputs:
- symbol
- timeframe
- bars/date range
- selected_regime
- selected_strategy
- investment_amount
- killzone_enabled
- breakout_enabled
- sweep_enabled
- alpha_enabled
- spread_filter_enabled

Rules:
- Use MT5 historical bars by default.
- Use cleaned CSV fallback only if MT5 unavailable.
- Only evaluate bars where detected regime matches selected_regime, unless user chooses "all observed regimes".
- Only run strategy if executable logic exists.
- If no executable logic exists, return blocked result with reason.

Initial executable strategy families:
- EMA pullback continuation
- Donchian/channel breakout
- ATR momentum breakout
- Bollinger mean reversion
- RSI range fade
- liquidity sweep reversal
- failed breakout fade
- no-trade defensive

Metrics:
- candidate trades
- executed simulated trades
- wins
- losses
- win rate
- gross profit
- gross loss
- net P/L
- spread cost
- slippage estimate
- profit factor
- expectancy
- average R
- max drawdown
- max consecutive losses
- best trade
- worst trade
- fail reason counts

Failure reasons:
- wrong regime
- no setup
- spread too high
- killzone blocked
- false breakout
- sweep failed
- stop too tight
- target not reached
- trend exhausted
- low liquidity
- data quality issue

Investment amount:
- default 10000 USD
- risk per trade from risk config
- position sizing uses stop distance and pip value estimate
- all output must say "scenario estimate"

Tests:
- scenario blocks non-executable strategy
- scenario produces trades for synthetic matching setup
- killzone toggle changes results
- spread filter changes results
- P/L includes spread cost

Acceptance:
- Regime Tab can show practical results for selected regime + strategy.
- No fake P/L for unimplemented strategies.
- Output explains why trades failed.
```

## Prompt D6 - WebSocket Live Updates

```text
Add FastAPI WebSocket live updates for Data Tab and Regime Tab.

WebSocket endpoints:
- /ws/data/live?symbol=EURUSD
- /ws/regime/live?symbol=EURUSD&tf_minutes=15

Data live payload:
{
  "type": "tick",
  "symbol": "EURUSD",
  "bid": 0,
  "ask": 0,
  "spread": 0,
  "time": "...",
  "mt5_connected": true
}

Regime live payload:
{
  "type": "regime",
  "symbol": "EURUSD",
  "tf_minutes": 15,
  "current_regime": {},
  "previous_regime": {},
  "risk_state": {},
  "time": "..."
}

Frontend:
- app/static/js/app.js should include small WebSocket helpers
- reconnect with backoff
- show amber disconnected state
- update visible status badges and metrics
- no trading logic in JS

Rules:
- WebSocket only streams data/status.
- It never places orders.
- It must respect MT5 lock.
- It must degrade gracefully if MT5 unavailable.

Tests:
- WebSocket endpoint can be connected with TestClient
- mock payload shape is valid
- unavailable MT5 sends disabled/error payload, not crash

Acceptance:
- Data Tab tick/spread updates live.
- Regime Tab current regime can refresh live.
- UI clearly shows disconnected/reconnecting states.
```

## Prompt D7 - Dark Functional UI Styling

```text
Apply a functional dark cockpit theme, inspired by the reference but written cleanly for our app.

Do not copy the whole CSS.
Do not make the UI decorative.

Color function:
- background: near black
- panel: elevated graphite
- border: muted gray
- text: near white
- muted: gray
- blue: selected/current/action
- green: healthy/approved/profitable/selected strategy
- amber: caution/live/reduced risk
- red: blocked/loss/kill switch
- gray: disabled/not tested

Update:
- base layout
- sidebar
- top status strip
- cards
- tables
- inputs
- buttons
- status pills
- quadrant cards
- regime cards
- strategy cards
- scenario result panels
- chart panels

Behavior:
- active nav blue
- live MT5 pill amber
- selected regime blue
- selected strategy green
- blocked risk red
- not tested strategy gray
- no-trade Q4 red/gray

Responsive:
- desktop dense layout
- mobile stack controls safely
- tables scroll horizontally
- no text overlap

Tests:
- existing page tests pass
- static CSS route works
- major pages render

Acceptance:
- UI feels like an operational trading cockpit.
- It remains readable and dense.
- No values are hardcoded into design.
```

## Build Order

```text
1. D0 - Re-align scope
2. D1 - MT5 Gateway
3. D2 - Dynamic MT5 Data Tab
4. D3 - One-week Regime Test Engine
5. D3A - Full Regime Scanner and trade-ready regime state
6. D4 - Dynamic Regime Tab Wizard
7. D5 - Scenario Backtest for selected regime + strategy
8. D6 - WebSocket live updates
9. D7 - Dark functional UI styling
```

Do Data Tab and Regime Tab first. Do not build real execution yet.
