# Regime 35 — Manipulation Phase (ICT)

**Practical quadrant:** Q4 — Q4 — Transition or Chaos

**Taxonomy section:** SECTION 7 — ICT / order flow

## Definition (spec)

Manipulation Phase — liquidity engineering / stop run before expansion (practitioner framework)

## Implementation

- **Code:** [`classify.py`](../classify.py) — `add_regime52_columns()`.
- **Parameters:** tune via [`Regime52Params`](../classify.py).
- **Context-only IDs:** some regimes need `ctx_*` columns on the DataFrame (macro, VIX, DXY, calendars). See the docstring on `add_regime52_columns`.

## Strategies (4 institutional / academic blueprints)

Each regime gets **four** linked strategies. Signals run **only** when `regime52_id` equals this regime (see [`strategies/runner.py`](../strategies/runner.py) and `build_scorecard_table`).

### `R35-S01` — Liquidity sweep fade — Manipulation Phase (ICT)

Fade engineered wicks / false breaks consistent with Manipulation Phase (ICT) (order flow narration; test empirically).

**References:** Evans & Lyons microstructure order flow — Hasbrouck (1991) information content of trades

### `R35-S02` — Vol-cluster straddle / flat gamma proxy fade — Manipulation Phase (ICT)

Stand aside or trade only mean-reversion spikes in Manipulation Phase (ICT); vol desks reduce naked gamma.

**References:** Bollerslev (1986) GARCH / vol clustering — Barndorff-Nielsen & Shephard realized volatility

### `R35-S03` — Event reversal template — Manipulation Phase (ICT)

Fade post-event overreaction when Manipulation Phase (ICT) implies crowded positioning (news microstructure).

**References:** Brandt et al. post-earnings announcement drift vs reversal contexts — FX fix / macro surprise literature

### `R35-S04` — Regime-switch cautious drift — Manipulation Phase (ICT)

Small size carry until Markov / HMM-style state probabilities stabilise in Manipulation Phase (ICT).

**References:** Hamilton (1989) regime switching (Econometrica) — Guidolin & Timmermann strategic asset allocation with regimes

## Scorecard (win-rate by R-multiple)

Run `python scripts/regime_strategy_scorecard.py` to get per-strategy trade counts and `wr_1r`…`wr_4r` (max favorable excursion in multiples of initial risk before stop).

## Quadrant deep-dive (if generated)

If you ran `_write_regime_docs.py`, extra notes may exist under project folder `Q4 — Transition or Chaos/regimes/r35.md` when this ID is in that quadrant’s list.
