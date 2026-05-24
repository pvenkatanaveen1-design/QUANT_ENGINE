# Regime 51 — COT Extreme Positioning Regime

**Practical quadrant:** Q4 — Q4 — Transition or Chaos

**Taxonomy section:** SECTION 10 — Intermarket

## Definition (spec)

COT Extreme Positioning Regime — commercials vs specs at tails; contrarian positioning read

## Implementation

- **Code:** [`classify.py`](../classify.py) — `add_regime52_columns()`.
- **Parameters:** tune via [`Regime52Params`](../classify.py).
- **Context-only IDs:** some regimes need `ctx_*` columns on the DataFrame (macro, VIX, DXY, calendars). See the docstring on `add_regime52_columns`.

## Strategies (4 institutional / academic blueprints)

Each regime gets **four** linked strategies. Signals run **only** when `regime52_id` equals this regime (see [`strategies/runner.py`](../strategies/runner.py) and `build_scorecard_table`).

### `R51-S01` — Liquidity sweep fade — COT Extreme Positioning Regime

Fade engineered wicks / false breaks consistent with COT Extreme Positioning Regime (order flow narration; test empirically).

**References:** Evans & Lyons microstructure order flow — Hasbrouck (1991) information content of trades

### `R51-S02` — Vol-cluster straddle / flat gamma proxy fade — COT Extreme Positioning Regime

Stand aside or trade only mean-reversion spikes in COT Extreme Positioning Regime; vol desks reduce naked gamma.

**References:** Bollerslev (1986) GARCH / vol clustering — Barndorff-Nielsen & Shephard realized volatility

### `R51-S03` — Event reversal template — COT Extreme Positioning Regime

Fade post-event overreaction when COT Extreme Positioning Regime implies crowded positioning (news microstructure).

**References:** Brandt et al. post-earnings announcement drift vs reversal contexts — FX fix / macro surprise literature

### `R51-S04` — Regime-switch cautious drift — COT Extreme Positioning Regime

Small size carry until Markov / HMM-style state probabilities stabilise in COT Extreme Positioning Regime.

**References:** Hamilton (1989) regime switching (Econometrica) — Guidolin & Timmermann strategic asset allocation with regimes

## Scorecard (win-rate by R-multiple)

Run `python scripts/regime_strategy_scorecard.py` to get per-strategy trade counts and `wr_1r`…`wr_4r` (max favorable excursion in multiples of initial risk before stop).

## Quadrant deep-dive (if generated)

If you ran `_write_regime_docs.py`, extra notes may exist under project folder `Q4 — Transition or Chaos/regimes/r51.md` when this ID is in that quadrant’s list.
