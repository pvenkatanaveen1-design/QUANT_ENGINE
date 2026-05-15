# Regime 9 — Low Volatility Squeeze

**Practical quadrant:** Q3 — Q3 — Range Low Volatility

**Taxonomy section:** SECTION 2 — Mean reversion

## Definition (spec)

Low Volatility Squeeze — ATR multi-week low, Bollinger band width tight; volatility breakout literature

## Implementation

- **Code:** [`classify.py`](../classify.py) — `add_regime52_columns()`.
- **Parameters:** tune via [`Regime52Params`](../classify.py).
- **Context-only IDs:** some regimes need `ctx_*` columns on the DataFrame (macro, VIX, DXY, calendars). See the docstring on `add_regime52_columns`.

## Strategies (4 institutional / academic blueprints)

Each regime gets **four** linked strategies. Signals run **only** when `regime52_id` equals this regime (see [`strategies/runner.py`](../strategies/runner.py) and `build_scorecard_table`).

### `R09-S01` — Range fade (upper boundary) — Low Volatility Squeeze

Fade local premium in Low Volatility Squeeze toward equilibrium; stat-arb / STIR desk style mean reversion.

**References:** Avellaneda & Lee (2010) statistical arbitrage mean reversion — Potter & Bouchaud short-horizon MR in ranges

### `R09-S02` — Range fade (lower boundary) — Low Volatility Squeeze

Buy discount in Low Volatility Squeeze when process shows stationary range behavior.

**References:** Same MR foundations as upper fade — Band-trading practitioner risk: partial exits into midline

### `R09-S03` — Z-score oscillation — Low Volatility Squeeze

Enter on standardized deviation from local mean under Low Volatility Squeeze; pairs / basket desks analogue.

**References:** Pole & critic: Ornstein–Uhlenbeck-inspired OU trading heuristics — Gatev, Goetzmann & Rouwenhorst (2006) pairs trading

### `R09-S04` — Premium/discount equilibrium trade — Low Volatility Squeeze

Scale toward 50% dealing range equilibrium in Low Volatility Squeeze (ICT-style auction framing; discretionary).

**References:** Auction theory & market profile (CBOT legacy) — Microstructure: passive liquidity provision heuristics

## Scorecard (win-rate by R-multiple)

Run `python scripts/regime_strategy_scorecard.py` to get per-strategy trade counts and `wr_1r`…`wr_4r` (max favorable excursion in multiples of initial risk before stop).

## Quadrant deep-dive (if generated)

If you ran `_write_regime_docs.py`, extra notes may exist under project folder `Q3 — Range Low Volatility/regimes/r09.md` when this ID is in that quadrant’s list.
