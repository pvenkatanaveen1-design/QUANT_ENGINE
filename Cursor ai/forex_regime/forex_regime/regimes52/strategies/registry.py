from __future__ import annotations

from dataclasses import dataclass

from forex_regime.regimes52.taxonomy import REGIME_NAME, quadrant_for_id


@dataclass(frozen=True)
class StrategySpec:
    """One tradable playbook tied to a single regime ID for scorecard + docs."""

    key: str
    regime_id: int
    title: str
    playbook: str
    references: tuple[str, ...]
    signal_kind: str
    side: int  # +1 long, -1 short, 0 both / signal chooses (e.g. squeeze breakout)


def _bp(
    title: str,
    playbook: str,
    refs: tuple[str, ...],
    kind: str,
    side: int,
) -> dict:
    return {"title": title, "playbook": playbook, "refs": refs, "kind": kind, "side": side}


# Four strategies per quadrant — titles reference institutional / academic anchors (abbreviated).
# signal_kind maps to `strategy_signal()` in signals.py
_BLUEPRINTS: dict[str, list[dict]] = {
    "Q1": [
        _bp(
            "TSMOM / vol-managed pullback",
            "Buy structural pullbacks while higher-timeframe trend holds in {regime_name}; size down when realized variance spikes.",
            (
                "Moskowitz, Ooi & Pedersen (2012) 'Time Series Momentum' (JFE)",
                "Barroso & Santa-Clara (2015) 'Momentum Has Its Moments' (JF)",
            ),
            "pullback_with_trend",
            1,
        ),
        _bp(
            "Channel / Donchian breakout",
            "Enter on range expansion in the direction of {regime_name} (institutional trend desks, managed futures CTAs).",
            (
                "Classic Donchian / Turtle-style breakout trend following",
                "Krausz (1997) channel + MA hybrid literature",
            ),
            "breakout_with_trend",
            1,
        ),
        _bp(
            "Cross-sectional momentum add-on",
            "Add on strong continuation closes when {regime_name} supports risk appetite and breadth.",
            (
                "Jegadeesh & Titman (1993) 'Returns to Buying Winners…' (JF)",
                "Asness, Moskowitz & Pedersen (2013) value and momentum everywhere",
            ),
            "continuation_bar",
            1,
        ),
        _bp(
            "Low-vol trend drift (defensive gross-up)",
            "Hold / pyramid slowly in {regime_name}; emphasis on not crowding into identical payoff tails.",
            (
                "Moreira & Muir (2017) volatility-managed portfolios",
                "Kelly criterion & fractional sizing (practitioner risk books)",
            ),
            "trend_drift",
            1,
        ),
    ],
    "Q2": [
        _bp(
            "Stress mean reversion (tail hedge tilt)",
            "Fade local extremes in {regime_name} when liquidity premia widen; institutional macro overlay book pattern.",
            (
                "Classic short-horizon reversal after volatility shocks (equity lit; FX analog)",
                "Brunnermeier & Nagel (2004) distressed arbitrage / funding constraints",
            ),
            "fade_extreme_rsi",
            -1,
        ),
        _bp(
            "Wide-stop directional breakout",
            "Trade expansion after compression in {regime_name} with widened stops (prop desks reduce size, widen λ).",
            (
                "Bollinger squeeze + expansion (Bollinger 1992; practitioner)",
                "Volatility breakout premium in currency markets (academic FX)",
            ),
            "squeeze_breakout_dir",
            0,
        ),
        _bp(
            "Crash / momentum reversal scalp",
            "Short-term reversal after sharp impulsive leg in {regime_name} (crash risk literature; tactical desks).",
            (
                "Daniel & Moskowitz (2016) momentum crashes (JFE)",
                "Cooper, Gutierrez & Hameed (2004) 'market states' & reversals",
            ),
            "impulse_reversal",
            -1,
        ),
        _bp(
            "Trend-with-vol overlay (short side bias ready)",
            "Directional trade aligned to dominant trend in {regime_name} but only after vol confirms participation.",
            (
                "Ang et al. downside correlation / asymmetric correlation",
                "FX carry crash premia (Brunnermeier, Nagel, Pedersen)",
            ),
            "breakout_with_trend",
            -1,
        ),
    ],
    "Q3": [
        _bp(
            "Range fade (upper boundary)",
            "Fade local premium in {regime_name} toward equilibrium; stat-arb / STIR desk style mean reversion.",
            (
                "Avellaneda & Lee (2010) statistical arbitrage mean reversion",
                "Potter & Bouchaud short-horizon MR in ranges",
            ),
            "fade_bb_high",
            -1,
        ),
        _bp(
            "Range fade (lower boundary)",
            "Buy discount in {regime_name} when process shows stationary range behavior.",
            (
                "Same MR foundations as upper fade",
                "Band-trading practitioner risk: partial exits into midline",
            ),
            "fade_bb_low",
            1,
        ),
        _bp(
            "Z-score oscillation",
            "Enter on standardized deviation from local mean under {regime_name}; pairs / basket desks analogue.",
            (
                "Pole & critic: Ornstein–Uhlenbeck-inspired OU trading heuristics",
                "Gatev, Goetzmann & Rouwenhorst (2006) pairs trading",
            ),
            "zscore_fade",
            1,
        ),
        _bp(
            "Premium/discount equilibrium trade",
            "Scale toward 50% dealing range equilibrium in {regime_name} (ICT-style auction framing; discretionary).",
            (
                "Auction theory & market profile (CBOT legacy)",
                "Microstructure: passive liquidity provision heuristics",
            ),
            "range_equilibrium",
            1,
        ),
    ],
    "Q4": [
        _bp(
            "Liquidity sweep fade",
            "Fade engineered wicks / false breaks consistent with {regime_name} (order flow narration; test empirically).",
            (
                "Evans & Lyons microstructure order flow",
                "Hasbrouck (1991) information content of trades",
            ),
            "wick_reversal",
            1,
        ),
        _bp(
            "Vol-cluster straddle / flat gamma proxy fade",
            "Stand aside or trade only mean-reversion spikes in {regime_name}; vol desks reduce naked gamma.",
            (
                "Bollerslev (1986) GARCH / vol clustering",
                "Barndorff-Nielsen & Shephard realized volatility",
            ),
            "vol_spike_fade",
            -1,
        ),
        _bp(
            "Event reversal template",
            "Fade post-event overreaction when {regime_name} implies crowded positioning (news microstructure).",
            (
                "Brandt et al. post-earnings announcement drift vs reversal contexts",
                "FX fix / macro surprise literature",
            ),
            "narrow_range_break_fake",
            1,
        ),
        _bp(
            "Regime-switch cautious drift",
            "Small size carry until Markov / HMM-style state probabilities stabilise in {regime_name}.",
            (
                "Hamilton (1989) regime switching (Econometrica)",
                "Guidolin & Timmermann strategic asset allocation with regimes",
            ),
            "tiny_drift",
            1,
        ),
    ],
}


def all_strategy_specs() -> list[StrategySpec]:
    specs: list[StrategySpec] = []
    for rid in range(1, 53):
        q = quadrant_for_id(rid)
        rn = REGIME_NAME[rid]
        blueprints = _BLUEPRINTS.get(q, _BLUEPRINTS["Q4"])
        for j, bp in enumerate(blueprints, start=1):
            key = f"R{rid:02d}-S{j:02d}"
            side = int(bp["side"])
            specs.append(
                StrategySpec(
                    key=key,
                    regime_id=rid,
                    title=f'{bp["title"]} — {rn}',
                    playbook=bp["playbook"].format(regime_name=rn),
                    references=tuple(bp["refs"]),
                    signal_kind=str(bp["kind"]),
                    side=side,
                )
            )
    return specs


def strategies_for_regime(regime_id: int) -> list[StrategySpec]:
    rid = int(regime_id)
    return [s for s in all_strategy_specs() if s.regime_id == rid]
