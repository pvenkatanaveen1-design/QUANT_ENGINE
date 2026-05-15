# Regime 42 — Absorption Regime

**Practical quadrant:** Q4 — Q4 — Transition or Chaos

**Taxonomy section:** SECTION 8 — Microstructure

## Definition (spec)

Absorption Regime — large passive liquidity absorbing aggressor flow; auction stalling

## Implementation

- **Code:** [`classify.py`](../classify.py) — `add_regime52_columns()`.
- **Parameters:** tune via [`Regime52Params`](../classify.py).
- **Context-only IDs:** some regimes need `ctx_*` columns on the DataFrame (macro, VIX, DXY, calendars). See the docstring on `add_regime52_columns`.

## Strategies (4 institutional / academic blueprints)

Each regime gets **four** linked strategies. Signals run **only** when `regime52_id` equals this regime (see [`strategies/runner.py`](../strategies/runner.py) and `build_scorecard_table`).

### `R42-S01` — Liquidity sweep fade — Absorption Regime

Fade engineered wicks / false breaks consistent with Absorption Regime (order flow narration; test empirically).

**References:** Evans & Lyons microstructure order flow — Hasbrouck (1991) information content of trades

### `R42-S02` — Vol-cluster straddle / flat gamma proxy fade — Absorption Regime

Stand aside or trade only mean-reversion spikes in Absorption Regime; vol desks reduce naked gamma.

**References:** Bollerslev (1986) GARCH / vol clustering — Barndorff-Nielsen & Shephard realized volatility

### `R42-S03` — Event reversal template — Absorption Regime

Fade post-event overreaction when Absorption Regime implies crowded positioning (news microstructure).

**References:** Brandt et al. post-earnings announcement drift vs reversal contexts — FX fix / macro surprise literature

### `R42-S04` — Regime-switch cautious drift — Absorption Regime

Small size carry until Markov / HMM-style state probabilities stabilise in Absorption Regime.

**References:** Hamilton (1989) regime switching (Econometrica) — Guidolin & Timmermann strategic asset allocation with regimes

## Scorecard (win-rate by R-multiple)

Run `python scripts/regime_strategy_scorecard.py` to get per-strategy trade counts and `wr_1r`…`wr_4r` (max favorable excursion in multiples of initial risk before stop).

## Quadrant deep-dive (if generated)

If you ran `_write_regime_docs.py`, extra notes may exist under project folder `Q4 — Transition or Chaos/regimes/r42.md` when this ID is in that quadrant’s list.
