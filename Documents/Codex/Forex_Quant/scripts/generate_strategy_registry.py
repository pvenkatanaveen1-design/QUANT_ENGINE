"""
Regenerate config/strategy_registry.yaml (208 = 52 regimes × 4 slots).
Q1: trend blueprint; Q2: high-vol trend + 0.5x (except patches); Q3: range blueprint; Q4: defensive.
Run: python scripts/generate_strategy_registry.py
"""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REG_PATH = ROOT / "config" / "strategy_registry.yaml"

SLOTS = ("primary", "secondary", "confirmation", "fallback")

# (signal_fn, name, win_rate_low, win_rate_high, rrr, ev, evidence, size_override|None, notes|None)
Q1_BLOCKS: dict[str, list[tuple]] = {
    "M01": [
        ("S01_ema_pullback", "Trend Base — EMA Pullback (Primary)", 0.55, 0.62, 2.5, 0.73, "[A Menkhoff2012][P]", None, None),
        ("S02_donchian", "Trend Base — Donchian Continuation", 0.52, 0.58, 3.0, 0.77, "[P][Q AQR]", None, None),
        ("S01_ema_pullback", "Trend Base — Break-Retest", 0.52, 0.58, 2.0, 0.50, "[P universal]", None, None),
        ("S02_donchian", "Trend Base — Time-Series Momentum", 0.55, 0.60, 3.0, 0.80, "[A Jegadeesh1993][A Menkhoff2012]", None, None),
    ],
    "M02": [
        ("S01_ema_pullback", "Trend Squeeze — Continuation After Squeeze", 0.58, 0.64, 3.0, 1.07, "[P][A GARCH vol clustering]", None, None),
        ("S01_ema_pullback", "Trend Squeeze — EMA Pullback", 0.55, 0.60, 2.5, 0.80, "[P]", None, None),
        ("S01_ema_pullback", "Trend Squeeze — Inside Bar Break", 0.52, 0.57, 2.5, 0.68, "[P]", None, None),
        ("S02_donchian", "Trend Squeeze — Donchian Break", 0.52, 0.58, 3.0, 0.77, "[P][Q]", None, None),
    ],
    "M03": [
        ("S07_carry_drift", "Trend Asia — Carry Drift", 0.48, 0.54, 2.0, 0.46, "[A Burnside2011][P]", 0.5, None),
        ("S07_carry_drift", "Trend Asia — EMA Pullback (Reduced)", 0.48, 0.54, 2.0, 0.46, "[P]", 0.5, None),
        ("S07_carry_drift", "Trend Asia — EMA Pullback Half Size", 0.48, 0.52, 2.0, 0.40, "[P]", 0.5, None),
        ("S08_no_trade", "Trend Asia — No Trade (Spread Wide)", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
    ],
    "M04": [
        ("S01_ema_pullback", "Trend London Kill Zone — EMA Pullback", 0.60, 0.65, 2.5, 0.85, "[P][I kill_zone]", None, None),
        ("S01_ema_pullback", "Trend London Kill Zone — Opening Range Break", 0.55, 0.62, 2.0, 0.73, "[P]", None, None),
        ("S01_ema_pullback", "Trend London Kill Zone — EMA Retest", 0.55, 0.62, 2.5, 0.80, "[P]", None, None),
        ("S04_asian_sweep", "Trend London Kill Zone — Sweep Continuation", 0.60, 0.65, 3.0, 1.15, "[P][I]", None, None),
    ],
    "M05": [
        ("S01_ema_pullback", "Trend NY/Overlap — Continuation", 0.55, 0.60, 2.5, 0.80, "[P NY continuation]", None, None),
        ("S01_ema_pullback", "Trend NY/Overlap — Pullback Continuation", 0.56, 0.62, 2.5, 0.84, "[P]", None, None),
        ("S01_ema_pullback", "Trend NY/Overlap — Breakout Retest", 0.54, 0.60, 2.5, 0.78, "[P]", None, None),
        ("S02_donchian", "Trend NY/Overlap — Pyramid Add", 0.55, 0.60, 3.0, 0.95, "[Q AQR pyramiding]", None, None),
    ],
    "M06": [
        ("S08_no_trade", "Trend Late Session — Trail Only", 0.00, 0.00, 0.0, -0.10, "[P][R]", None, None),
        ("S08_no_trade", "Trend Late Session — No New Entry", 0.00, 0.00, 0.0, -0.10, "[P][R]", None, None),
        ("S08_no_trade", "Trend Late Session — Time Exit", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
        ("S08_no_trade", "Trend Late Session — Swap Check Exit", 0.00, 0.00, 0.0, -0.10, "[P][R]", None, None),
    ],
    "M07": [
        ("S08_no_trade", "Trend Pre-News — Reduce Size 50%", 0.00, 0.00, 0.0, -0.10, "[A Lucca2015][P]", None, None),
        ("S08_no_trade", "Trend Pre-News — No New Trade", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
        ("S08_no_trade", "Trend Pre-News — Tighten/Partial Exit", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
        ("S08_no_trade", "Trend Pre-News — Wait for Post-News", 0.00, 0.00, 0.0, -0.10, "[P][R]", None, None),
    ],
    "M08": [
        ("S01_ema_pullback", "Trend Post-News Confirmed — Continuation Retest", 0.60, 0.65, 2.5, 0.88, "[P post-news]", None, None),
        ("S01_ema_pullback", "Trend Post-News — EMA Pullback", 0.56, 0.62, 2.5, 0.84, "[P]", None, None),
        ("S02_donchian", "Trend Post-News — Breakout Continuation", 0.55, 0.62, 3.0, 0.96, "[P]", None, None),
        ("S01_ema_pullback", "Trend Post-News — Reduced Size (vol still elevated)", 0.55, 0.62, 2.5, 0.80, "[P]", 0.75, None),
    ],
    "M09": [
        ("S05_sweep_reclaim", "Trend Sweep — Sweep Pullback Entry", 0.62, 0.68, 3.0, 1.56, "[P][I ICT sweep]", None, None),
        ("S01_ema_pullback", "Trend Sweep — Break-Retest After Sweep", 0.58, 0.64, 2.5, 1.02, "[P]", None, None),
        ("S01_ema_pullback", "Trend Sweep — Trend Continuation After Sweep", 0.58, 0.65, 2.5, 1.03, "[P]", None, None),
        ("S05_sweep_reclaim", "Trend Sweep — Stop Beyond Sweep Extreme", 0.58, 0.64, 3.0, 1.18, "[P][I]", None, None),
    ],
    "M10": [
        ("S08_no_trade", "Trend High Spread — No New Trade", 0.00, 0.00, 0.0, -0.10, "[A][P spread kills edge]", None, None),
        ("S08_no_trade", "Trend High Spread — Reduce Size", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
        ("S08_no_trade", "Trend High Spread — Wait for Spread Normal", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
        ("S08_no_trade", "Trend High Spread — Trail Existing Only", 0.00, 0.00, 0.0, -0.10, "[P][R]", None, None),
    ],
    "M11": [
        ("S01_ema_pullback", "Trend Exhaustion — Smaller Pullback Entry", 0.52, 0.58, 2.0, 0.50, "[P]", 0.75, None),
        ("S01_ema_pullback", "Trend Exhaustion — Trail Existing", 0.52, 0.58, 2.0, 0.50, "[P]", None, None),
        ("S01_ema_pullback", "Trend Exhaustion — Partial Exit at TP1", 0.52, 0.58, 2.0, 0.50, "[P]", None, None),
        ("S08_no_trade", "Trend Exhaustion — No Fresh Breakout Chase", 0.38, 0.45, 0.0, -0.10, "[P]", None, None),
    ],
    "M12": [
        ("S01_ema_pullback", "Trend Multi-TF — Full Trend Continuation", 0.62, 0.68, 3.0, 1.56, "[P][Q AQR multi-signal]", None, None),
        ("S01_ema_pullback", "Trend Multi-TF — EMA Pullback", 0.60, 0.65, 2.5, 1.13, "[P]", None, None),
        ("S01_ema_pullback", "Trend Multi-TF — Break-Retest", 0.58, 0.64, 2.5, 1.02, "[P]", None, None),
        ("S02_donchian", "Trend Multi-TF — Time-Series Momentum", 0.60, 0.68, 3.0, 1.20, "[A Menkhoff2012]", None, None),
    ],
    "M13": [
        ("S02_donchian", "Trend Macro — USD-Aligned Continuation", 0.64, 0.70, 3.0, 1.68, "[A Serban2010][P]", None, None),
        ("S01_ema_pullback", "Trend Macro — Pullback", 0.62, 0.67, 2.5, 1.20, "[P]", None, None),
        ("S02_donchian", "Trend Macro — Basket-Confirmed Breakout", 0.63, 0.68, 3.0, 1.32, "[P]", None, None),
        (
            "S08_no_trade",
            "Trend Macro — Reduce Correlated Exposure",
            0.00,
            0.00,
            0.0,
            -0.10,
            "[P][A correlation risk]",
            None,
            "Cap correlated exposure at 3% total. EUR+GBP+AUD all long USD = 1 trade x3.",
        ),
    ],
}

Q3_BLOCKS: dict[str, list[tuple]] = {
    "M01": [
        ("S03_bb_fade", "Range Base — Bollinger Fade", 0.63, 0.70, 1.8, 0.82, "[A Poterba1988][P BB 2SD]", None, None),
        ("S03_bb_fade", "Range Base — RSI Range Fade", 0.60, 0.67, 1.8, 0.74, "[P]", None, None),
        ("S03_bb_fade", "Range Base — S/R Fade", 0.57, 0.63, 1.8, 0.67, "[P]", None, None),
        ("S03_bb_fade", "Range Base — VWAP Mean Fade", 0.55, 0.62, 1.5, 0.55, "[P]", None, None),
    ],
    "M02": [
        ("S03_bb_fade", "Range Compression — Post-Squeeze Mean Reversion", 0.61, 0.67, 1.8, 0.76, "[P][A vol clustering]", None, None),
        ("S06_failed_bo_fade", "Range Compression — Failed Range Break", 0.58, 0.65, 2.0, 0.70, "[P]", None, None),
        ("S03_bb_fade", "Range Compression — Inner Range Fade", 0.56, 0.62, 1.8, 0.62, "[P]", None, None),
        ("S08_no_trade", "Range Compression — Wait Expansion Clear", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
    ],
    "M03": [
        ("S03_bb_fade", "Range Asia — Session Mean Fade", 0.58, 0.64, 1.8, 0.68, "[P]", 0.5, None),
        ("S03_bb_fade", "Range Asia — Tight Range Scalp", 0.55, 0.62, 1.5, 0.58, "[P]", 0.5, None),
        ("S07_carry_drift", "Range Asia — Drift Fade", 0.52, 0.58, 1.8, 0.52, "[P]", 0.5, None),
        ("S08_no_trade", "Range Asia — Spread Watch", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
    ],
    "M04": [
        (
            "S04_asian_sweep",
            "Range London Kill Zone — Asian Range Sweep Reversal ⭐ CORE",
            0.62,
            0.68,
            3.0,
            1.60,
            "[P Zaye Capital][I ICT Asian Range]",
            None,
            "3-4/5 trading days. Kill zone timing MANDATORY. MSS confirmation (body_ratio<0.5).",
        ),
        ("S06_failed_bo_fade", "Range London Kill Zone — Failed Breakout Fade", 0.60, 0.65, 2.5, 1.00, "[P]", None, None),
        ("S03_bb_fade", "Range London Kill Zone — Range Expansion Fade", 0.56, 0.62, 2.5, 0.84, "[P]", None, None),
        (
            "S04_asian_sweep",
            "Range London Kill Zone — Wait MSS Confirmation",
            0.62,
            0.68,
            3.0,
            1.60,
            "[I MSS required]",
            None,
            "If unclear — wait for MSS. MSS = most recent HH broken (bull) or LL broken (bear).",
        ),
    ],
    "M05": [
        ("S03_bb_fade", "Range Overlap — High Liquidity Mean Fade", 0.60, 0.66, 1.8, 0.74, "[P]", None, None),
        ("S06_failed_bo_fade", "Range Overlap — Liquidity Grab Fade", 0.58, 0.64, 2.2, 0.72, "[P]", None, None),
        ("S03_bb_fade", "Range Overlap — Session VWAP Fade", 0.56, 0.62, 1.8, 0.65, "[P]", None, None),
        ("S05_sweep_reclaim", "Range Overlap — Sweep Mean Revert", 0.57, 0.63, 2.5, 0.78, "[P][I]", None, None),
    ],
    "M06": [
        ("S08_no_trade", "Range Late Session — No New Range Trade", 0.00, 0.00, 0.0, -0.10, "[P][R]", None, None),
        ("S03_bb_fade", "Range Late Session — Tight Fade Only", 0.52, 0.58, 1.5, 0.48, "[P]", 0.5, None),
        ("S08_no_trade", "Range Late Session — Trail Stops", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
        ("S08_no_trade", "Range Late Session — Flat Before Rollover", 0.00, 0.00, 0.0, -0.10, "[P][R]", None, None),
    ],
    "M07": [
        ("S08_no_trade", "Range Pre-News — Flat", 0.00, 0.00, 0.0, -0.10, "[A Lucca2015][P]", None, None),
        ("S08_no_trade", "Range Pre-News — No Fade Lottery", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
        ("S08_no_trade", "Range Pre-News — Close Pending Fades", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
        ("S08_no_trade", "Range Pre-News — Wait Post-Catalyst", 0.00, 0.00, 0.0, -0.10, "[P][R]", None, None),
    ],
    "M08": [
        ("S03_bb_fade", "Range Post-News — Volatility Mean Revert", 0.58, 0.64, 2.0, 0.72, "[P]", None, None),
        ("S06_failed_bo_fade", "Range Post-News — Failed Spike Fade", 0.57, 0.63, 2.2, 0.70, "[P]", None, None),
        ("S03_bb_fade", "Range Post-News — Two-Sided Range", 0.55, 0.61, 1.8, 0.62, "[P]", 0.75, None),
        ("S08_no_trade", "Range Post-News — If Range Broken, Stand Down", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
    ],
    "M09": [
        ("S05_sweep_reclaim", "Range Sweep at Boundary — Sweep Reclaim", 0.62, 0.68, 3.0, 1.60, "[P][I]", None, None),
        ("S04_asian_sweep", "Range Sweep at Boundary — Break-Retest", 0.60, 0.65, 2.5, 1.00, "[P]", None, None),
        ("S03_bb_fade", "Range Sweep at Boundary — Continuation Fade", 0.58, 0.65, 3.0, 1.04, "[P]", None, None),
        ("S05_sweep_reclaim", "Range Sweep at Boundary — Stop Beyond Sweep", 0.58, 0.64, 3.0, 1.03, "[P][I]", None, None),
    ],
    "M10": [
        ("S08_no_trade", "Range High Spread — No Range Edge", 0.00, 0.00, 0.0, -0.10, "[A][P]", None, None),
        ("S08_no_trade", "Range High Spread — Cost > Fair Value", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
        ("S08_no_trade", "Range High Spread — Observe Only", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
        ("S08_no_trade", "Range High Spread — Trail Working Fades", 0.00, 0.00, 0.0, -0.10, "[P][R]", None, None),
    ],
    "M11": [
        ("S03_bb_fade", "Range Exhaustion — Terminal Range Fade", 0.56, 0.62, 1.8, 0.64, "[P]", 0.75, None),
        ("S06_failed_bo_fade", "Range Exhaustion — Last Fakeout Fade", 0.54, 0.60, 2.0, 0.60, "[P]", None, None),
        ("S08_no_trade", "Range Exhaustion — Reduced New Risk", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
        ("S08_no_trade", "Range Exhaustion — Wait Trend Resolution", 0.00, 0.00, 0.0, -0.10, "[P]", None, None),
    ],
    "M12": [
        ("S03_bb_fade", "Range Multi-TF — HTF Range Anchor Fade", 0.61, 0.67, 1.9, 0.78, "[P][Q]", None, None),
        ("S06_failed_bo_fade", "Range Multi-TF — HTF Boundary Fakeout", 0.59, 0.65, 2.2, 0.74, "[P]", None, None),
        ("S05_sweep_reclaim", "Range Multi-TF — Liquidity Sweep Revert", 0.58, 0.64, 2.5, 0.76, "[P][I]", None, None),
        ("S03_bb_fade", "Range Multi-TF — Confluence VWAP Fade", 0.57, 0.63, 1.8, 0.68, "[P]", None, None),
    ],
    "M13": [
        ("S08_no_trade", "Range Macro — Correlation Chaos", 0.00, 0.00, 0.0, -0.10, "[P][A correlation risk]", None, None),
        ("S03_bb_fade", "Range Macro — USD Stress Two-Way", 0.54, 0.60, 1.8, 0.56, "[P]", 0.35, None),
        ("S08_no_trade", "Range Macro — No Hero Trades", 0.00, 0.00, 0.0, -0.10, "[P][R]", None, None),
        (
            "S08_no_trade",
            "Range Macro — Basket Risk Cap",
            0.00,
            0.00,
            0.0,
            -0.10,
            "[P][A correlation risk]",
            None,
            "Cap correlated exposure at 3% total. Missing a trade costs zero.",
        ),
    ],
}

# (primary_title, evidence_tag, primary_notes, secondary_hint, confirmation_hint, fallback_hint)
Q4_MOD_META: dict[str, tuple[str, str, str, str, str, str]] = {
    "M01": (
        "Defensive — No Trade (Ambiguous)",
        "[Q AQR][R]",
        "ADX 15-25 transition. Regime uncertainty = reduce/skip.",
        "Observe structure only; no new risk.",
        "Wait for Q1–Q3 clarity before sizing.",
        "Wrong trade in Q4 costs real money — flat is valid.",
    ),
    "M02": (
        "Defensive — No Trade (Compression Noise)",
        "[P][R]",
        "Compressed tape without clean expansion — skip new entries.",
        "Avoid breakout lottery ahead of vol event.",
        "Stand down until range boundaries confirm.",
        "Missing a trade costs zero.",
    ),
    "M03": (
        "Defensive — No Trade (Asia Thin)",
        "[P]",
        "Illiquid drift; fade edge poor after costs.",
        "No chase through wide spreads.",
        "Protect capital over session transition.",
        "Wait for London/NY liquidity.",
    ),
    "M04": (
        "Defensive — No Trade (Open Chop)",
        "[P][I]",
        "First 5–15 min noisy or spread unstable.",
        "Do not hunt liquidity scans without MSS.",
        "Observe sweeps from distance; no chase without structural confirmation.",
        "Kill zone without MSS = stand down — no machine-gun entries.",
    ),
    "M05": (
        "Defensive — No Trade (Overlap Whipsaw)",
        "[P][R]",
        "Peak volume two-way; false breaks common.",
        "Flat is a position in overlap chop.",
        "Wait for directional commitment.",
        "Preserve mental and financial capital.",
    ),
    "M06": (
        "Defensive — No Trade (Late / Low Liquidity)",
        "[P][R]",
        "Trail only; no new speculative risk.",
        "Swap and slippage dominate edge.",
        "Book flat ahead of rollover window awareness.",
        "Wrong trade here prints permanently.",
    ),
    "M07": (
        "Defensive — No Trade (Pre-News)",
        "[A Lucca2015][P]",
        "News convexity dominates; calendar risk off.",
        "No lottery fades into binary events.",
        "Protect open risk; reduce if mandated.",
        "Wait for post-print structure.",
    ),
    "M08": (
        "Defensive — No Trade (Post-News Chop)",
        "[P]",
        "Volatility without structural follow-through.",
        "Fade only after validated range returns.",
        "Avoid revenge entries after spike.",
        "Clarity before size.",
    ),
    "M09": (
        "Defensive — No Trade (Sweep Without Confirmation)",
        "[P][I]",
        "Sweeps without reclaim/MSS = noise.",
        "Do not marry sweep bias blindly.",
        "Let order flow prove direction.",
        "Stand down until sweep resolves.",
    ),
    "M10": (
        "Defensive — No Trade (Spread Stress)",
        "[A][P spread kills edge]",
        "Edge negative after transaction costs.",
        "Wait for spread normalization.",
        "Trail runners only if already on.",
        "Capital preservation mode.",
    ),
    "M11": (
        "Defensive — No Trade (Trend/Ranging Exhaustion)",
        "[P]",
        "Late-cycle chop; breakout chase toxic.",
        "Fade only with tested playbook elsewhere.",
        "Reduce temptation trades.",
        "Wrong breakout costs more than missed fade.",
    ),
    "M12": (
        "Defensive — No Trade (Multi-TF Conflict)",
        "[P][Q]",
        "Higher TF disagrees with micro — no conviction.",
        "Wait for timeframe alignment.",
        "Do not average conflicting signals.",
        "Patience is the position.",
    ),
    "M13": (
        "Defensive — No Trade (Macro / Correlation Shock)",
        "[P][A correlation risk]",
        "USD and cross-asset shocks — reduce exposure.",
        "No correlated doubling across pairs.",
        "Basket risk cap enforced.",
        "Universal: missing a trade costs zero; wrong trade costs real money.",
    ),
}

Q2_PATCHES: dict[str, dict[str, object]] = {
    "Q2_M01_S01": {
        "signal_fn": "S01_ema_pullback",
        "name": "Trend High Vol Base — ATR Breakout",
        "win_rate_low": 0.52,
        "win_rate_high": 0.58,
        "rrr": 2.0,
        "ev": 0.50,
        "evidence": "[A][P] 0.5x size",
        "size_override": 0.50,
    },
    "Q2_M04_S01": {
        "signal_fn": "S01_ema_pullback",
        "name": "Trend High Vol London Kill Zone — EMA Pullback",
        "win_rate_low": 0.55,
        "win_rate_high": 0.62,
        "rrr": 2.5,
        "ev": 0.80,
        "evidence": "[P][I] 0.5x size",
        "size_override": 0.50,
    },
    "Q2_M09_S01": {
        "signal_fn": "S05_sweep_reclaim",
        "name": "Trend High Vol Sweep — Fast Reversal",
        "win_rate_low": 0.55,
        "win_rate_high": 0.62,
        "rrr": 2.0,
        "ev": 0.60,
        "evidence": "[P][I] 0.35x size fast exit",
        "size_override": 0.35,
    },
}


def _family(fn: str) -> str:
    if fn.startswith("S01") or fn.startswith("S07"):
        return "trend_momentum"
    if fn.startswith("S02"):
        return "breakout"
    if fn.startswith("S03") or fn.startswith("S06"):
        return "mean_reversion"
    if fn.startswith("S04") or fn.startswith("S05"):
        return "liquidity"
    if fn.startswith("S08"):
        return "defensive"
    return "general"


def _row_to_entry(q: str, m: str, slot_i: int, row: tuple) -> dict:
    sn = f"S0{slot_i + 1}"
    rid = f"{q}_{m}"
    sid = f"{rid}_{sn}"
    fnm, name, wl, wh, rrr, ev, evd, sz, notes = row
    e: dict = {
        "id": sid,
        "regime_id": rid,
        "slot": SLOTS[slot_i],
        "signal_fn": fnm,
        "name": name,
        "win_rate_low": wl,
        "win_rate_high": wh,
        "rrr": rrr,
        "ev": ev,
        "evidence": evd,
        "family": _family(fnm),
        "enabled": False,
        "status": "not_tested",
    }
    if sz is not None:
        e["size_override"] = sz
    if notes:
        e["notes"] = notes
    return e


def _expand_q1() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for m, rows in Q1_BLOCKS.items():
        for i in range(4):
            entry = _row_to_entry("Q1", m, i, rows[i])
            out[entry["id"]] = entry
    return out


def _expand_q3() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for m, rows in Q3_BLOCKS.items():
        for i in range(4):
            entry = _row_to_entry("Q3", m, i, rows[i])
            out[entry["id"]] = entry
    return out


def _expand_q4() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for m, meta in Q4_MOD_META.items():
        ptitle, evbase, n0, n1, n2, n3 = meta
        names = (
            ptitle,
            f"Defensive — Observe / No New ({m})",
            f"Defensive — Capital preservation ({m})",
            f"Defensive — Flat is valid ({m})",
        )
        notes = (n0, n1, n2, n3)
        for i in range(4):
            sn = f"S0{i + 1}"
            rid = f"Q4_{m}"
            sid = f"{rid}_{sn}"
            out[sid] = {
                "id": sid,
                "regime_id": rid,
                "slot": SLOTS[i],
                "signal_fn": "S08_no_trade",
                "name": names[i],
                "win_rate_low": 0.0,
                "win_rate_high": 0.0,
                "rrr": 0.0,
                "ev": -0.10,
                "evidence": evbase,
                "family": "defensive",
                "enabled": False,
                "status": "not_tested",
                "notes": notes[i],
            }
    return out


def _q2_from_q1(q1: dict) -> dict:
    e = copy.deepcopy(q1)
    rid = q1["regime_id"]
    suf = rid[2:]
    e["regime_id"] = f"Q2{suf}"
    e["id"] = f"Q2{suf}_{q1['id'].rsplit('_', 1)[-1]}"
    nm = q1["name"]
    if nm.startswith("Trend "):
        e["name"] = "Trend High Vol " + nm[6:]
    else:
        e["name"] = "Trend High Vol — " + nm
    wr_l, wr_h = float(q1["win_rate_low"]), float(q1["win_rate_high"])
    if wr_l > 0:
        e["win_rate_low"] = max(0.0, wr_l - 0.04)
        e["win_rate_high"] = max(0.0, wr_h - 0.04)
    ev_v = float(q1["ev"])
    if ev_v > 0:
        e["ev"] = round(ev_v * 0.92, 3)
    r = float(q1["rrr"])
    if r > 0:
        e["rrr"] = max(1.5, round(r - 0.25, 2))
    base_ev = (q1.get("evidence") or "").strip()
    if base_ev:
        e["evidence"] = f"{base_ev} [A][P] 0.5x size"
    else:
        e["evidence"] = "[A][P] 0.5x size"
    if q1["signal_fn"].startswith("S08"):
        e.pop("size_override", None)
    else:
        e["size_override"] = 0.5
    if e["id"] in Q2_PATCHES:
        patch = Q2_PATCHES[e["id"]]
        for k, v in patch.items():
            e[k] = v
    e["family"] = _family(str(e["signal_fn"]))
    return e


def _load_regime_logic() -> dict[str, str]:
    raw = yaml.safe_load(REG_PATH.read_text(encoding="utf-8-sig"))
    logic: dict[str, str] = {}
    for item in raw.get("strategies") or []:
        rid = item.get("regime_id")
        if rid and rid not in logic:
            logic[rid] = str(item.get("regime_logic") or "")
    return logic


def _ordered_ids() -> list[str]:
    ids: list[str] = []
    for mi in range(1, 14):
        m = f"M{mi:02d}"
        for q in ("Q1", "Q2", "Q3", "Q4"):
            for si in range(1, 5):
                ids.append(f"{q}_{m}_S0{si}")
    return ids


def main() -> None:
    regime_logic = _load_regime_logic()
    all_e: dict[str, dict] = {}
    for q1 in _expand_q1().values():
        all_e[q1["id"]] = q1
        q2 = _q2_from_q1(q1)
        all_e[q2["id"]] = q2
    for e in _expand_q3().values():
        all_e[e["id"]] = e
    for e in _expand_q4().values():
        all_e[e["id"]] = e

    strategies: list[dict] = []
    for sid in _ordered_ids():
        e = all_e[sid]
        rl = regime_logic.get(e["regime_id"], "")
        if rl:
            e["regime_logic"] = rl
        strategies.append(e)

    payload = {"version": 0.1, "total_strategies": 208, "strategies": strategies}
    text = (
        "# config/strategy_registry.yaml\n"
        "# All strategies start disabled. Enable ONLY after backtest validates.\n"
        "# Evidence codes: A=Academic P=Practitioner Q=Quant firm I=ICT\n"
        "# Q2: default size_override 0.5x; Q4: universal defensive — missing a trade costs zero.\n\n"
        + yaml.dump(payload, sort_keys=False, allow_unicode=True, default_flow_style=False)
    )
    REG_PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
