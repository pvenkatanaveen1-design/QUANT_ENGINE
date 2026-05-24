# Regime 28 — Liquidity Crunch

**Practical quadrant:** Q4 — Q4 — Transition or Chaos

**Taxonomy section:** SECTION 5 — Sentiment / risk

## Definition (spec)

Liquidity Crunch — margin / funding stress; fire-sale correlations → 1

## Implementation

- **Code:** [`classify.py`](../classify.py) — `add_regime52_columns()`.
- **Parameters:** tune via [`Regime52Params`](../classify.py).
- **Context-only IDs:** some regimes need `ctx_*` columns on the DataFrame (macro, VIX, DXY, calendars). See the docstring on `add_regime52_columns`.

## Strategies (4 institutional / academic blueprints)

Each regime gets **four** linked strategies. Signals run **only** when `regime52_id` equals this regime (see [`strategies/runner.py`](../strategies/runner.py) and `build_scorecard_table`).

### `R28-S01` — Liquidity sweep fade — Liquidity Crunch

Fade engineered wicks / false breaks consistent with Liquidity Crunch (order flow narration; test empirically).

**References:** Evans & Lyons microstructure order flow — Hasbrouck (1991) information content of trades

### `R28-S02` — Vol-cluster straddle / flat gamma proxy fade — Liquidity Crunch

Stand aside or trade only mean-reversion spikes in Liquidity Crunch; vol desks reduce naked gamma.

**References:** Bollerslev (1986) GARCH / vol clustering — Barndorff-Nielsen & Shephard realized volatility

### `R28-S03` — Event reversal template — Liquidity Crunch

Fade post-event overreaction when Liquidity Crunch implies crowded positioning (news microstructure).

**References:** Brandt et al. post-earnings announcement drift vs reversal contexts — FX fix / macro surprise literature

### `R28-S04` — Regime-switch cautious drift — Liquidity Crunch

Small size carry until Markov / HMM-style state probabilities stabilise in Liquidity Crunch.

**References:** Hamilton (1989) regime switching (Econometrica) — Guidolin & Timmermann strategic asset allocation with regimes

## Scorecard (win-rate by R-multiple)

Run `python scripts/regime_strategy_scorecard.py` to get per-strategy trade counts and `wr_1r`…`wr_4r` (max favorable excursion in multiples of initial risk before stop).

## Quadrant deep-dive (if generated)

If you ran `_write_regime_docs.py`, extra notes may exist under project folder `Q4 — Transition or Chaos/regimes/r28.md` when this ID is in that quadrant’s list.
