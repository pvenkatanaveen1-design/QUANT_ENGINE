# Regime 25 — Risk-Off

**Practical quadrant:** Q2 — Q2 — Trend High Volatility

**Taxonomy section:** SECTION 5 — Sentiment / risk

## Definition (spec)

Risk-Off — safe havens, de-grossing, correlation spike in stress

## Implementation

- **Code:** [`classify.py`](../classify.py) — `add_regime52_columns()`.
- **Parameters:** tune via [`Regime52Params`](../classify.py).
- **Context-only IDs:** some regimes need `ctx_*` columns on the DataFrame (macro, VIX, DXY, calendars). See the docstring on `add_regime52_columns`.

## Strategies (4 institutional / academic blueprints)

Each regime gets **four** linked strategies. Signals run **only** when `regime52_id` equals this regime (see [`strategies/runner.py`](../strategies/runner.py) and `build_scorecard_table`).

### `R25-S01` — Stress mean reversion (tail hedge tilt) — Risk-Off

Fade local extremes in Risk-Off when liquidity premia widen; institutional macro overlay book pattern.

**References:** Classic short-horizon reversal after volatility shocks (equity lit; FX analog) — Brunnermeier & Nagel (2004) distressed arbitrage / funding constraints

### `R25-S02` — Wide-stop directional breakout — Risk-Off

Trade expansion after compression in Risk-Off with widened stops (prop desks reduce size, widen λ).

**References:** Bollinger squeeze + expansion (Bollinger 1992; practitioner) — Volatility breakout premium in currency markets (academic FX)

### `R25-S03` — Crash / momentum reversal scalp — Risk-Off

Short-term reversal after sharp impulsive leg in Risk-Off (crash risk literature; tactical desks).

**References:** Daniel & Moskowitz (2016) momentum crashes (JFE) — Cooper, Gutierrez & Hameed (2004) 'market states' & reversals

### `R25-S04` — Trend-with-vol overlay (short side bias ready) — Risk-Off

Directional trade aligned to dominant trend in Risk-Off but only after vol confirms participation.

**References:** Ang et al. downside correlation / asymmetric correlation — FX carry crash premia (Brunnermeier, Nagel, Pedersen)

## Scorecard (win-rate by R-multiple)

Run `python scripts/regime_strategy_scorecard.py` to get per-strategy trade counts and `wr_1r`…`wr_4r` (max favorable excursion in multiples of initial risk before stop).

## Quadrant deep-dive (if generated)

If you ran `_write_regime_docs.py`, extra notes may exist under project folder `Q2 — Trend High Volatility/regimes/r25.md` when this ID is in that quadrant’s list.
