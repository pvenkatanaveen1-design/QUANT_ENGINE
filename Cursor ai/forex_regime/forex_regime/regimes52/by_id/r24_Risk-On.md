# Regime 24 — Risk-On

**Practical quadrant:** Q1 — Q1 — Trend Low Volatility

**Taxonomy section:** SECTION 5 — Sentiment / risk

## Definition (spec)

Risk-On — pro-cyclical allocations; carry-seeking, credit tight spreads typical

## Implementation

- **Code:** [`classify.py`](../classify.py) — `add_regime52_columns()`.
- **Parameters:** tune via [`Regime52Params`](../classify.py).
- **Context-only IDs:** some regimes need `ctx_*` columns on the DataFrame (macro, VIX, DXY, calendars). See the docstring on `add_regime52_columns`.

## Strategies (4 institutional / academic blueprints)

Each regime gets **four** linked strategies. Signals run **only** when `regime52_id` equals this regime (see [`strategies/runner.py`](../strategies/runner.py) and `build_scorecard_table`).

### `R24-S01` — TSMOM / vol-managed pullback — Risk-On

Buy structural pullbacks while higher-timeframe trend holds in Risk-On; size down when realized variance spikes.

**References:** Moskowitz, Ooi & Pedersen (2012) 'Time Series Momentum' (JFE) — Barroso & Santa-Clara (2015) 'Momentum Has Its Moments' (JF)

### `R24-S02` — Channel / Donchian breakout — Risk-On

Enter on range expansion in the direction of Risk-On (institutional trend desks, managed futures CTAs).

**References:** Classic Donchian / Turtle-style breakout trend following — Krausz (1997) channel + MA hybrid literature

### `R24-S03` — Cross-sectional momentum add-on — Risk-On

Add on strong continuation closes when Risk-On supports risk appetite and breadth.

**References:** Jegadeesh & Titman (1993) 'Returns to Buying Winners…' (JF) — Asness, Moskowitz & Pedersen (2013) value and momentum everywhere

### `R24-S04` — Low-vol trend drift (defensive gross-up) — Risk-On

Hold / pyramid slowly in Risk-On; emphasis on not crowding into identical payoff tails.

**References:** Moreira & Muir (2017) volatility-managed portfolios — Kelly criterion & fractional sizing (practitioner risk books)

## Scorecard (win-rate by R-multiple)

Run `python scripts/regime_strategy_scorecard.py` to get per-strategy trade counts and `wr_1r`…`wr_4r` (max favorable excursion in multiples of initial risk before stop).

## Quadrant deep-dive (if generated)

If you ran `_write_regime_docs.py`, extra notes may exist under project folder `Q1 — Trend Low Volatility/regimes/r24.md` when this ID is in that quadrant’s list.
