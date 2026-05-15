# Regime 10 — Accumulation (Wyckoff)

**Practical quadrant:** Q3 — Q3 — Range Low Volatility

**Taxonomy section:** SECTION 3 — Wyckoff

## Definition (spec)

Accumulation — institutions absorbing supply at lows; spring / test narrative

## Implementation

- **Code:** [`classify.py`](../classify.py) — `add_regime52_columns()`.
- **Parameters:** tune via [`Regime52Params`](../classify.py).
- **Context-only IDs:** some regimes need `ctx_*` columns on the DataFrame (macro, VIX, DXY, calendars). See the docstring on `add_regime52_columns`.

## Strategies (4 institutional / academic blueprints)

Each regime gets **four** linked strategies. Signals run **only** when `regime52_id` equals this regime (see [`strategies/runner.py`](../strategies/runner.py) and `build_scorecard_table`).

### `R10-S01` — Range fade (upper boundary) — Accumulation (Wyckoff)

Fade local premium in Accumulation (Wyckoff) toward equilibrium; stat-arb / STIR desk style mean reversion.

**References:** Avellaneda & Lee (2010) statistical arbitrage mean reversion — Potter & Bouchaud short-horizon MR in ranges

### `R10-S02` — Range fade (lower boundary) — Accumulation (Wyckoff)

Buy discount in Accumulation (Wyckoff) when process shows stationary range behavior.

**References:** Same MR foundations as upper fade — Band-trading practitioner risk: partial exits into midline

### `R10-S03` — Z-score oscillation — Accumulation (Wyckoff)

Enter on standardized deviation from local mean under Accumulation (Wyckoff); pairs / basket desks analogue.

**References:** Pole & critic: Ornstein–Uhlenbeck-inspired OU trading heuristics — Gatev, Goetzmann & Rouwenhorst (2006) pairs trading

### `R10-S04` — Premium/discount equilibrium trade — Accumulation (Wyckoff)

Scale toward 50% dealing range equilibrium in Accumulation (Wyckoff) (ICT-style auction framing; discretionary).

**References:** Auction theory & market profile (CBOT legacy) — Microstructure: passive liquidity provision heuristics

## Scorecard (win-rate by R-multiple)

Run `python scripts/regime_strategy_scorecard.py` to get per-strategy trade counts and `wr_1r`…`wr_4r` (max favorable excursion in multiples of initial risk before stop).

## Quadrant deep-dive (if generated)

If you ran `_write_regime_docs.py`, extra notes may exist under project folder `Q3 — Range Low Volatility/regimes/r10.md` when this ID is in that quadrant’s list.
