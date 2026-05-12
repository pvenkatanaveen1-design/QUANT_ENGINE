"""52-regime taxonomy (IDs 1–52) aligned with `catalog/` and `_write_regime_docs.py`."""

from __future__ import annotations

# id -> short name
REGIME_NAME: dict[int, str] = {
    1: "Bull Trend",
    2: "Bear Trend",
    3: "Weak Transitional Trend",
    4: "Momentum Regime",
    5: "Momentum Crash Regime",
    6: "Range Consolidation",
    7: "Mean Reversion Regime",
    8: "Premium and Discount Regime",
    9: "Low Volatility Squeeze",
    10: "Accumulation (Wyckoff)",
    11: "Markup (Wyckoff)",
    12: "Distribution (Wyckoff)",
    13: "Markdown (Wyckoff)",
    14: "Re-accumulation (Wyckoff)",
    15: "Re-distribution (Wyckoff)",
    16: "Rate Hiking Cycle",
    17: "Rate Cutting Cycle",
    18: "Quantitative Easing",
    19: "Quantitative Tightening",
    20: "Stagflation",
    21: "Deflationary Regime",
    22: "Reflation Regime",
    23: "Yield Curve Inversion",
    24: "Risk-On",
    25: "Risk-Off",
    26: "Fear Regime",
    27: "Greed Regime",
    28: "Liquidity Crunch",
    29: "Pre-FOMC Drift",
    30: "Post-News Continuation",
    31: "Post-News Reversal",
    32: "Geopolitical Risk Regime",
    33: "Options Expiry Regime",
    34: "End of Month Rebalancing",
    35: "Manipulation Phase (ICT)",
    36: "Expansion Phase (ICT)",
    37: "Asian Range Regime",
    38: "Kill Zone Regime",
    39: "Order Block Regime",
    40: "Imbalance / FVG Regime",
    41: "Order Imbalance Regime",
    42: "Absorption Regime",
    43: "Exhaustion Regime",
    44: "Stop Cascade Regime",
    45: "Hidden Markov / Latent State",
    46: "Volatility Clustering",
    47: "Carry Trade Regime",
    48: "Factor Rotation Regime",
    49: "Dollar Bull Regime",
    50: "Dollar Bear Regime",
    51: "COT Extreme Positioning Regime",
    52: "Intermarket Divergence Regime",
}

Q1_IDS = frozenset({1, 2, 4, 11, 13, 17, 18, 22, 24, 36, 38, 47})
Q2_IDS = frozenset({3, 5, 16, 19, 20, 25, 30, 32, 44, 46})
Q3_IDS = frozenset({6, 7, 8, 9, 10, 12, 27, 29, 33, 34, 37, 39, 40})
Q4_IDS = frozenset({14, 15, 21, 23, 26, 28, 31, 35, 41, 42, 43, 45, 48, 51, 52})

_QUAD_BY_ID: dict[int, str] = {}
for _s, tag in ((Q1_IDS, "Q1"), (Q2_IDS, "Q2"), (Q3_IDS, "Q3"), (Q4_IDS, "Q4")):
    for _i in _s:
        _QUAD_BY_ID[_i] = tag
# Your collapse map omitted 49–50; place under intermarket overlays.
_QUAD_BY_ID[49] = "Q2"
_QUAD_BY_ID[50] = "Q1"


def quadrant_for_id(regime_id: int) -> str:
    return _QUAD_BY_ID.get(int(regime_id), "Q?")


# (section title, definition line) — same taxonomy as `_write_regime_docs.py` / `catalog/`
REGIME_DOC: dict[int, tuple[str, str]] = {
    1: ("SECTION 1 — Trend", "Bull Trend — ADX above 40, RSI above 55, HH/HL structure, price above 50 EMA"),
    2: ("SECTION 1 — Trend", "Bear Trend — ADX above 40, RSI below 45, LH/LL structure, price below 50 EMA"),
    3: ("SECTION 1 — Trend", "Weak Transitional Trend — ADX 25–40 rising, RSI crossing 50, early structure forming"),
    4: ("SECTION 1 — Trend", "Momentum Regime — price persistence over 3–12 months (academic cross-section/time-series momentum)"),
    5: ("SECTION 1 — Trend", "Momentum Crash Regime — momentum factor reverses violently after crisis or extreme crowding"),
    6: ("SECTION 2 — Mean reversion", "Range Consolidation — ADX below 25, RSI 40–60, price between clear S/R levels"),
    7: ("SECTION 2 — Mean reversion", "Mean Reversion Regime — price ~2σ from mean; statistical reversion under stationarity / bounded range"),
    8: ("SECTION 2 — Mean reversion", "Premium and Discount Regime — price vs ~50% equilibrium of dealing range (ICT-style range anatomy)"),
    9: ("SECTION 2 — Mean reversion", "Low Volatility Squeeze — ATR multi-week low, Bollinger band width tight; volatility breakout literature"),
    10: ("SECTION 3 — Wyckoff", "Accumulation — institutions absorbing supply at lows; spring / test narrative"),
    11: ("SECTION 3 — Wyckoff", "Markup — trend leg after accumulation; sustained higher highs / lows"),
    12: ("SECTION 3 — Wyckoff", "Distribution — institutions distributing into strength at highs; UTAD narrative"),
    13: ("SECTION 3 — Wyckoff", "Markdown — downtrend after distribution; mirror of markup"),
    14: ("SECTION 3 — Wyckoff", "Re-accumulation — consolidation mid-markup; reload before continuation"),
    15: ("SECTION 3 — Wyckoff", "Re-distribution — consolidation mid-markdown; reload before continuation down"),
    16: ("SECTION 4 — Macro", "Rate Hiking Cycle — policy tightening; higher real yields; typical USD / duration headwinds context-dependent"),
    17: ("SECTION 4 — Macro", "Rate Cutting Cycle — easing cycle; growth/defensive rotation varies by recession vs mid-cycle cut"),
    18: ("SECTION 4 — Macro", "Quantitative Easing — large-scale asset purchases; portfolio balance channel (academic)"),
    19: ("SECTION 4 — Macro", "Quantitative Tightening — balance sheet runoff; liquidity withdrawal drag"),
    20: ("SECTION 4 — Macro", "Stagflation — high inflation + weak growth; macro hedge demand for real assets / curve steepeners"),
    21: ("SECTION 4 — Macro", "Deflationary Regime — falling nominal demand/prices; duration, flight-to-quality bias"),
    22: ("SECTION 4 — Macro", "Reflation Regime — recovery from deflationary scare; cyclicals/commodities leadership phase"),
    23: ("SECTION 4 — Macro", "Yield Curve Inversion — short > long yields; late-cycle recession signal with lag (empirical)"),
    24: ("SECTION 5 — Sentiment / risk", "Risk-On — pro-cyclical allocations; carry-seeking, credit tight spreads typical"),
    25: ("SECTION 5 — Sentiment / risk", "Risk-Off — safe havens, de-grossing, correlation spike in stress"),
    26: ("SECTION 5 — Sentiment / risk", "Fear Regime — VIX elevated; forced deleveraging, liquidity premiums"),
    27: ("SECTION 5 — Sentiment / risk", "Greed Regime — volatility complacency; crowding, low risk premia"),
    28: ("SECTION 5 — Sentiment / risk", "Liquidity Crunch — margin / funding stress; fire-sale correlations → 1"),
    29: ("SECTION 6 — News / events", "Pre-FOMC Drift — scheduled-event risk premium / positioning mechanics (mixed evidence, context-specific)"),
    30: ("SECTION 6 — News / events", "Post-News Continuation — outcome surprises align with trend; drift under information diffusion"),
    31: ("SECTION 6 — News / events", "Post-News Reversal — priced-in outcomes; mean reversion after volatility event"),
    32: ("SECTION 6 — News / events", "Geopolitical Risk Regime — war/sanctions premia in energy, gold, safe FX"),
    33: ("SECTION 6 — News / events", "Options Expiry Regime — gamma / OI pinning; dealer hedging flows near strikes"),
    34: ("SECTION 6 — News / events", "End of Month Rebalancing — benchmark flow schedules; predictable directional pressure windows"),
    35: ("SECTION 7 — ICT / order flow", "Manipulation Phase — liquidity engineering / stop run before expansion (practitioner framework)"),
    36: ("SECTION 7 — ICT / order flow", "Expansion Phase — directional impulse after manipulation; participation ↑"),
    37: ("SECTION 7 — ICT / order flow", "Asian Range Regime — overnight balance; London/NY breakout games"),
    38: ("SECTION 7 — ICT / order flow", "Kill Zone Regime — session opens / overlaps; liquidity timetable"),
    39: ("SECTION 7 — ICT / order flow", "Order Block Regime — return to defended auction zones; reaction trade framework"),
    40: ("SECTION 7 — ICT / order flow", "Imbalance / FVG Regime — gap/inefficiency fill before continuation (practitioner)"),
    41: ("SECTION 8 — Microstructure", "Order Imbalance Regime — signed volume / queue imbalance persistence (microstructure)"),
    42: ("SECTION 8 — Microstructure", "Absorption Regime — large passive liquidity absorbing aggressor flow; auction stalling"),
    43: ("SECTION 8 — Microstructure", "Exhaustion Regime — trend leg with declining participation; climax risk"),
    44: ("SECTION 8 — Microstructure", "Stop Cascade Regime — liquidity vacuum past clustered stops; snapback risk"),
    45: ("SECTION 8 — Microstructure", "Hidden Markov Regime — latent discrete states drive parameters (Hamilton-style switching)"),
    46: ("SECTION 9 — Quant / statistical", "Volatility Clustering — persistence in |returns|; GARCH family models"),
    47: ("SECTION 9 — Quant / statistical", "Carry Trade Regime — funding vs target rates; crash risk under sudden unwind"),
    48: ("SECTION 9 — Quant / statistical", "Factor Rotation Regime — time-varying factor premia (value/mom/quality/low-vol cycles)"),
    49: ("SECTION 9 — Quant / statistical", "Dollar Bull Regime — broad USD uptrend; EM/FX/cross-asset constraints"),
    50: ("SECTION 10 — Intermarket", "Dollar Bear Regime — broad USD downtrend; supports gold/commodity complex mechanically"),
    51: ("SECTION 10 — Intermarket", "COT Extreme Positioning Regime — commercials vs specs at tails; contrarian positioning read"),
    52: ("SECTION 10 — Intermarket", "Intermarket Divergence Regime — correlation breakdown; potential stress in weaker leg"),
}


QUADRANT_FOLDER_LABEL = {
    "Q1": "Q1 — Trend Low Volatility",
    "Q2": "Q2 — Trend High Volatility",
    "Q3": "Q3 — Range Low Volatility",
    "Q4": "Q4 — Transition or Chaos",
}
