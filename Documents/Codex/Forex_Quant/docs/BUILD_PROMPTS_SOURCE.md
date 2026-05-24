# VS Code Codex Build Prompts For Quanta Forex Control Center

Use these prompts one by one in VS Code Codex. Do not skip phases. Each prompt assumes the same architecture: data first, then regime detection, then strategy routing, then risk analysis, then backtest trust, then execution.

Important: this is research/trading infrastructure, not a promise of profitability. Every strategy must remain disabled for live trading until it has backtest, walk-forward, Monte Carlo, paper-trading, and funded-rule approval.

## Master Architecture Context To Paste At The Top Of Every Prompt

```text
You are building a Python Forex quant research and execution platform named quanta-forex-control-center.

Main goal:
Build a UI-first quant platform where the user can see market regimes, strategy candidates, historical backtest trust, present risk, funded-account rules, paper/live status, and execution logs without editing code.

Tech stack:
- Python 3.11+
- pandas and numpy for data
- pydantic or dataclasses for models
- pyyaml for config
- pytest for tests
- DuckDB or SQLite for local storage
- FastAPI for the backend/web server
- Jinja2 templates for server-rendered pages
- plain HTML with Tailwind CSS for the UI
- HTMX for dynamic UI updates without a large frontend app
- small vanilla JavaScript only where needed
- Use CDN links for Tailwind/HTMX in the first local version; move to local compiled/static assets later if needed.
- plotly for charts
- MetaTrader5 Python package later, only after paper trading is stable

Architecture rule:
- core/ contains shared utilities and models only.
- systems/ contains independent vertical business systems.
- orchestrator/ coordinates systems.
- app/ contains only the FastAPI shell, shared base template, shared static CSS/JS, and route registration.
- strategies/ contains strategy logic only.
- config/ contains user-editable YAML.
- data/ contains raw, cleaned, features, backtest results, journal, and live logs.
- tests/ proves behavior.
- docs/ explains architecture and operation.

Vertical system rule:
Each major system should be easy to understand in one folder. Use this pattern:
systems/<system_name>/
  backend.py      # system-facing functions used by orchestrator or other approved callers
  service.py      # business logic and workflows for this system
  schemas.py      # pydantic/dataclass request/response/domain schemas
  ui.py           # FastAPI APIRouter for this system's pages, API endpoints, and HTMX partials
  config.yaml     # local defaults for this system
  templates/      # system-specific full page templates if needed
  partials/       # system-specific HTMX partial templates if needed
  README.md       # what this system owns and does not own

Keep logic and UI close by folder, but not mixed in the same function:
- service.py owns business logic.
- backend.py exposes clean operations.
- schemas.py owns typed data contracts.
- ui.py only translates HTTP requests into service/backend calls and renders templates/partials.
- tests prove the system behavior.

Do not create random bot scripts.
Do not put trading logic inside the UI.
Do not put broker execution inside strategies.
Do not let systems import each other heavily.
Use orchestrator to coordinate.
All live trading must be disabled by default.

Target folder structure:
quanta-forex-control-center/
  app/
    main.py
    templates/
      base.html
    static/
      css/
      js/
  core/
    config_manager.py
    logger.py
    event_bus.py
    state_store.py
    time_utils.py
    models/
  config/
    app.yaml
    symbols.yaml
    sessions.yaml
    regimes.yaml
    strategy_registry.yaml
    risk_rules.yaml
    funded_rules.yaml
    data_sources.yaml
    broker.yaml.example
  systems/
    data/
      backend.py
      service.py
      schemas.py
      ui.py
      config.yaml
      templates/
      partials/
    regime/
      backend.py
      service.py
      schemas.py
      ui.py
      config.yaml
      templates/
      partials/
    strategy_router/
      backend.py
      service.py
      schemas.py
      ui.py
      config.yaml
    strategy_templates/
      backend.py
      service.py
      schemas.py
      ui.py
      config.yaml
    research/
      backend.py
      service.py
      schemas.py
      ui.py
      config.yaml
    risk/
      backend.py
      service.py
      schemas.py
      ui.py
      config.yaml
    execution/
      backend.py
      service.py
      schemas.py
      ui.py
      config.yaml
    monitoring/
      backend.py
      service.py
      schemas.py
      ui.py
      config.yaml
    journal/
      backend.py
      service.py
      schemas.py
      ui.py
      config.yaml
  orchestrator/
  strategies/
  data/
    raw/
    cleaned/
    features/
    backtest_results/
    journal/
    live_logs/
  docs/
  tests/
  scripts/

System map:
Data layer:
S6 Market Data Hub, S32 Tick Sanitizer, S41 Data Quality Monitor, S42 Economic Surprise placeholder.
Market intelligence:
S1 Pulse, S3 Heartbeat, S5 News Guard, S8 Regime Detector, S10 Session Filter, S11 Curve Filter placeholder, S13 Liquidity Map, S25 Sentiment placeholder, S26 Macro placeholder.
Strategy:
S14 Alpha Trigger, S15 Scoring Engine, S17 Re-entry Logic, S34 Optimizer placeholder, S35 AI Supervisor placeholder.
Risk:
S2 Shield, S7 Cost Guard, S9 Correlation Guard, S12 State Manager, S16 Position Sizer, S18 Exit Manager, S30 Edge Decay Monitor, S37 Kill Switch, S38 Funded Rules Engine, S43 Portfolio Allocator placeholder.
Execution:
S4 Router, S24 Multi Sync placeholder, S29 API Vault, S31 Static IP Locker placeholder, S33 Execution Profiler, S39 Broker Reconciliation.
Research:
S19 Backtester, S20 Walk-Forward, S21 Monte Carlo, S23 Statistical Auditor, S40 Model Registry.
Operations:
S22 Journaler, S27 Health Dashboard, S28 Self-Healer placeholder, S36 Tax Ledger placeholder, S44 Disaster Recovery placeholder.

Critical decision flow:
Market data -> data quality -> regime detection -> regime strategy router -> strategy signal -> historical backtest trust -> present risk analysis -> funded rules -> kill switch -> position sizing -> execution approval -> paper/live router -> journal -> performance feedback.
```

## Prompt 1 - Data Setup And Project Foundation

```text
Use the Master Architecture Context above.

Build Phase 1: Data setup and project foundation.

Goal:
Create the foundation that all 40+ systems will depend on. This phase should not trade, backtest, or run strategies yet. It should only load, validate, clean, store, and report Forex market data.

Create or update the full folder structure from the architecture.

Implement these files:

1. README.md
Explain:
- project purpose
- current phase
- how to install
- how to run tests
- what is intentionally not built yet

2. requirements.txt
Include:
- pandas
- numpy
- pyyaml
- pytest
- duckdb
- fastapi
- uvicorn
- jinja2
- python-multipart
- plotly
- pydantic if useful

3. .env.example
Include placeholders only:
- ENV=local
- DATA_ROOT=data
- BROKER_MODE=disabled
- ALLOW_LIVE_TRADING=false

4. config/app.yaml
Include:
- app_name
- environment
- timezone: UTC
- data_root
- live_trading_enabled: false
- paper_trading_enabled: false

5. config/symbols.yaml
Include major FX symbols:
- EURUSD
- GBPUSD
- USDJPY
- USDCHF
- USDCAD
- AUDUSD
- NZDUSD
- XAUUSD as optional/high risk
For each symbol include:
- pip_size
- pip_value_mode placeholder
- min_spread_pips placeholder
- max_spread_pips placeholder
- enabled false by default

6. config/sessions.yaml
Define sessions in UTC:
- Asia
- London
- London Open
- London NY Overlap
- NY Late
- Rollover
Each session must have start/end time and notes.

7. config/data_sources.yaml
Define local CSV source:
- source_name: local_csv
- raw_path: data/raw
- cleaned_path: data/cleaned
- required_columns: time, open, high, low, close, tick_volume, spread

8. systems/data/config.yaml
Local defaults for the Data System:
- raw_path
- cleaned_path
- duckdb_path
- required_columns
- max_spread_percentile_warning
- gap_detection_lookback
- stale_data_minutes

9. core/config_manager.py
Build a ConfigManager that:
- loads YAML files
- validates required keys
- provides get(path, default)
- raises clear config errors
- does not silently ignore missing required config

10. core/logger.py
Build logging setup:
- console logs
- file logs to data/live_logs/quanta.log
- create directory if missing
- format includes time, level, module, message

11. core/time_utils.py
Build:
- parse timestamp
- convert timezone to UTC
- check whether a timestamp is inside a session window
- handle sessions that cross midnight

12. core/models/market.py
Create dataclasses or pydantic models:
- Candle
- Tick
- MarketDataset
- DataQualityReport

13. systems/data/schemas.py
Create Data System schemas:
- Candle
- Tick
- DataLoadRequest
- DataLoadResult
- DataQualityIssue
- DataQualityReport
- CleanedDatasetInfo

14. systems/data/service.py
Own all Data System business logic:
- load CSV from data/raw
- normalize column names lowercase
- validate required columns
- parse time
- sort by time
- remove exact duplicates
- remove invalid OHLC rows where high < low
- remove rows where open/high/low/close <= 0
- flag missing values
- flag abnormal spread
- flag large price gaps using ATR-like rolling range
- detect missing time intervals
- detect duplicate timestamps
- detect stale data
- save cleaned CSV to data/cleaned
- optionally write DuckDB table
- return DataLoadResult and DataQualityReport

15. systems/data/backend.py
Expose clean Data System operations:
- load_symbol_data(symbol, timeframe, source)
- clean_dataset(input_path)
- get_dataset_status(symbol, timeframe)
- get_quality_report(symbol, timeframe)
This file should call service.py, not duplicate logic.

16. systems/data/ui.py
Create a FastAPI APIRouter for Data System:
- GET /data page route
- GET /api/data/status
- POST /api/data/load-csv
- GET /partials/data-quality
ui.py must call backend.py/service.py and render templates/partials. No cleaning logic inside route handlers.

17. systems/data/templates/data.html
Page should show:
- data source
- loaded symbols
- cleaned files
- latest quality status
- obvious warning if no data exists

18. systems/data/partials/data_quality.html
HTMX partial for quality report.

19. systems/data/README.md
Explain:
- system ownership
- backend.py vs service.py vs ui.py
- accepted input columns
- quality checks
- what this system does not do

20. docs/DATA_LAYER.md
Explain:
- what data columns are expected
- how data is cleaned
- what quality checks exist
- why data quality comes before strategy

21. tests/systems/test_data_system.py
Tests must cover:
- config loading
- valid CSV loading
- missing required column fails
- invalid OHLC rows removed
- duplicate timestamps handled
- abnormal spread flagged
- session time utility works

Acceptance criteria:
- pytest passes
- no strategy files are implemented yet
- no broker execution is implemented
- no live trading setting is true
- app/main.py can register systems/data/ui.py, but the Data System must still work without UI
- code is modular and readable
```

## Prompt 2 - Regime Detection Engine

```text
Use the Master Architecture Context above.

Build Phase 2: Regime Detection Engine.

Goal:
The system must understand the market before choosing a strategy. Regime detection converts raw/cleaned market data into a regime_id like Q1_M04. The strategy layer must later depend on this regime_id.

Regime model:
Base regimes:
- Q1 = Trend + Low/Normal Volatility
- Q2 = Trend + High Volatility
- Q3 = Range + Low/Normal Volatility
- Q4 = Chaos / Transition / No Trade

Modifiers:
- M01 Clean Liquid Market
- M02 Compression
- M03 Asia Session
- M04 London Open
- M05 London-NY Overlap
- M06 NY Late / Rollover
- M07 Pre-News
- M08 Post-News
- M09 Liquidity Sweep
- M10 Spread Stress
- M11 Trend Exhaustion
- M12 Multi-Timeframe Agreement
- M13 USD / Correlation Shock

Implement:

1. config/regimes.yaml
Include thresholds:
- atr_period: 14
- trend_efficiency_period: 30
- volatility_percentile_lookback: 252
- low_vol_percentile: 40
- high_vol_percentile: 70
- extreme_vol_percentile: 90
- trend_efficiency_min: 0.35
- adx_trend_min: 22
- adx_range_max: 18
- spread_stress_percentile: 90
- compression_percentile: 25
- exhaustion_atr_distance: 2.5
Include each base regime and modifier with description, tradable flag, and risk posture.

2. systems/regime/config.yaml
Local defaults for the Regime System:
- feature lookbacks
- base regime thresholds
- modifier priority order
- session modifier mapping
- no-trade severity rules

3. core/models/regime.py
Create:
- RegimeResult
- RegimeFeatureSet
- RegimeReason
RegimeResult fields:
- base_regime
- modifier
- regime_id
- confidence
- tradable
- risk_posture
- reasons list
- feature snapshot

4. systems/regime/schemas.py
Create Regime System schemas:
- RegimeDetectionRequest
- RegimeDetectionResult
- RegimeFeatureSet
- RegimeReason
- ModifierResult
- SessionLabel

5. systems/regime/service.py
Own all Regime System business logic.
Implement feature calculations using only past data:
- simple returns
- log returns
- true range
- ATR
- ATR percent of close
- volatility percentile
- trend efficiency = abs(close_t - close_t-n) / sum(abs(close_i - close_i-1))
- ADX or a simplified trend strength helper
- rolling range compression
- spread percentile
- candle body/wick metrics

Base regime logic:
- If data quality bad, spread stress extreme, volatility extreme, or trend/range unclear -> Q4
- If trend strength is high and volatility percentile <= high threshold -> Q1
- If trend strength is high and volatility percentile > high threshold -> Q2
- If trend strength is weak and volatility not extreme -> Q3
- Otherwise Q4

Modifier logic:
- M10 must override normal modifiers when spread stress is true.
- M07/M08 are placeholders using news_lock fields if provided, but do not call external news APIs yet.
- M03/M04/M05/M06 come from session detection.
- M02 compression when ATR percentile is low and range compressed.
- M09 liquidity sweep when price breaks prior swing high/low and closes back inside.
- M11 exhaustion when price is far from EMA/mean by ATR multiple and trend strength is flattening.
- M12 when higher timeframe and current timeframe agree. Implement placeholder input support.
- M13 when correlation/USD shock data is provided. Implement placeholder input support.
- M01 if no stronger modifier applies and spread/data are clean.

Also implement session classification inside this system:
- read config/sessions.yaml
- classify current timestamp
- handle sessions that cross midnight

Also implement basic liquidity map features:
- prior swing high
- prior swing low
- sweep high
- sweep low
- close back inside range

6. systems/regime/backend.py
Expose clean Regime System operations:
- detect_latest_regime(symbol, timeframe)
- detect_regime_for_dataframe(dataframe, symbol, timeframe)
- calculate_feature_snapshot(dataframe)
- explain_regime(regime_id)
This file should call service.py, not duplicate logic.

7. systems/regime/ui.py
Create a FastAPI APIRouter for Regime System:
- GET /regimes page route
- GET /api/regimes/latest
- GET /api/regimes/history
- GET /api/regimes/definitions
- GET /partials/latest-regime
- GET /partials/regime-feature-table
ui.py must call backend.py/service.py and render templates/partials. No regime formulas inside route handlers.

8. systems/regime/templates/regimes.html
Show:
- current regime
- Q1-Q4 explanation
- M01-M13 modifiers
- regime confidence
- reasons
- feature values
- no-trade reasons

9. systems/regime/partials/latest_regime.html
HTMX partial for current regime.

10. systems/regime/README.md
Explain:
- why regime comes before strategy
- backend.py vs service.py vs schemas.py vs ui.py
- formulas used
- no-lookahead rule
- what the Regime System does not own

11. docs/REGIME_ENGINE.md
Explain:
- why regime comes before strategy
- formulas used
- how Q1-Q4 are chosen
- how M01-M13 modifiers are chosen
- what causes no-trade
- how this avoids using future candles

12. tests/systems/test_regime_system.py
Cover:
- synthetic trend low vol -> Q1
- synthetic trend high vol -> Q2
- synthetic range -> Q3
- extreme spread -> Q*_M10 or Q4_M10 depending severity
- London Open timestamp -> M04
- compression -> M02
- liquidity sweep -> M09
- bad data -> Q4

Acceptance criteria:
- pytest passes
- RegimeResult contains clear reasons
- no strategy logic is implemented in regime detector
- ui.py contains route/rendering code only
- no broker execution exists
```

## Prompt 3 - Strategy Registry And Regime Router

```text
Use the Master Architecture Context above.

Build Phase 3: Strategy registry and regime router.

Goal:
Create the bridge from regime -> strategy. The system must not evaluate all strategies blindly. It must only show/evaluate the 4 strategy candidates assigned to the current regime.

Inputs:
- config/strategy_registry.yaml
- RegimeResult from the regime detector

Registry rules:
- 52 regimes x 4 slots = 208 entries
- slots: primary, secondary, confirmation, fallback
- all entries start enabled=false
- all entries start status=not_tested
- live trading cannot use not_tested strategies
- research UI can display not_tested strategies

Implement:

1. config/strategy_registry.yaml
Create 208 strategy entries. Each entry must have:
- id
- name
- regime_id
- slot
- family
- status
- enabled
- description
- logic_status: name_only
- live_allowed: false

Use existing regime candidate names from the blueprint if available. If not available, generate clean names from the 52 regime table.

2. core/models/signal.py
Create:
- StrategyCandidate
- Signal
- SignalScore

3. systems/strategy/strategy_router.py
Responsibilities:
- load all registry entries
- validate exactly 208 entries
- validate each regime has exactly 4 entries
- return candidates for a regime_id
- support modes:
  - research: show all 4 even if not_tested
  - paper: only return enabled strategies with status paper_approved or higher
  - live: only return enabled strategies with status live_approved
- preserve slot order
- return clear reasons when no strategies are tradable

4. systems/strategy/strategy_selector.py
Responsibilities:
- receive candidates and later strategy signals
- choose candidate order
- never override risk engine
- never execute orders

5. docs/STRATEGY_ROUTER.md
Explain:
- why we use regime router
- why all 208 are disabled by default
- status lifecycle:
  name_only -> logic_added -> backtested -> walk_forward_passed -> monte_carlo_passed -> paper_approved -> live_approved -> retired

6. tests/test_strategy_router.py
Cover:
- total entries = 208
- every regime has 4
- research mode returns not_tested entries
- live mode blocks not_tested entries
- missing regime returns safe empty result
- duplicate id fails validation

Acceptance criteria:
- pytest passes
- all 208 names exist
- no real strategy formulas are required yet
- no live trading possible
```

## Prompt 4 - Strategy Template Logic

```text
Use the Master Architecture Context above.

Build Phase 4: Add first strategy logic templates, not all 208.

Goal:
Build reusable strategy templates that many of the 208 names can map to. Do not write 208 separate strategy classes. Build core strategy families first.

Implement strategy interface:

1. strategies/base_strategy.py
BaseStrategy must define:
- strategy_id
- name
- family
- supported_regimes
- required_columns
- generate_signal(data, regime_result, config) -> Signal or None
- validate_data()
- no lookahead rule

2. Implement first 8 templates:
- EMA Pullback Continuation
- Donchian Continuation
- ATR Breakout
- Opening Range Breakout
- Bollinger Mean Reversion
- RSI Range Fade
- Liquidity Sweep Reversal
- Failed Breakout Fade

Each template must:
- use only completed candles
- check regime suitability
- check spread is normal
- produce entry, stop, target, direction, confidence, and reason
- return None if conditions are absent
- not calculate position size
- not send broker orders

3. systems/strategy/alpha_trigger.py
Given candidates and loaded templates:
- evaluate only candidate templates allowed by regime router
- collect possible signals

4. systems/strategy/scoring_engine.py
Score signals using:
- regime confidence
- strategy confidence
- spread quality
- volatility quality
- distance to stop
- old backtest trust placeholder
Return ranked signals.

5. docs/STRATEGY_TEMPLATES.md
For each template, document:
- best regimes
- formula
- entry logic
- stop logic
- exit/target logic
- failure conditions

6. tests/test_strategy_templates.py
Cover:
- no signal when wrong regime
- signal when synthetic pattern matches
- no signal when spread abnormal
- no future candle usage
- scoring ranks stronger signal above weak signal

Acceptance criteria:
- pytest passes
- only 8 templates implemented
- registry remains 208 names
- strategy templates do not execute trades
```

## Prompt 5 - Risk Analysis Layer

```text
Use the Master Architecture Context above.

Build Phase 5: Risk analysis and funded-account protection.

Goal:
Before any execution, every signal must pass risk analysis. Risk uses two kinds of evidence:
1. Old evidence: backtest/walk-forward performance trust.
2. Present evidence: current market, spread, drawdown, correlation, funded rules, kill switch.

Implement:

1. config/risk_rules.yaml
Include:
- base_risk_per_trade_percent: 0.25
- max_risk_per_trade_percent: 0.5
- max_daily_loss_percent: 3.0
- daily_lock_buffer_percent: 60
- max_total_drawdown_percent: 8.0
- max_open_trades: 2
- max_symbol_trades: 1
- max_correlated_trades: 2
- min_backtest_profit_factor: 1.15
- min_sample_trades: 100
- min_expectancy_r: 0.05
- max_allowed_spread_percentile: 80
- reduce_risk_when_confidence_below: 0.70

2. config/funded_rules.yaml
Include common funded-account controls:
- max_daily_loss_percent
- max_total_drawdown_percent
- no_trade_near_daily_limit
- news_trading_allowed false by default
- weekend_holding_allowed false by default
- max_lot_size placeholder
- consistency_rule placeholder

3. core/models/risk.py
Create:
- RiskApproval
- PositionSizeResult
- AccountState
- PresentRiskSnapshot
- HistoricalTrustProfile

4. systems/risk/cost_guard.py
Checks:
- current spread
- spread percentile
- estimated slippage
- commission placeholder
- swap placeholder
Return approval/rejection with reasons.

5. systems/risk/position_sizer.py
Calculate:
- account risk amount
- stop distance in pips
- lot size
- final risk percent
Formula:
final_risk = base_risk * regime_confidence_factor * historical_trust_factor * present_risk_factor

6. systems/risk/funded_rules_engine.py
Block if:
- daily loss near limit
- total drawdown near limit
- max trades exceeded
- news lock active and news trading disabled
- weekend/rollover rule breached
- symbol disabled

7. systems/risk/correlation_guard.py
Track:
- USD exposure
- same-direction pair exposure
- correlated pair count
Can be simple in Phase 5.

8. systems/risk/kill_switch.py
Hard block when:
- data quality critical
- spread stress critical
- daily lock active
- broker disconnected placeholder
- repeated losses placeholder
- manual kill flag true

9. systems/risk/shield.py
Combine all risk systems:
- cost guard
- funded rules
- correlation guard
- kill switch
- position sizer
Return final RiskApproval.

10. docs/RISK_LAYER.md
Explain:
- old backtest trust vs present risk
- why risk can reduce size even if signal is good
- funded account safety behavior
- kill switch rules

11. tests/test_risk_layer.py
Cover:
- cost guard blocks wide spread
- funded rules block daily loss
- kill switch blocks critical data quality
- position sizing reduces risk for weak confidence
- final shield approves only when all checks pass

Acceptance criteria:
- pytest passes
- no execution happens inside risk layer
- every rejection has human-readable reason
```

## Prompt 6 - Backtest And Historical Trust

```text
Use the Master Architecture Context above.

Build Phase 6: Backtester and historical trust scoring.

Goal:
The risk layer needs old evidence. Build a backtester that stores performance by:
regime_id + strategy_id/template + symbol + timeframe + session.

Implement:

1. systems/research/backtester.py
Capabilities:
- run one strategy template on cleaned historical data
- detect regime per candle or per completed window
- only evaluate strategy when router allows it
- simulate entry, stop, target
- include spread and slippage
- record trades with R multiple
- avoid lookahead bias

2. systems/research/statistical_auditor.py
Calculate:
- trades count
- win rate
- profit factor
- expectancy R
- average win R
- average loss R
- max drawdown
- Sharpe approximation
- Sortino approximation
- longest losing streak
- stability score

3. systems/research/walk_forward.py
Simple first version:
- split data into train/test windows
- run backtest per window
- report whether performance survives unseen data

4. systems/research/monte_carlo.py
Simple first version:
- shuffle trade R outcomes
- estimate possible drawdown distribution
- estimate risk of ruin placeholder

5. systems/research/performance_store.py
Use DuckDB or JSON/CSV first:
- save performance profiles
- load historical trust profile for a signal
- approve/reject using config/risk_rules.yaml thresholds

6. core/models/research.py
Create:
- TradeRecord
- BacktestResult
- PerformanceMetrics
- HistoricalTrustProfile

7. docs/BACKTEST_AND_TRUST.md
Explain:
- why backtest alone is not enough
- how costs are included
- how historical trust is used before paper/live
- why sample size matters

8. tests/test_research_layer.py
Cover:
- backtest creates trades
- costs reduce returns
- metrics calculate correctly
- weak profit factor fails trust
- low sample size fails trust
- performance store saves and loads

Acceptance criteria:
- pytest passes
- historical trust can approve/reject a signal
- no live trading exists
```

## Prompt 7 - Decision Orchestrator

```text
Use the Master Architecture Context above.

Build Phase 7: Decision Orchestrator.

Goal:
Create the central brain that coordinates all systems without mixing responsibilities.

Decision flow:
1. Load latest cleaned data
2. Run data quality monitor
3. Detect current regime
4. If regime not tradable, return no-trade decision
5. Load allowed strategies for regime
6. Generate candidate signals
7. Score signals
8. Load historical trust profile
9. Analyze present risk
10. Run funded rules and kill switch
11. Calculate position size
12. Return approved/rejected decision
13. Journal every decision

Implement:

1. core/models/decision.py
Create DecisionResult with:
- decision_id
- timestamp
- symbol
- regime_result
- candidate_strategies
- selected_signal
- historical_trust
- present_risk
- risk_approval
- final_action: no_trade, rejected, approved_paper, approved_live_blocked
- reasons

2. orchestrator/decision_engine.py
Coordinate systems. It may import systems. Systems should not import the orchestrator.

3. orchestrator/research_runner.py
Run historical backtests and save trust profiles.

4. orchestrator/paper_decision_runner.py
Runs decision engine but sends approved orders only to paper execution later.

5. docs/DECISION_FLOW.md
Explain the complete regime -> strategy -> risk -> execution approval flow.

6. tests/test_decision_engine.py
Cover:
- Q4 regime creates no-trade
- no approved strategy creates no-trade
- signal with weak historical trust is rejected
- signal with high present risk is rejected
- valid signal becomes approved_paper
- live remains blocked by default

Acceptance criteria:
- pytest passes
- decision engine has no FastAPI, HTML, or UI code
- decision engine does not place real orders
```

## Prompt 8 - UI Control Center

```text
Use the Master Architecture Context above.

Build Phase 8: FastAPI + HTML + Tailwind + HTMX Control Center.

Goal:
The user must see and control the system without editing code. UI is for visibility, safe config editing, and triggering approved research/paper workflows only. UI must not contain trading logic.

Frontend rules:
- Use plain server-rendered HTML templates.
- Use Tailwind CSS for styling.
- Use HTMX for partial page updates such as refreshing regime status, strategy table filters, risk panels, and decision logs.
- Use vanilla JavaScript only for small UI helpers such as confirm dialogs, local table filtering, or chart initialization.
- For the first local version, include Tailwind and HTMX from CDN in base.html. Do not add Node/Vite/Webpack unless explicitly requested later.
- Do not build React, Next.js, Vue, Angular, or a heavy frontend app.
- Do not use Streamlit.
- Do not put trading decisions inside templates or route handlers.

Backend/UI boundary:
- app/main.py starts FastAPI, mounts shared static files/templates, and registers each system's ui.py router.
- each system owns its own ui.py, page routes, API endpoints, templates, and HTMX partials.
- app/templates/ contains only the shared base layout unless a truly global page is needed.
- app/static/css/ contains Tailwind output or a simple local stylesheet during early development.
- app/static/js/ contains tiny vanilla JS helpers only.
- orchestrator/ remains responsible for decision flow.
- systems/ remains responsible for business logic.

Implement:

1. app/main.py
Create FastAPI app:
- configure app name
- mount /static
- register system routers from systems/*/ui.py
- add simple health endpoint /health

2. app/templates/base.html
Create the common layout:
- left sidebar navigation
- top status bar
- obvious Live Trading Disabled badge
- content block
- include HTMX
- include Tailwind
- include app static JS

3. systems/monitoring/ui.py
Own dashboard/system monitor routes:
- GET /
- GET /api/system/status
- GET /api/system/health
- GET /api/system/kill-switch
- GET /partials/system-summary

4. systems/monitoring/templates/dashboard.html
Show:
- current mode
- live trading disabled/enabled status
- current symbol
- latest regime
- data quality status
- kill switch status
- today's paper/live status placeholder

5. systems/regime/ui.py
Own regime routes:
- GET /regimes
- GET /api/regimes/latest
- GET /api/regimes/history
- GET /api/regimes/definitions
- GET /partials/latest-regime
- GET /partials/regime-feature-table

6. systems/regime/templates/regimes.html
Show:
- Q1-Q4 explanation
- M01-M13 explanation
- latest RegimeResult
- feature values
- reasons
- regime history chart if data exists

7. systems/strategy_router/ui.py
Own strategy registry/router routes:
- GET /strategies
- GET /api/strategies
- GET /api/strategies/by-regime/{regime_id}
- GET /api/strategies/{strategy_id}
- GET /partials/strategy-table
- POST /api/strategies/{strategy_id}/research-enable only for research display, not live approval

8. systems/strategy_router/templates/strategies.html
Show:
- all 208 strategy names
- filters by regime, family, status
- selected regime's 4 strategies
- status lifecycle
- enabled flag display
Editing enabled should be protected and should not allow live approval.

9. systems/research/ui.py
Own research/backtest routes:
- GET /backtester
- POST /api/backtests/run
- GET /api/backtests/results
- GET /api/backtests/results/{result_id}
- GET /partials/backtest-status

10. systems/research/templates/backtester.html
Allow:
- select symbol
- select strategy template
- select date range
- run backtest
- show metrics
- save historical trust profile

11. systems/risk/ui.py
Own risk routes:
- GET /risk
- GET /api/risk/rules
- POST /api/risk/rules/preview
- POST /api/risk/rules/save with validation and backup
- GET /api/risk/funded-rules
- GET /partials/risk-summary

12. systems/risk/templates/risk.html
Show/edit safely:
- base risk
- max daily loss
- max drawdown
- spread limits
- funded rules
- kill switch manual flag

13. systems/journal/ui.py
Own decision/journal routes:
- GET /decisions
- GET /api/decisions
- GET /api/decisions/{decision_id}
- POST /api/decisions/paper-run-one
- GET /partials/decision-log

14. systems/journal/templates/decisions.html
Show:
- approved trades
- rejected trades
- no-trade decisions
- reasons

15. systems/monitoring/templates/settings.html or app/templates/settings.html
Show config files and safe editable values. Use a global settings page only if it genuinely crosses multiple systems.

16. Each system's partials/ folder
Create the partial templates owned by that system:
- monitoring/partials/system_summary.html
- regime/partials/latest_regime.html
- strategy_router/partials/strategy_table.html
- risk/partials/risk_summary.html
- journal/partials/decision_log.html
- research/partials/backtest_status.html

17. app/static/css/app.css
Small project-specific styles only. Use Tailwind utility classes for most styling.

18. app/static/js/app.js
Small helpers only:
- confirm dangerous actions
- show toast messages
- initialize simple charts if needed

19. scripts/run_web.ps1
Runs:
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

20. docs/UI_CONTROL_CENTER.md
Explain UI pages and safety rules.

Acceptance criteria:
- FastAPI app starts at http://127.0.0.1:8000
- /health returns ok
- HTML pages render
- HTMX partial endpoints render
- no trading logic inside UI
- live trading disabled display is obvious
- all 208 strategy names visible
- regime reasons visible
- no React/Vue/Next/Streamlit added
```

## Prompt 9 - Paper Execution

```text
Use the Master Architecture Context above.

Build Phase 9: Paper execution only.

Goal:
Approved decisions should go to a fake broker/router first. This validates execution flow without risking money.

Implement:

1. systems/execution/paper_router.py
Responsibilities:
- accept approved DecisionResult
- simulate fill price using bid/ask/spread/slippage
- create paper order
- update paper position
- close position on stop/target if simulated
- return ExecutionResult

2. systems/execution/execution_profiler.py
Track:
- expected entry
- simulated fill
- slippage
- spread paid
- execution delay placeholder

3. systems/journal/journaler.py
Log:
- no-trade decisions
- rejected decisions
- approved decisions
- paper fills
- trade close results
- MFE/MAE placeholder

4. core/models/execution.py
Create:
- OrderRequest
- ExecutionResult
- PaperPosition

5. orchestrator/paper_trading_runner.py
Connect:
decision engine -> paper router -> journal

6. docs/PAPER_TRADING.md
Explain how paper trading differs from backtesting and live trading.

7. tests/test_paper_execution.py
Cover:
- rejected decision does not execute
- approved decision creates paper fill
- slippage recorded
- journal records fill

Acceptance criteria:
- pytest passes
- no MT5 orders
- no live broker connection
```

## Prompt 10 - MT5 Safe Integration Later

```text
Use the Master Architecture Context above.

Build Phase 10: MT5 integration in safe disabled mode.

Goal:
Prepare broker integration, but keep real live trading blocked by default.

Implement:

1. config/broker.yaml.example
Include:
- broker_type: mt5
- mt5_terminal_path placeholder
- account_mode: demo
- allow_live_trading: false
- allow_real_orders: false
- max_lot_size
- max_slippage_pips

2. systems/execution/mt5_router.py
Capabilities:
- initialize MT5 connection
- read account info
- read symbol info
- read latest tick
- dry-run order validation
- send_order method exists but refuses unless all safety flags true

3. systems/execution/broker_reconciliation.py
Compare:
- internal journal orders
- broker positions/orders
- mismatches

4. systems/execution/api_vault.py
Load credentials from environment only.
Never hardcode secrets.

5. docs/MT5_SAFE_MODE.md
Explain:
- demo first
- live disabled by default
- required safety flags
- funded rules before order send

6. tests/test_mt5_safety.py
Cover:
- send_order blocked when allow_live_trading false
- send_order blocked when allow_real_orders false
- dry-run validation works without placing order

Acceptance criteria:
- pytest passes
- real order sending is impossible by default
- no secrets in code
```
