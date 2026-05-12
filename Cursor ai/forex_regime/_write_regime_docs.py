# One-off writer: UTF-8 markdown into quadrant folders. Run: python _write_regime_docs.py
from __future__ import annotations

import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from forex_regime.regimes52.taxonomy import REGIME_DOC as REGIMES

Q1 = {1, 2, 4, 11, 13, 17, 18, 22, 24, 36, 38, 47}
Q2 = {3, 5, 16, 19, 20, 25, 30, 32, 44, 46}
Q3 = {6, 7, 8, 9, 10, 12, 27, 29, 33, 34, 37, 39, 40}
Q4 = {14, 15, 21, 23, 26, 28, 31, 35, 41, 42, 43, 45, 48, 51, 52}

QUADS = {
    "Q1 \u2014 Trend Low Volatility": Q1,
    "Q2 \u2014 Trend High Volatility": Q2,
    "Q3 \u2014 Range Low Volatility": Q3,
    "Q4 \u2014 Transition or Chaos": Q4,
}

IMPORTANT_FOLDER = "Important Regimes \u2014 15 Must Know"

ACADEMIC_AND_INDUSTRY = """
## Evidence and references (starting points, not exhaustive)

- **Regime switching / latent states:** Hamilton (1989), *Econometrica* — Markov switching in macro series; foundation for “Hidden Markov / regime” thinking. Handbook: `https://econweb.ucsd.edu/~jhamilto/handbook_regimes.pdf`
- **Momentum (3–12m):** Jegadeesh & Titman (1993), *Journal of Finance* — momentum in equities; later work extends across assets.
- **Momentum crashes / crowding:** Daniel & Moskowitz (2016), *Journal of Financial Economics* — momentum crash dynamics around stress/rebounds; related crowding/tail-risk debates (e.g., Yan SSRN; Barroso–Edelen–Karehnke JFQA).
- **Volatility clustering:** Bollerslev (1986) GARCH; vast empirical literature on persistence in conditional variance.
- **Carry / funding liquidity:** classic FX carry empirical work (e.g., Brunnermeier, Nagel, Pedersen “carry trades and currency crashes” line of research).
- **Macro policy transmission:** QE/QT and portfolio balance channel (Bernanke et al. 2019 survey book chapter references); event-study FOMC literature.
- **Market microstructure:** order imbalance and absorption concepts tie to Hasbrouck, O’Hara, modern LOB microstructure surveys.

**Institutional practice note:** Desks rarely label bars with one academic model. They stack *narrative* (macro), *positioning* (COT, vol surface), *microstructure* (session/imbalance), and *risk* (correlation / VaR shocks). Your quadrants are a *risk-management* map, not a single generative model.
"""

IMPORTANT_15 = [
    (1, "Stop Hunt Manipulation (35)", [35]),
    (2, "Bull Trend with OB and Institutional Alignment", [1, 39]),
    (3, "Rate Cycle Macro", [16, 17]),
    (4, "Risk-Off Safe Haven", [25]),
    (5, "Wyckoff Accumulation Spring", [10]),
    (6, "Momentum Regime", [4]),
    (7, "Hidden Markov Regime Switching", [45]),
    (8, "London Kill Zone OB Entry", [38, 39]),
    (9, "Volatility Squeeze Breakout", [9]),
    (10, "COT Extreme Contrarian", [51]),
    (11, "Post-News Reversal", [31]),
    (12, "Mean Reversion Z-Score", [7]),
    (13, "Dollar DXY Intermarket", [49, 50]),
    (14, "Absorption Exhaustion Microstructure", [42, 43]),
    (15, "Stagflation", [20]),
]


def quad_slug(name: str) -> str:
    if name.startswith("Q1"):
        return "Q1"
    if name.startswith("Q2"):
        return "Q2"
    if name.startswith("Q3"):
        return "Q3"
    return "Q4"


def regime_detail_md(rid: int) -> str:
    sec, desc = REGIMES[rid]
    body = f"# Regime {rid}\n\n**Taxonomy:** {sec}\n\n**Definition (your spec):** {desc}\n"
    body += ACADEMIC_AND_INDUSTRY
    body += """
## How institutional traders tend to use this bucket

- **Book-level:** shift gross/leverage, tighten outliers, change VAR/correlation assumptions.
- **Execution:** favor VWAP/TWAP vs opportunistic liquidity; widen slippage tolerances in Q4-style chaos.
- **Hedging:** index/FX/Vol overlays when macro + risk-off stacks (e.g., 16+19+25).

## Practical measurement ideas (FX / futures)

- Trend strength: ADX(14), Choppiness, slope of 50/200 EMA, structure rules (HH/HL).
- Volatility: ATR%, realized vol, Bollinger width, GARCH sigma.
- Positioning: COT net specs, ETF flows (equities), FX futures OI.
- Events: implied vol around FOMC/CPI, calendar overlays.
- Micro: session returns, volume vs median, bid-ask bounce proxies (where available).

---
*This file is educational synthesis — validate every signal on your symbols and regime definitions before risking capital.*
"""
    return body


def write_catalog() -> None:
    lines = [
        "# Full regime catalog (52 IDs)",
        "",
        "Numbering follows your SECTION 1→10 order.",
        "",
    ]
    for rid in range(1, 53):
        sec, desc = REGIMES[rid]
        lines.append(f"## {rid} — {sec.split('—')[1].strip() if '—' in sec else sec}")
        lines.append(desc)
        lines.append("")
    (BASE / "catalog" / "FULL_TAXONOMY_52.md").parent.mkdir(parents=True, exist_ok=True)
    (BASE / "catalog" / "FULL_TAXONOMY_52.md").write_text("\n".join(lines), encoding="utf-8")

    collapse = """# How regimes collapse into 4 practical quadrants (your map)

| Quadrant | Regime IDs |
|----------|------------|
| Q1 — Trend Low Volatility | 1, 2, 4, 11, 13, 17, 18, 22, 24, 36, 38, 47 |
| Q2 — Trend High Volatility | 3, 5, 16, 19, 20, 25, 30, 32, 44, 46 |
| Q3 — Range Low Volatility | 6, 7, 8, 9, 10, 12, 27, 29, 33, 34, 37, 39, 40 |
| Q4 — Transition or Chaos | 14, 15, 21, 23, 26, 28, 31, 35, 41, 42, 43, 45, 48, 51, 52 |

Use per-quadrant `OVERVIEW.md` and `regimes/rXX.md` for depth.
"""
    (BASE / "catalog" / "QUADRANT_COLLAPSE.md").write_text(collapse, encoding="utf-8")


def resolve_quad_dir(folder_key: str) -> Path:
    """Match existing folder like 'Q1 — Trend Low Volatility' (em dash)."""
    prefix = folder_key.split()[0]  # "Q1"
    for d in os.listdir(BASE):
        if d.startswith(prefix + " "):
            return BASE / d
    return BASE / folder_key


def write_quadrant_folder(quad_dir: Path, ids: set[int]) -> None:
    quad_dir.mkdir(parents=True, exist_ok=True)
    qs = quad_slug(quad_dir.name)
    overview = [
        f"# {quad_dir.name}",
        "",
        f"**Quadrant:** {qs} — practical bucket for risk, sizing, and playbook selection.",
        "",
        "## Regime IDs in this quadrant (your mapping)",
        "",
        ", ".join(str(i) for i in sorted(ids)),
        "",
        "## Regime files",
        "",
        "Each `regimes/rXX.md` expands definition + academic/industry lenses + measurement stubs.",
        "",
    ]
    (quad_dir / "OVERVIEW.md").write_text("\n".join(overview), encoding="utf-8")
    reg_dir = quad_dir / "regimes"
    reg_dir.mkdir(exist_ok=True)
    for rid in sorted(ids):
        (reg_dir / f"r{rid:02d}.md").write_text(regime_detail_md(rid), encoding="utf-8")


def write_important_folder() -> None:
    p = BASE / IMPORTANT_FOLDER
    p.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Important Regimes — 15 Must Know (Deep Stack)",
        "",
        "These are the highest ROI labels to internalize for *narrative + execution + risk*.",
        "",
        "| Priority | Name | Core regime IDs |",
        "|----------|------|-------------------|",
    ]
    for pr, name, rids in IMPORTANT_15:
        lines.append(f"| {pr} | {name} | {', '.join(str(x) for x in rids)} |")
    lines.append("")
    lines.append(ACADEMIC_AND_INDUSTRY)
    lines.append("")
    for pr, name, rids in IMPORTANT_15:
        lines.append(f"## {pr}. {name}")
        lines.append("")
        for rid in rids:
            sec, desc = REGIMES[rid]
            lines.append(f"### Regime {rid} — {sec}")
            lines.append(desc)
            lines.append("")
        lines.append("**Desk translation:** map this priority to your actual triggers (session rules, OB/FVG validity tests, macro surprise matrix, vol targeting).")
        lines.append("")
    (p / "THE_15_DEEP_DIVE.md").write_text("\n".join(lines), encoding="utf-8")

    readme = [
        "# Folder guide",
        "",
        "- `THE_15_DEEP_DIVE.md` — consolidated depth on the 15 priorities.",
        "- Cross-reference quadrant folders for per-ID files if an ID spans multiple “priority” bundles.",
        "",
    ]
    (p / "README.md").write_text("\n".join(readme), encoding="utf-8")


def main() -> None:
    write_catalog()
    for folder_key, ids in QUADS.items():
        quad_dir = resolve_quad_dir(folder_key)
        write_quadrant_folder(quad_dir, ids)
    write_important_folder()
    print("Wrote catalog/, quadrant regime files, and Important Regimes folder.")


if __name__ == "__main__":
    main()
