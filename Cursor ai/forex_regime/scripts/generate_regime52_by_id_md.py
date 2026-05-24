#!/usr/bin/env python3
"""Generate `forex_regime/regimes52/by_id/r01.md` … `r52.md` + index. Run from project root."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex_regime.regimes52.strategies.registry import strategies_for_regime  # noqa: E402
from forex_regime.regimes52.taxonomy import (  # noqa: E402
    QUADRANT_FOLDER_LABEL,
    REGIME_DOC,
    REGIME_NAME,
    quadrant_for_id,
)


def safe_filename_part(name: str) -> str:
    return "".join(c if c.isalnum() or c in " -" else "_" for c in name)[:60].strip().replace(" ", "_")


def main() -> int:
    out_dir = ROOT / "forex_regime" / "regimes52" / "by_id"
    out_dir.mkdir(parents=True, exist_ok=True)

    index_lines = [
        "# Regime index (52 files)",
        "",
        "One markdown file per regime ID. Definitions are **`REGIME_DOC`** in [`taxonomy.py`](../taxonomy.py).",
        "",
        "Python classifier: [`classify.py`](../classify.py) (`add_regime52_columns`).",
        "",
        "| ID | File | Short name | Quadrant |",
        "|----|------|------------|----------|",
    ]

    for rid in range(1, 53):
        section, definition = REGIME_DOC[rid]
        name = REGIME_NAME[rid]
        quad = quadrant_for_id(rid)
        qfolder = QUADRANT_FOLDER_LABEL.get(quad, "")
        slug = safe_filename_part(name)

        strat_lines = [
            "## Strategies (4 institutional / academic blueprints)",
            "",
            "Each regime gets **four** linked strategies. Signals run **only** when `regime52_id` equals this regime (see [`strategies/runner.py`](../strategies/runner.py) and `build_scorecard_table`).",
            "",
        ]
        for s in strategies_for_regime(rid):
            strat_lines.append(f"### `{s.key}` — {s.title}")
            strat_lines.append("")
            strat_lines.append(s.playbook)
            strat_lines.append("")
            strat_lines.append("**References:** " + " — ".join(s.references))
            strat_lines.append("")

        body = "\n".join(
            [
                f"# Regime {rid} — {name}",
                "",
                f"**Practical quadrant:** {quad} — {qfolder}",
                "",
                f"**Taxonomy section:** {section}",
                "",
                "## Definition (spec)",
                "",
                definition,
                "",
                "## Implementation",
                "",
                "- **Code:** [`classify.py`](../classify.py) — `add_regime52_columns()`.",
                "- **Parameters:** tune via [`Regime52Params`](../classify.py).",
                "- **Context-only IDs:** some regimes need `ctx_*` columns on the DataFrame (macro, VIX, DXY, calendars). See the docstring on `add_regime52_columns`.",
                "",
                *strat_lines,
                "## Scorecard (win-rate by R-multiple)",
                "",
                "Run `python scripts/regime_strategy_scorecard.py` to get per-strategy trade counts and `wr_1r`…`wr_4r` (max favorable excursion in multiples of initial risk before stop).",
                "",
                "## Quadrant deep-dive (if generated)",
                "",
                f"If you ran `_write_regime_docs.py`, extra notes may exist under project folder `{qfolder}/regimes/r{rid:02d}.md` when this ID is in that quadrant’s list.",
                "",
            ]
        )
        fn = out_dir / f"r{rid:02d}_{slug}.md"
        fn.write_text(body, encoding="utf-8")
        index_lines.append(f"| {rid} | [`{fn.name}`]({fn.name}) | {name} | {quad} |")

    (out_dir / "00_INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    print(f"Wrote 52 regime files + 00_INDEX.md in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
