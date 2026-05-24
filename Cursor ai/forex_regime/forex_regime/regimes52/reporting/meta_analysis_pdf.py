from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from forex_regime.regimes52.analysis.cross_tf import tf_label
from forex_regime.regimes52.taxonomy import REGIME_NAME


def _text_page(pdf: PdfPages, title: str, body: str, fontsize: float = 9.0) -> None:
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.axis("off")
    ax.set_title(title, fontsize=14, fontweight="bold", pad=14, loc="left")
    ax.text(0.02, 0.92, body, transform=ax.transAxes, va="top", ha="left", fontsize=fontsize, linespacing=1.38)
    fig.tight_layout()
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _table_page(
    pdf: PdfPages,
    title: str,
    df: pd.DataFrame,
    col_labels: list[str] | None = None,
    max_rows: int = 35,
    fontsize: float = 7.0,
) -> None:
    if df.empty:
        _text_page(pdf, title, "(No rows.)", 11)
        return
    show = df.head(max_rows).copy()
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.axis("off")
    ax.set_title(title, fontsize=13, fontweight="bold", pad=10, loc="left")
    labels = col_labels if col_labels is not None else [str(c) for c in show.columns]
    table = ax.table(
        cellText=show.astype(str).values,
        colLabels=labels,
        loc="upper center",
        cellLoc="left",
        colLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(fontsize)
    table.scale(1.02, 1.25)
    fig.tight_layout()
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def write_meta_analysis_pdf(
    output: Path,
    *,
    multi: pd.DataFrame,
    best_per_tf: pd.DataFrame,
    regime_summary: pd.DataFrame,
    pairs_summary: pd.DataFrame,
    symbol: str,
    bars: int,
    tf_minutes_list: list[int],
    min_trades: int,
) -> None:
    """
    Summary PDF: cross-timeframe “best regime / best strategy” from long-form scorecard `multi`
    (must include tf_minutes, rank_score, and scorecard columns).
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tf_str = ", ".join(f"{m}m ({tf_label(m)})" for m in sorted(tf_minutes_list))
    scope = f"Symbol: {symbol}\nBars per timeframe run: {bars:,}\nTimeframes (minutes): {tf_str}\nMin trades per row to qualify: {min_trades}"

    methods = (
        "Method (descriptive — not a formal hypothesis test):\n\n"
        "1. Per timeframe: each row is one of 208 regime×strategy specs. "
        "`rank_score` blends wr_1r…wr_4r (MFE ≥ kR before ATR stop) and lightly "
        "penalizes trades < 8 (same as per-regime PDF).\n\n"
        "2. Per (regime, timeframe): among strategies with trades ≥ min_trades, "
        "select the strategy with highest rank_score (argmax). That is one "
        "discrete choice out of four candidates.\n\n"
        "3. Cross-timeframe: for each regime, take the rank_score of that winner "
        "on each TF where a winner exists. Report median / mean / std across TFs — "
        "a simple robustness read. `dominant_winner_*` is the strategy that won "
        "the argmax most often across TFs (mode).\n\n"
        "4. Pairs table: for each fixed (regime_id, strategy_key), require "
        "trades ≥ min_trades on each TF row, then aggregate median rank_score across TFs. "
        "Useful when the best regime should stay on one named playbook across horizons.\n\n"
        "5. Search space: 52 regimes × 4 strategies × len(timeframes) evaluated — "
        "reports compress this with medians and modes, not exhaustive enumeration."
    )

    with PdfPages(str(output)) as pdf:
        _text_page(
            pdf,
            "Cross-timeframe meta-analysis — best regimes & strategies",
            f"{scope}\n\n{methods}",
            fontsize=7.8,
        )

        if not regime_summary.empty:
            disp = regime_summary.head(30).copy()
            for c in ["median_best_rank", "mean_best_rank", "std_best_rank", "mean_wr2_of_winner"]:
                if c in disp.columns:
                    disp[c] = disp[c].map(lambda x: f"{float(x):.4f}")
        else:
            disp = regime_summary
        _table_page(
            pdf,
            f"Top regimes by median best-strategy rank_score across TFs (min_trades={min_trades})",
            disp,
        )

        if not pairs_summary.empty:
            dp = pairs_summary.head(40).copy()
            for c in ["median_rank", "mean_rank", "std_rank", "median_wr2"]:
                if c in dp.columns:
                    dp[c] = dp[c].map(lambda x: f"{float(x):.4f}")
        else:
            dp = pairs_summary
        _table_page(
            pdf,
            "Top (regime × strategy) pairs by median rank_score across TFs",
            dp,
        )

        # Heatmap: regime × tf for winner's rank_score
        if not best_per_tf.empty:
            heat = best_per_tf.pivot_table(
                index="regime_id",
                columns="tf_minutes",
                values="rank_score",
                aggfunc="first",
            )
            if not regime_summary.empty:
                top_ids = regime_summary["regime_id"].head(22).tolist()
                heat = heat.reindex(top_ids).dropna(how="all")
            if not heat.empty:
                fig, ax = plt.subplots(figsize=(11, max(6, 0.22 * len(heat))))
                data = heat.to_numpy(dtype=float)
                cax = ax.imshow(data, aspect="auto", cmap="YlGn", vmin=0.0, vmax=1.0)
                ax.set_xticks(range(len(heat.columns)))
                ax.set_xticklabels([str(c) for c in heat.columns], rotation=45, ha="right")
                ax.set_yticks(range(len(heat.index)))
                ax.set_yticklabels(
                    [f"R{r:02d} {REGIME_NAME.get(int(r), '')}"[:42] for r in heat.index],
                    fontsize=7,
                )
                ax.set_xlabel("tf_minutes")
                ax.set_title(
                    f"Winner rank_score heatmap (rows = top regimes by median)\n{symbol} · n={bars}"
                )
                fig.colorbar(cax, ax=ax, fraction=0.035, pad=0.04, label="rank_score")
                fig.tight_layout()
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)

        _text_page(
            pdf,
            "Coverage",
            f"Rows in combined long-form scorecard: {len(multi):,}\n"
            f"(regime, timeframe) cells with a per-TF winner: {len(best_per_tf)}\n"
            f"(Some cells have no strategy meeting min_trades — those regimes×TFs are omitted.)\n",
            10,
        )
