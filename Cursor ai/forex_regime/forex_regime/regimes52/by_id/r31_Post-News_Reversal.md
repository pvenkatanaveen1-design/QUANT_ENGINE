# Regime 31 — Post-News Reversal

**Practical quadrant:** Q4 — Q4 — Transition or Chaos

**Taxonomy section:** SECTION 6 — News / events

## Definition (spec)

Post-News Reversal — priced-in outcomes; mean reversion after volatility event

## Implementation

- **Code:** [`classify.py`](../classify.py) — `add_regime52_columns()`.
- **Parameters:** tune via [`Regime52Params`](../classify.py).
- **Context-only IDs:** some regimes need `ctx_*` columns on the DataFrame (macro, VIX, DXY, calendars). See the docstring on `add_regime52_columns`.

## Strategies (4 institutional / academic blueprints)

Each regime gets **four** linked strategies. Signals run **only** when `regime52_id` equals this regime (see [`strategies/runner.py`](../strategies/runner.py) and `build_scorecard_table`).

### `R31-S01` — Liquidity sweep fade — Post-News Reversal

Fade engineered wicks / false breaks consistent with Post-News Reversal (order flow narration; test empirically).

**References:** Evans & Lyons microstructure order flow — Hasbrouck (1991) information content of trades

### `R31-S02` — Vol-cluster straddle / flat gamma proxy fade — Post-News Reversal

Stand aside or trade only mean-reversion spikes in Post-News Reversal; vol desks reduce naked gamma.

**References:** Bollerslev (1986) GARCH / vol clustering — Barndorff-Nielsen & Shephard realized volatility

### `R31-S03` — Event reversal template — Post-News Reversal

Fade post-event overreaction when Post-News Reversal implies crowded positioning (news microstructure).

**References:** Brandt et al. post-earnings announcement drift vs reversal contexts — FX fix / macro surprise literature

### `R31-S04` — Regime-switch cautious drift — Post-News Reversal

Small size carry until Markov / HMM-style state probabilities stabilise in Post-News Reversal.

**References:** Hamilton (1989) regime switching (Econometrica) — Guidolin & Timmermann strategic asset allocation with regimes

## Scorecard (win-rate by R-multiple)

Run `python scripts/regime_strategy_scorecard.py` to get per-strategy trade counts and `wr_1r`…`wr_4r` (max favorable excursion in multiples of initial risk before stop).

## Quadrant deep-dive (if generated)

If you ran `_write_regime_docs.py`, extra notes may exist under project folder `Q4 — Transition or Chaos/regimes/r31.md` when this ID is in that quadrant’s list.
