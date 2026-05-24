# Quant Forex Regime And Strategy Blueprint

This document is a build specification for a Forex quant system that detects market regimes, selects strategies, runs backtests, stores analysis in a database, and displays results in a UI.

Important: research-backed does not mean guaranteed profitable. It means the concept has support in market research or professional practice and must still be validated on your symbols, broker feed, costs, slippage, sessions, and funded-account rules.

## 1. Core Market Model

The system starts with four base regimes:

| Base | Name | Meaning | Trading posture |
|---|---|---|---|
| Q1 | Trend + Low Volatility | Direction is clear, volatility is controlled | Trend continuation and pullback entries |
| Q2 | Trend + High Volatility | Direction is clear, volatility is expanded | Breakout, momentum, reduced size |
| Q3 | Range + Low Volatility | Direction is weak, volatility is compressed | Mean reversion and range fades |
| Q4 | Chaos / Transition / No-Trade | Direction, volatility, spread, or news risk is unstable | No trade, exit only, or wait |

The full library uses 52 regimes:

```text
4 base regimes x 13 modifiers = 52 regimes
```

The engine should observe all 52 regimes, but live trading should only allow regimes that pass backtest, walk-forward, Monte Carlo, and forward-demo checks.

## 2. Required Forex Inputs

Minimum MT5 data:

| Input | Source | Use |
|---|---|---|
| `open` | MT5 bars | candle structure |
| `high` | MT5 bars | breakout, ATR, swing detection |
| `low` | MT5 bars | breakout, sweep, stop distance |
| `close` | MT5 bars | returns, trend, mean reversion |
| `tick_volume` | MT5 bars | activity proxy, not true centralized volume |
| `spread` | MT5 tick/broker data | cost filter |
| `bid` / `ask` | MT5 ticks | execution and spread modeling |
| `time` | MT5 bars/ticks | sessions, kill zones, news windows |

Optional but valuable:

| Input | Use |
|---|---|
| Economic calendar | news guard and event regime |
| CME FX futures volume | better volume confirmation for major FX pairs |
| DXY / USD index proxy | USD shock filter |
| Gold / oil / yields / equity indices | macro risk context |
| Broker execution logs | slippage, rejection, latency, fill quality |

## 3. Forex Terms Used In The System

| Term | Meaning |
|---|---|
| `pip` | Standard price movement unit. For most FX pairs, 0.0001. For JPY pairs, 0.01. |
| `point` | Broker quote increment. Often 1/10 pip on 5-digit brokers. |
| `spread` | Ask minus bid. Direct trading cost. |
| `slippage` | Difference between expected and actual fill price. |
| `swap` | Overnight financing cost or credit. |
| `lot` | Trade size. Standard lot is usually 100,000 base currency units. |
| `R` | Risk unit. If stop loss risks 100 currency units, a 200 profit is `+2R`. |
| `MFE` | Maximum favorable excursion during trade. |
| `MAE` | Maximum adverse excursion during trade. |
| `kill zone` | High-activity session window. In code, treat it as a measurable session/time window, not magic. |
| `liquidity sweep` | Price breaks prior swing high/low and closes back inside, suggesting stop-run behavior. |
| `institutional trap` | Retail term. Convert to testable rules: sweep, rejection, abnormal spread, failed breakout, volume/tick activity. |

## 4. Time Series Formulas

Use only past data. Never use future candles in features.

### Returns

```text
simple_return_t = close_t / close_t-1 - 1
log_return_t = ln(close_t / close_t-1)
```

### True Range And ATR

```text
TR_t = max(
  high_t - low_t,
  abs(high_t - close_t-1),
  abs(low_t - close_t-1)
)

ATR_N = average(TR over N bars)
```

Typical `N`: 14, 20, 50.

### Realized Volatility

```text
realized_vol_N = sqrt(sum(log_return_i^2 over N bars))
```

For annualized volatility:

```text
annualized_vol = std(log_returns_N) * sqrt(periods_per_year)
```

### Volatility Percentile

```text
vol_percentile_t = percentile_rank(ATR_N / close_t, lookback=252 bars or more)
```

Initial thresholds:

```text
low_vol = vol_percentile < 40
normal_vol = 40 <= vol_percentile <= 70
high_vol = vol_percentile > 70
extreme_vol = vol_percentile > 90
```

### Trend Efficiency

```text
trend_efficiency_N =
  abs(close_t - close_t-N) /
  sum(abs(close_i - close_i-1), i=t-N+1..t)
```

Initial thresholds:

```text
trend = trend_efficiency > 0.35
range = trend_efficiency < 0.20
transition = 0.20 <= trend_efficiency <= 0.35
```

### Linear Regression Slope Score

```text
slope_N = linear_regression_slope(close over N bars)
slope_score = slope_N / ATR_N
```

Initial thresholds:

```text
uptrend = slope_score > +0.05
downtrend = slope_score < -0.05
flat = abs(slope_score) <= 0.05
```

### ADX Trend Strength

ADX is a standard trend-strength indicator based on directional movement and true range.

Initial thresholds:

```text
weak_trend = ADX_14 < 18
developing_trend = 18 <= ADX_14 < 25
strong_trend = ADX_14 >= 25
very_strong_trend = ADX_14 >= 35
```

### Bollinger Z-Score

```text
mid = SMA(close, N)
std = standard_deviation(close, N)
zscore = (close_t - mid) / std
upper_band = mid + k * std
lower_band = mid - k * std
```

Typical values:

```text
N = 20
k = 2
overbought = zscore > +2
oversold = zscore < -2
```

### Donchian Channel

```text
donchian_high_N = max(high over N bars)
donchian_low_N = min(low over N bars)
breakout_long = close_t > donchian_high_N_previous
breakout_short = close_t < donchian_low_N_previous
```

Typical `N`: 20, 55.

### Spread Stress

```text
spread_points = ask - bid
spread_z = (spread_t - mean(spread_N)) / std(spread_N)
spread_percentile = percentile_rank(spread_t, lookback=N)
```

Initial thresholds:

```text
normal_spread = spread_percentile < 70
warning_spread = 70 <= spread_percentile < 90
stress_spread = spread_percentile >= 90 or spread_z > 2
```

### Jump / Shock Detection

```text
jump_z = abs(log_return_t) / std(log_return_N)
```

Initial thresholds:

```text
jump_warning = jump_z > 2
jump_shock = jump_z > 3
```

### Wick / Rejection Ratio

```text
candle_range = high_t - low_t
body = abs(close_t - open_t)
upper_wick = high_t - max(open_t, close_t)
lower_wick = min(open_t, close_t) - low_t

upper_wick_ratio = upper_wick / candle_range
lower_wick_ratio = lower_wick / candle_range
body_ratio = body / candle_range
```

Initial thresholds:

```text
strong_rejection = wick_ratio > 0.55 and body_ratio < 0.45
```

### Liquidity Sweep

Bullish sweep:

```text
previous_swing_low = lowest low over swing lookback before current candle

bullish_sweep =
  low_t < previous_swing_low
  and close_t > previous_swing_low
  and lower_wick_ratio > 0.45
  and spread_percentile < 80
```

Bearish sweep:

```text
previous_swing_high = highest high over swing lookback before current candle

bearish_sweep =
  high_t > previous_swing_high
  and close_t < previous_swing_high
  and upper_wick_ratio > 0.45
  and spread_percentile < 80
```

### Breakout Failure

```text
failed_long_breakout =
  high_t > previous_range_high
  and close_t < previous_range_high

failed_short_breakout =
  low_t < previous_range_low
  and close_t > previous_range_low
```

### Time Series Momentum

```text
ts_momentum_N = close_t / close_t-N - 1

long_bias = ts_momentum_N > threshold
short_bias = ts_momentum_N < -threshold
```

Common lookbacks to test:

```text
20 bars, 50 bars, 100 bars, 200 bars
```

### Mean Reversion Score

```text
mean_reversion_score = -zscore

long_reversion = zscore < -2 and regime is range
short_reversion = zscore > +2 and regime is range
```

### Session Features

The system should store session label for every bar:

```text
Asia
London_PreOpen
London_Open
London_Mid
London_NY_Overlap
NY_Open
NY_Late
Rollover
Weekend_Close_Risk
```

The exact session times must be configurable because broker server time differs.

## 5. Base Regime Classification

### Q1: Trend + Low Volatility

```text
Q1 =
  trend_efficiency_N > 0.35
  and ADX_14 >= 20
  and vol_percentile < 60
  and spread_percentile < 80
  and jump_z <= 2
```

### Q2: Trend + High Volatility

```text
Q2 =
  trend_efficiency_N > 0.35
  and ADX_14 >= 25
  and vol_percentile >= 60
  and spread_percentile < 90
  and no_extreme_news_lock
```

### Q3: Range + Low Volatility

```text
Q3 =
  trend_efficiency_N < 0.25
  and ADX_14 < 20
  and vol_percentile < 60
  and price_inside_range
  and spread_percentile < 80
```

### Q4: Chaos / Transition / No-Trade

```text
Q4 =
  spread_percentile >= 90
  or jump_z > 3
  or news_lock_active
  or contradictory_signals
  or volatility_extreme
  or liquidity_too_low
  or data_quality_bad
```

Contradictory signals example:

```text
trend_efficiency says trend
but ADX falling sharply
and price repeatedly rejects both sides
and volatility expands without directional follow-through
```

## 6. The 13 Modifiers

| Modifier ID | Name | Logic |
|---|---|---|
| M01 | Clean Liquid Market | normal spread, normal jump, no news lock, normal session |
| M02 | Compression | Bollinger bandwidth percentile low, ATR percentile low |
| M03 | Asia Session | bar time inside Asia session |
| M04 | London Open | bar time inside London open kill zone |
| M05 | London-NY Overlap | bar time inside overlap session |
| M06 | NY Late / Rollover | late NY, rollover, weak liquidity |
| M07 | Pre-News | event within configured pre-news window |
| M08 | Post-News | event recently passed, volatility still elevated |
| M09 | Liquidity Sweep | bullish or bearish sweep detected |
| M10 | Spread Stress | spread percentile high |
| M11 | Trend Exhaustion | extended move, divergence, high MFE, weakening ADX |
| M12 | Multi-Timeframe Agreement | lower and higher timeframes agree |
| M13 | USD / Correlation Shock | USD basket move, correlated-pair stress, risk-off signal |

## 7. The 52 Regimes And Strategy Logic

Each regime gets up to 4 strategy candidates. The backtest ranks them by expectancy, drawdown, stability, and forward performance.

Live rule:

```text
current_regime = regime_detector(latest_data)
allowed_strategies = strategy_router[current_regime]

Only strategies mapped to current_regime are evaluated.
All other strategies are disabled for that decision cycle.
```

This prevents the system from running trend strategies in range markets, range strategies in trend markets, or any strategy in no-trade regimes.

Recommended live decision flow:

```text
1. Fetch latest bars/ticks
2. Update features
3. Detect current base regime: Q1, Q2, Q3, or Q4
4. Detect current modifier: M01-M13
5. Build regime_id, example: Q1_M04
6. Load only that regime's strategy playbook
7. Evaluate only the 0-4 allowed strategies for that regime
8. Score candidate signals
9. Apply risk checks
10. Apply funded rules
11. Apply kill switch
12. Send approved order to order manager/execution
13. Log decision even if no trade
```

Strategy permissions:

```text
Q1 regimes = trend and continuation strategies only
Q2 regimes = momentum/breakout strategies with reduced size
Q3 regimes = range and mean-reversion strategies only
Q4 regimes = no-trade or defensive actions only
```

Each regime should have one primary strategy, two backup strategies, and one defensive fallback:

```text
primary_strategy = first choice for the regime
secondary_strategy = used if primary conditions are absent
confirmation_strategy = used only if extra filters agree
fallback_strategy = no trade, exit only, or reduce risk
```

### M01 Clean Liquid Market

| Regime | Logic | Strategy candidates |
|---|---|---|
| Q1_M01 | Trend, low vol, clean spread | EMA pullback, Donchian continuation, break-retest, time-series momentum |
| Q2_M01 | Trend, high vol, clean spread | ATR breakout, momentum continuation, volatility pullback, trailing runner |
| Q3_M01 | Range, low vol, clean spread | Bollinger fade, RSI range fade, support/resistance fade, VWAP/session mean fade |
| Q4_M01 | Clean but unclear structure | no trade, wait for Q1-Q3, reduce exposure, observe only |

### M02 Compression

| Regime | Logic | Strategy candidates |
|---|---|---|
| Q1_M02 | Trend pauses with compressed volatility | trend continuation after squeeze, EMA pullback, inside-bar break, Donchian break |
| Q2_M02 | Compression then expansion in trend | ATR expansion breakout, stop-entry breakout, volatility-scaled momentum, trail-only runner |
| Q3_M02 | Tight range and low volatility | range fade, mean reversion, boundary scalp, no trade until edge proven |
| Q4_M02 | Compression with unstable signals | wait, no trade, alert only, classify after breakout |

### M03 Asia Session

| Regime | Logic | Strategy candidates |
|---|---|---|
| Q1_M03 | Slow trend during Asia | small trend continuation, carry drift, EMA pullback, no-trade if spread wide |
| Q2_M03 | High vol during Asia | reduced-size momentum, event-driven continuation, no trade, trail existing only |
| Q3_M03 | Classic Asia range | Asian range fade, Bollinger fade, liquidity boundary fade, time stop |
| Q4_M03 | Thin liquidity or random movement | no trade, reduce risk, wait for London, close weak trades |

### M04 London Open

| Regime | Logic | Strategy candidates |
|---|---|---|
| Q1_M04 | Trend into London open | break-retest, opening range continuation, EMA pullback, sweep continuation |
| Q2_M04 | High-vol London expansion | opening range breakout, ATR breakout, momentum impulse, partial exits |
| Q3_M04 | London tests Asia range but no trend | Asia high/low sweep reversal, failed breakout fade, range expansion fade, wait-confirmation |
| Q4_M04 | First 5-15 min noisy or spread unstable | wait, no trade, observe sweep, trade only after confirmation |

### M05 London-NY Overlap

| Regime | Logic | Strategy candidates |
|---|---|---|
| Q1_M05 | Trend with strong liquidity | trend continuation, pullback continuation, breakout retest, pyramiding only if allowed |
| Q2_M05 | Large directional volatility | momentum breakout, ATR trailing, volatility pullback, reduced position sizing |
| Q3_M05 | Range starts breaking or rejecting | range fade if no breakout, failed breakout, session mean reversion, no trade if mixed |
| Q4_M05 | News/event overlap confusion | no trade, close risk, wait for spread normalization, observe only |

### M06 NY Late / Rollover

| Regime | Logic | Strategy candidates |
|---|---|---|
| Q1_M06 | Existing trend late session | trail existing, no new entry, time-based exit, small continuation only if tested |
| Q2_M06 | High vol late session | no new entry, reduce risk, trail, close before rollover |
| Q3_M06 | Low-vol late range | small mean reversion only if spread normal, time exit, no trade, close weak trades |
| Q4_M06 | Rollover spread/liquidity stress | no trade, kill new orders, close risky trades, wait |

### M07 Pre-News

| Regime | Logic | Strategy candidates |
|---|---|---|
| Q1_M07 | Trend before major news | reduce size, no new trade, tighten/partial exit, wait |
| Q2_M07 | Volatile trend before news | no trade, reduce exposure, close risky positions, wait |
| Q3_M07 | Range before news | no trade, cancel pending orders, wait, observe breakout levels |
| Q4_M07 | Event risk dominant | hard no trade, news lock, kill new orders, exit if rules require |

### M08 Post-News

| Regime | Logic | Strategy candidates |
|---|---|---|
| Q1_M08 | News confirms trend after spread normalizes | continuation after retest, EMA pullback, breakout continuation, reduced size |
| Q2_M08 | Strong news impulse | momentum continuation, ATR breakout, trailing runner, reduced size |
| Q3_M08 | News spike returns to range | fade only after volatility normalizes, failed breakout fade, z-score mean reversion, wait |
| Q4_M08 | Spread/jump still unstable | no trade, wait for normalization, observe only, kill new orders |

### M09 Liquidity Sweep

| Regime | Logic | Strategy candidates |
|---|---|---|
| Q1_M09 | Sweep against trend then continuation | sweep pullback entry, break-retest, trend continuation, stop below sweep |
| Q2_M09 | Sweep then high-vol impulse | sweep continuation, ATR momentum, reduced size, fast partials |
| Q3_M09 | Sweep at range edge | sweep reversal, failed breakout fade, Bollinger fade, range target |
| Q4_M09 | Sweep without confirmation or bad spread | wait, no trade, require next-bar confirmation, observe only |

### M10 Spread Stress

| Regime | Logic | Strategy candidates |
|---|---|---|
| Q1_M10 | Trend but execution cost high | no new trade, reduce size, wait for spread normal, trail existing |
| Q2_M10 | High volatility and high spread | no trade, kill new orders, close by rules, wait |
| Q3_M10 | Range but spread ruins edge | no trade, skip scalps, wait, observe only |
| Q4_M10 | Cost/liquidity stress dominant | kill switch candidate, no trade, data warning, broker warning |

### M11 Trend Exhaustion

| Regime | Logic | Strategy candidates |
|---|---|---|
| Q1_M11 | Trend mature but controlled | smaller pullback, trail, partial exit, no fresh breakout chase |
| Q2_M11 | Volatile exhaustion | trailing stop, reversal only after confirmation, no chase, reduce size |
| Q3_M11 | Exhaustion into range | mean reversion, range fade, divergence fade if tested, time stop |
| Q4_M11 | Exhaustion plus instability | no trade, wait, protect profits, reclassify |

### M12 Multi-Timeframe Agreement

| Regime | Logic | Strategy candidates |
|---|---|---|
| Q1_M12 | Higher and lower timeframe trend agree | full trend continuation, pullback, break-retest, time-series momentum |
| Q2_M12 | Multi-timeframe trend plus high vol | ATR breakout, reduced-size momentum, trailing runner, volatility pullback |
| Q3_M12 | Multiple timeframes range-bound | range fade, mean reversion, boundary reversal, smaller targets |
| Q4_M12 | Timeframes conflict | no trade, wait for alignment, reduce risk, observe only |

### M13 USD / Correlation Shock

| Regime | Logic | Strategy candidates |
|---|---|---|
| Q1_M13 | Trend aligns with USD/macro flow | USD-aligned continuation, pullback, basket-confirmed breakout, reduced correlated exposure |
| Q2_M13 | Strong USD shock or risk-off trend | momentum continuation, ATR breakout, reduced basket risk, trail |
| Q3_M13 | Range but cross-pair correlation abnormal | pair-neutral mean reversion, reduce exposure, no trade if basket risk high, observe |
| Q4_M13 | Correlation shock unstable | no trade, close correlated risk, kill new basket trades, wait |

## 8. Strategy Rule Templates

## 8A. Live Regime Strategy Router

This is the exact live mapping. When the detected regime is `regime_id`, only these four strategies are available.

Slot meaning:

```text
Primary = first strategy evaluated for this regime
Secondary = backup if primary setup is absent
Confirmation = stricter setup that needs extra confirmation
Fallback = defensive action, no-trade, or lower-risk behavior
```

| Regime | Primary | Secondary | Confirmation | Fallback |
|---|---|---|---|---|
| Q1_M01 | EMA Pullback Continuation | Break-Retest Continuation | Time-Series Momentum | Trail / No New Trade |
| Q2_M01 | ATR Momentum Breakout | Donchian Breakout | Volatility Pullback Continuation | Reduced Size / No Trade |
| Q3_M01 | Bollinger Mean Reversion | RSI Range Fade | Session Mean Fade | No Trade If Range Breaks |
| Q4_M01 | No-Trade Defensive | Wait For Reclassification | Exit Weak Trades | Block New Orders |
| Q1_M02 | Squeeze Trend Continuation | Inside-Bar Breakout | Donchian Breakout | Wait For Expansion |
| Q2_M02 | ATR Expansion Breakout | Stop-Entry Breakout | Momentum Continuation | Reduced Size / Fast Trail |
| Q3_M02 | Range Boundary Fade | Bollinger Mean Reversion | Compression Break Failure Fade | No Trade Until Edge Proven |
| Q4_M02 | No-Trade Defensive | Wait For Breakout Close | Observe Only | Block New Orders |
| Q1_M03 | Small EMA Pullback | Carry Drift Continuation | Time-Series Momentum | No Trade If Spread Wide |
| Q2_M03 | Reduced-Size Momentum | Event Continuation | ATR Trail Existing | No New Trade |
| Q3_M03 | Asian Range Fade | Bollinger Mean Reversion | Liquidity Boundary Fade | Time Stop / No Trade |
| Q4_M03 | No-Trade Defensive | Wait For London | Close Weak Trades | Block New Orders |
| Q1_M04 | London Break-Retest | Opening Range Continuation | Sweep Continuation | Wait First 5-15 Minutes |
| Q2_M04 | Opening Range Breakout | ATR Momentum Breakout | Impulse Pullback | Reduced Size / Partial Exit |
| Q3_M04 | Asia High/Low Sweep Reversal | Failed Breakout Fade | Range Expansion Fade | Wait Confirmation |
| Q4_M04 | No-Trade First Minutes | Wait For Spread Normal | Observe Sweep Only | Block New Orders |
| Q1_M05 | Trend Continuation | Pullback Continuation | Break-Retest Continuation | Trail Existing |
| Q2_M05 | Momentum Breakout | ATR Trailing Runner | Volatility Pullback | Reduced Position Size |
| Q3_M05 | Failed Breakout Fade | Session Mean Reversion | Range Fade | No Trade If Mixed |
| Q4_M05 | No-Trade Defensive | Wait News/Spread Normal | Close Risk | Block New Orders |
| Q1_M06 | Trail Existing Trend | Time-Based Exit | Small Pullback Continuation | No New Trade |
| Q2_M06 | Protect Profit / Trail | Reduce Exposure | Close Before Rollover | No New Trade |
| Q3_M06 | Small Mean Reversion | Session Mean Fade | Time-Boxed Range Fade | No Trade If Spread Rises |
| Q4_M06 | Rollover No-Trade | Kill New Orders | Close Risky Trades | Block New Orders |
| Q1_M07 | Reduce Trend Exposure | Tighten / Partial Exit | Wait News Result | No New Trade |
| Q2_M07 | Close Or Reduce Risk | Cancel Pending Orders | Wait News Result | Hard News Lock |
| Q3_M07 | Cancel Range Entries | Mark Levels Only | Wait News Result | Hard News Lock |
| Q4_M07 | Hard News Lock | Block New Orders | Close By Rule | Observe Only |
| Q1_M08 | Post-News Retest Continuation | EMA Pullback Continuation | Breakout Continuation | Reduced Size |
| Q2_M08 | Post-News Momentum Continuation | ATR Momentum Breakout | Trailing Runner | Reduced Size / Wait Spread |
| Q3_M08 | Failed News Breakout Fade | Volatility-Normalized Mean Reversion | Z-Score Fade | Wait For Vol Normal |
| Q4_M08 | No-Trade Post-News | Wait Spread Normal | Observe Only | Block New Orders |
| Q1_M09 | Trend-Side Sweep Entry | Sweep Pullback Continuation | Break-Retest Continuation | No Trade Without Confirmation |
| Q2_M09 | Sweep Momentum Continuation | ATR Impulse Continuation | Fast Partial Exit Runner | Reduced Size |
| Q3_M09 | Liquidity Sweep Reversal | Failed Breakout Fade | Bollinger Range Fade | No Trade Without Confirmation |
| Q4_M09 | Wait Retest | No-Trade Defensive | Observe Only | Block New Orders |
| Q1_M10 | Trail Existing Trend | Wait Spread Normal | Reduce Size Existing | No New Trade |
| Q2_M10 | No-Trade Defensive | Kill New Orders | Close By Rule | Block New Orders |
| Q3_M10 | No-Trade Defensive | Skip Scalps | Wait Spread Normal | Block New Orders |
| Q4_M10 | Kill Switch Candidate | No-Trade Defensive | Broker/Data Warning | Block New Orders |
| Q1_M11 | Smaller Pullback Continuation | Trail / Partial Exit | No Fresh Breakout Chase | Reduce Risk |
| Q2_M11 | Trail Volatile Trend | Exhaustion Reversal After Confirmation | Protect Profit | No Chase |
| Q3_M11 | Trend Exhaustion Mean Reversion | Range Fade | Divergence Fade If Tested | Time Stop |
| Q4_M11 | No-Trade Defensive | Protect Profit | Wait Reclassification | Block New Orders |
| Q1_M12 | Full Trend Continuation | EMA Pullback | Break-Retest Continuation | Trail Existing |
| Q2_M12 | Multi-Timeframe ATR Breakout | Reduced-Size Momentum | Volatility Pullback | Trail Runner |
| Q3_M12 | Multi-Timeframe Range Fade | Bollinger Mean Reversion | Boundary Reversal | Smaller Targets |
| Q4_M12 | No-Trade On Conflict | Wait Alignment | Reduce Risk | Block New Orders |
| Q1_M13 | USD-Aligned Trend Continuation | Basket-Confirmed Pullback | Breakout With Correlation Check | Reduce Correlated Exposure |
| Q2_M13 | USD Shock Momentum | ATR Breakout With Basket Limit | Trail Strong Impulse | Reduce Basket Risk |
| Q3_M13 | Pair-Neutral Mean Reversion | Range Fade With Correlation Limit | Reduce Exposure | No Trade If Basket Risk High |
| Q4_M13 | Correlation Shock No-Trade | Close Correlated Risk | Wait Shock Normalize | Block New Orders |

Implementation rule:

```text
def get_allowed_strategies(regime_id):
    return strategy_router[regime_id]
```

No strategy should be allowed to evaluate unless it appears in the router for the current live regime.

## 8B. Strategy Rule Templates

### S01 EMA Pullback Continuation

Best regimes: Q1, Q1_M12, Q1_M04, Q1_M05.

Long logic:

```text
trend_up =
  close > EMA_50
  and EMA_20 > EMA_50
  and slope_score > 0
  and ADX_14 >= 20

pullback =
  low <= EMA_20 or low <= EMA_50
  and close > EMA_20

entry_long =
  trend_up
  and pullback
  and spread_percentile < 80
  and no_news_lock

stop = swing_low - 0.2 * ATR_14
target_1 = entry + 1R
target_2 = entry + 2R or trailing ATR stop
```

Short logic mirrors long logic.

### S02 Donchian Breakout

Best regimes: Q1, Q2, compression, London/NY overlap.

```text
long_breakout =
  close > highest_high(N) from previous bars
  and ADX_14 rising
  and ATR_percentile not extreme
  and spread_percentile < 80

stop = min(ATR stop, channel midpoint, swing low)
exit = opposite channel break or ATR trailing stop
```

### S03 Opening Range Breakout

Best regimes: London open, NY open, high-vol trend.

```text
opening_range_high = high of first X minutes
opening_range_low = low of first X minutes

long =
  close > opening_range_high
  and range_size >= minimum_ATR_fraction
  and spread normal
  and no high-impact news lock

stop = opening_range_mid or opening_range_low
exit = fixed R target, trailing stop, or session time exit
```

### S04 Break-Retest Continuation

Best regimes: Q1/Q2 clean trend.

```text
breakout = close > prior_resistance
retest = low <= prior_resistance and close > prior_resistance
entry = retest confirmation candle closes bullish
stop = below retest low
target = next liquidity level or 2R
```

### S05 ATR Momentum Breakout

Best regimes: Q2.

```text
range_expansion =
  TR_t > 1.5 * ATR_14
  and close near candle extreme

long =
  range_expansion
  and close > previous_high
  and ADX_14 >= 25
  and spread normal

position_size = base_size * volatility_adjustment
```

### S06 Time-Series Momentum

Best regimes: Q1/Q2, multi-timeframe agreement.

```text
momentum = close / close_N_bars_ago - 1

long = momentum > threshold and trend filters agree
short = momentum < -threshold and trend filters agree
```

### S07 Bollinger Mean Reversion

Best regimes: Q3.

```text
long =
  zscore < -2
  and ADX_14 < 20
  and trend_efficiency < 0.25
  and spread normal

exit = zscore >= 0 or opposite band or time stop
stop = beyond range boundary + ATR buffer
```

### S08 RSI Range Fade

Best regimes: Q3.

```text
long =
  RSI_14 < 30
  and price near range low
  and ADX_14 < 20

short =
  RSI_14 > 70
  and price near range high
  and ADX_14 < 20
```

### S09 Asian Range Fade

Best regimes: Q3_M03.

```text
asia_range_high = max(high during Asia window)
asia_range_low = min(low during Asia window)

long =
  price tests asia_range_low
  and sweep/rejection detected
  and spread normal

short =
  price tests asia_range_high
  and sweep/rejection detected
  and spread normal

exit = range midpoint or opposite side
```

### S10 Liquidity Sweep Reversal

Best regimes: Q3_M09 and selected Q1 pullbacks.

```text
bullish_entry =
  bullish_sweep
  and next candle closes above sweep candle midpoint
  and spread normal
  and no news lock

stop = sweep low - ATR buffer
target = range midpoint, opposite range side, or fixed R
```

### S11 Failed Breakout Fade

Best regimes: Q3, Q3_M04, Q3_M09.

```text
failed_long_breakout =
  high > prior_range_high
  and close < prior_range_high

short_entry =
  failed_long_breakout
  and ADX_14 < 25
  and spread normal
```

### S12 Post-News Continuation

Best regimes: Q1_M08, Q2_M08.

```text
news_wait_passed =
  minutes_since_event >= minimum_wait
  and spread_percentile < 80

long =
  news_wait_passed
  and impulse_direction_up
  and retest_holds
  and volatility_not_extreme
```

### S13 Trend Exhaustion Mean Reversion

Best regimes: Q3_M11 and carefully tested Q2_M11.

```text
exhaustion =
  move_from_EMA_50 > k * ATR_14
  and wick_rejection
  and ADX_14 flattening/falling

entry = reversal confirmation
stop = beyond exhaustion extreme
target = EMA_20 or EMA_50
```

### S14 Session VWAP / Session Mean Fade

Best regimes: Q3 clean liquid sessions.

```text
session_mean = average price or VWAP proxy during session
distance = (close - session_mean) / ATR_14

fade =
  abs(distance) > threshold
  and range regime
  and no news lock
```

### S15 Correlation / Basket Risk Strategy

Best regimes: M13.

```text
usd_exposure =
  sum(direction_weight for all USD-related open trades)

allow_trade =
  abs(usd_exposure_after_trade) <= max_usd_exposure
  and correlated_pair_count <= max_correlated_pairs
```

This is more risk/control than alpha.

### S16 No-Trade / Defensive Strategy

Best regimes: Q4 and stress modifiers.

```text
no_trade =
  Q4
  or spread_stress
  or news_lock
  or data_quality_bad
  or kill_switch_active

actions =
  cancel pending orders
  block new orders
  optionally reduce or close risk by rule
```

## 9. Kill Zone Logic

In this system, kill zone means a configurable session window with historically different liquidity/volatility.

Example configurable windows:

```text
Asia range: 00:00-06:00 London time
London open: 07:00-10:00 London time
New York open: 13:00-16:00 London time
London-NY overlap: 13:00-16:00 London time
Rollover caution: broker rollover window
```

Backtest must compare:

```text
killzone_on
killzone_off
London only
NY only
Overlap only
Asia only
all sessions
```

## 10. Risk Rules

### Position Sizing

```text
risk_amount = account_equity * risk_percent
stop_distance_price = abs(entry_price - stop_price)
pip_value = broker pip value per lot
lot_size = risk_amount / (stop_distance_pips * pip_value)
```

Initial funded-account-friendly settings:

```text
risk_per_trade = 0.25% to 0.50%
max_daily_loss_soft_stop = 50% to 70% of firm daily loss limit
max_open_trades = 1 to 3
max_correlated_trades = 1 or 2
max_spread_percentile = 80 for entries
news_blackout = 15-30 min before and after high-impact news
```

### Volatility Adjusted Sizing

```text
vol_adjustment = target_ATR_percentile / current_ATR_percentile
adjusted_size = base_size * clamp(vol_adjustment, min=0.25, max=1.0)
```

### Kill Switch Conditions

```text
kill_switch =
  daily_loss >= daily_loss_limit
  or consecutive_losses >= max_consecutive_losses
  or spread_percentile >= 95
  or broker_disconnected
  or data_stale
  or slippage_z > 3
  or account_equity_mismatch
  or news_lock_hard_stop
```

## 11. Backtest Design

Every backtest must include costs:

```text
entry_price_long = ask or close + spread/2 + slippage
exit_price_long = bid or close - spread/2 - slippage
entry_price_short = bid or close - spread/2 - slippage
exit_price_short = ask or close + spread/2 + slippage
```

Run matrix:

```text
symbols = EURUSD, GBPUSD, USDJPY, XAUUSD, etc.
timeframes = M5, M15, M30, H1, H4
date ranges = in-sample, out-of-sample, walk-forward
regimes = all 52
strategies = strategy candidates per regime
filters = killzone on/off, news on/off, spread filter on/off
```

Minimum sample rules:

```text
minimum_trades_per_test = 100
better_minimum = 200+
minimum_forward_demo = 2-3 months
serious_forward_demo = 6 months
```

## 12. Metrics To Store In DB

### Backtest Run Table

```text
run_id
symbol
timeframe
start_time
end_time
initial_balance
spread_model
slippage_model
commission_model
swap_model
killzone_mode
news_filter_mode
regime_version
strategy_version
created_at
```

### Trade Table

```text
trade_id
run_id
symbol
timeframe
entry_time
exit_time
direction
entry_price
exit_price
stop_loss
take_profit
lot_size
risk_amount
pnl
r_multiple
regime_id
modifier_id
strategy_id
entry_reason
exit_reason
failure_reason
mfe
mae
spread_at_entry
slippage
session_label
news_distance_minutes
```

### Regime Performance Table

```text
run_id
regime_id
strategy_id
trades
win_rate
profit_factor
expectancy
avg_r
max_drawdown
sharpe
sortino
calmar
avg_hold_time
max_consecutive_losses
stability_score
pass_fail_status
```

## 13. Performance Formulas

```text
win_rate = winning_trades / total_trades
loss_rate = losing_trades / total_trades
avg_win = average(profit of winners)
avg_loss = average(abs(loss of losers))
expectancy = win_rate * avg_win - loss_rate * avg_loss
profit_factor = gross_profit / abs(gross_loss)
R_multiple = pnl / initial_trade_risk
avg_R = average(R_multiple)
max_drawdown = max(peak_equity - trough_equity)
return_over_drawdown = net_profit / max_drawdown
```

Sharpe:

```text
sharpe = mean(strategy_returns - risk_free_rate) / std(strategy_returns)
```

Sortino:

```text
sortino = mean(strategy_returns - target_return) / downside_deviation
```

Calmar:

```text
calmar = annualized_return / max_drawdown
```

Regime edge:

```text
edge_by_regime = expectancy_in_regime - expectancy_all_trades
```

Filter value:

```text
filter_value = expectancy_with_filter - expectancy_without_filter
```

## 14. Failure Reason Tags

Every losing trade should be tagged with one primary reason and optional secondary reasons:

```text
wrong_regime
late_entry
false_breakout
failed_retest
spread_too_high
slippage_too_high
news_shock
stop_too_tight
target_too_far
range_broke
trend_exhausted
low_liquidity
correlation_stack
session_decay
overfit_parameter
data_quality_issue
broker_execution_issue
```

Initial formulas:

```text
spread_too_high = spread_percentile_at_entry > 80
late_entry = entry_distance_from_breakout > 1.0 * ATR_14
stop_too_tight = MAE_before_profit < stop_distance and average_MAE_winners > stop_distance
target_too_far = MFE >= 1R but final trade loses
false_breakout = breakout entry and close returns inside range within K bars
wrong_regime = detected_regime_at_entry != best_regime_after_analysis
```

## 15. Probability, Permutation, And Robustness

### Monte Carlo Trade Shuffle

Shuffle trade order to estimate drawdown risk:

```text
for i in 1..num_simulations:
  shuffled_returns = random_permutation(trade_R_values)
  equity_curve = cumulative_sum(shuffled_returns)
  record max_drawdown, longest_loss_streak
```

### Bootstrap Confidence Interval

```text
sample trades with replacement
calculate expectancy for each sample
confidence_interval = percentile(expectancy_samples, 5%, 95%)
```

### Parameter Robustness

Do not trust one best parameter.

```text
test grid:
  EMA = 10, 20, 30
  ATR = 14, 20
  Donchian = 20, 55
  stop_ATR = 1.0, 1.5, 2.0
```

Prefer parameter zones where many nearby values work.

### Walk-Forward

```text
train window -> choose parameters
test next unseen window -> record result
roll forward -> repeat
```

## 16. Alpha And Time Series Derivatives

Useful derived features:

```text
return_lag_1
return_lag_3
return_lag_5
rolling_mean_return
rolling_volatility
ATR_percentile
slope_score
trend_efficiency
ADX
Bollinger_zscore
RSI
distance_from_EMA
distance_from_session_high
distance_from_session_low
wick_ratio
spread_percentile
jump_z
session_label
news_distance
multi_timeframe_alignment
correlation_exposure
```

Alpha feature examples:

```text
trend_alpha = slope_score * trend_efficiency * ADX_normalized
range_alpha = abs(zscore) * (1 - trend_efficiency)
breakout_alpha = channel_break_strength * volume_activity_score * spread_quality
sweep_alpha = wick_rejection_score * level_importance * confirmation_score
cost_penalty = spread_percentile + slippage_percentile
final_score = alpha_score - cost_penalty - risk_penalty
```

## 17. UI Pages

Minimum UI:

```text
System Heart Monitor
Data System
Regime Detector
Strategy Library
Backtest Lab
Regime Heatmap
Trade Journal
Risk Manager
Failure Analysis
Settings
```

Regime heatmap should show:

```text
regime_id
strategy_id
trades
expectancy
profit_factor
max_drawdown
win_rate
avg_R
filter_value
pass/fail
```

## 18. Pass / Fail Rules

A regime-strategy pair should not be enabled live unless:

```text
trades >= 100, preferably 200+
profit_factor >= 1.20 after costs
expectancy > 0
max_drawdown acceptable for funded rules
walk_forward positive
Monte Carlo drawdown acceptable
performance not dependent on one lucky trade
nearby parameters also work
forward demo does not collapse
```

Example status:

```text
PASS = eligible for demo
WATCH = more data needed
FAIL = not allowed
NO_TRADE = defensive regime
```

## 19. Research And Reference Sources

These sources support the broad concepts used in this blueprint. They do not prove any single retail strategy will be profitable.

Trend and time-series momentum:

- Moskowitz, Ooi, Pedersen, "Time Series Momentum": https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum
- Hurst, Ooi, Pedersen, "A Century of Evidence on Trend-Following Investing": https://www.aqr.com/Insights/Research/White-Papers/A-Century-of-Evidence-on-Trend-Following-Investing

Technical rules, moving averages, support/resistance:

- Brock, Lakonishok, LeBaron, "Simple Technical Trading Rules and the Stochastic Properties of Stock Returns": https://technicalanalysis.org.uk/support-and-resistance/BrockLakonishokLeBaron1992.pdf

Mean reversion and pairs-style logic:

- Gatev, Goetzmann, Rouwenhorst, "Pairs Trading: Performance of a Relative-Value Arbitrage Rule": https://papers.ssrn.com/sol3/papers.cfm?abstract_id=141615

FX order flow and microstructure:

- Evans and Lyons, "Order Flow and Exchange Rate Dynamics": https://www.nber.org/papers/w7317

Macro news and FX price discovery:

- Andersen, Bollerslev, Diebold, Vega, "Real-Time Price Discovery in Global Stock, Bond and Foreign Exchange Markets": https://www.federalreserve.gov/pubs/ifdp/2006/871/ifdp871.htm

Intraday FX behavior:

- Andersen and Bollerslev, "Deutsche Mark-Dollar Volatility: Intraday Activity Patterns, Macroeconomic Announcements, and Longer Run Dependencies": https://www.nber.org/papers/w5761

Regime switching:

- Hamilton, "A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle": https://www.jstor.org/stable/1912559

Backtest overfitting and false discovery:

- Bailey, Borwein, Lopez de Prado, Zhu, "The Probability of Backtest Overfitting": https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- White, "A Reality Check for Data Snooping": https://www.jstor.org/stable/2669586

Data / platform:

- MetaTrader 5 Python integration: https://www.mql5.com/en/docs/python_metatrader5
- Dukascopy historical data: https://www.dukascopy.com/swiss/english/marketwatch/historical/

Indicators:

- Average True Range / Wilder-style volatility logic: https://www.investopedia.com/terms/a/atr.asp
- Bollinger Bands: https://www.bollingerbands.com/bollinger-bands
- ADX: https://www.investopedia.com/terms/a/adx.asp

## 20. Build Order

Recommended system-by-system build:

```text
1. Data System
2. Regime System
3. Strategy System
4. Backtest System
5. Analysis DB
6. UI / Regime Heatmap
7. Risk System
8. Order Manager
9. Execution System
10. Kill Switch
11. Heart Monitor
```

First implementation target:

```text
EURUSD
M15
2-5 years historical bars if available
Q1-Q4 classification
13 modifiers
4-6 strategy templates
cost-adjusted backtest
DB storage
UI heatmap
```
