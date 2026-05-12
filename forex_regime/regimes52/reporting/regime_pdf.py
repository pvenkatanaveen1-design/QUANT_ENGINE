from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from forex_regime.regimes52.classify import Regime52Params
from forex_regime.regimes52.strategies.signals import side_rule_label, signal_kind_legend
from forex_regime.regimes52.taxonomy import REGIME_DOC, REGIME_NAME, quadrant_for_id


def _truncate_text(s: str, max_len: int = 56) -> str:
    t = str(s).strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _sample_scope_lines(
    *,
    symbol: str,
    tf_label: str,
    tf_minutes: int | None,
    n_all: int,
) -> tuple[str, str]:
    """
    Short line (chart/table subtitles) and long line (cover) for symbol + timeframe + sample.
    """
    sym = symbol.strip() or "(symbol)"
    if tf_minutes is not None and tf_minutes > 0:
        tf_long = (
            f"Bar timeframe: {tf_minutes} minutes ({tf_label})"
            if tf_label
            else f"Bar timeframe: {tf_minutes} minutes"
        )
        tf_short = (
            f"{tf_minutes}-minute bars ({tf_label})" if tf_label else f"{tf_minutes}-minute bars"
        )
    elif tf_label:
        tf_long = f"Bar timeframe: {tf_label}"
        tf_short = tf_label
    else:
        tf_long = "Bar timeframe: (pass tf_minutes when building the PDF)"
        tf_short = "timeframe n/a"
    short = f"{sym} · {tf_short} · n={n_all:,} bars"
    long_body = f"Symbol: {sym}\n{tf_long}\nTotal bars in backtest sample: {n_all:,}"
    return short, long_body


def enrich_strategy_table(sub: pd.DataFrame) -> pd.DataFrame:
    """
    Add ranking helpers for PDF / console: composite win-quality score, frequency ratios.
    `sub` = scorecard rows for one regime_id (typically 4 strategies).
    """
    if sub.empty:
        return sub
    out = sub.copy()
    bars = int(out["bars_in_regime"].iloc[0]) if "bars_in_regime" in out.columns else 0
    out["score_wr_blend"] = (
        0.20 * out["wr_1r"]
        + 0.35 * out["wr_2r"]
        + 0.30 * out["wr_3r"]
        + 0.15 * out["wr_4r"]
    )
    if bars > 0:
        out["trades_per_1k_regime_bars"] = (out["trades"] / bars * 1000.0).round(2)
        out["regime_pct_of_all_bars"] = None  # filled by caller if needed
    else:
        out["trades_per_1k_regime_bars"] = 0.0
    # Down-weight tiny samples so rank is interpretable
    out["sample_factor"] = np.where(out["trades"] < 8, 0.82, 1.0)
    out["rank_score"] = (out["score_wr_blend"] * out["sample_factor"]).round(4)
    return out.sort_values("rank_score", ascending=False).reset_index(drop=True)


def _format_regime52_params(p: Regime52Params) -> str:
    lines = ["Regime52Params — shared by the 52-regime classifier and signal indicators:\n"]
    for f in fields(Regime52Params):
        lines.append(f"  {f.name}: {getattr(p, f.name)!r}")
    lines.append(
        "\nClassifier rules (thresholds per regime id, claim order, optional ctx_* columns) "
        "live in forex_regime/regimes52/classify.py — add context columns to activate "
        "macro/event regimes when those rows have data."
    )
    return "\n".join(lines)


def _pdf_text_page(pdf: PdfPages, title: str, body: str, fontsize: float = 9.0) -> None:
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.axis("off")
    ax.set_title(title, fontsize=14, fontweight="bold", pad=14, loc="left")
    ax.text(0.02, 0.92, body, transform=ax.transAxes, va="top", ha="left", fontsize=fontsize, linespacing=1.38)
    fig.tight_layout()
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _strategies_and_legends_body(
    sub_sc: pd.DataFrame, p: Regime52Params, scope_short: str
) -> str:
    if sub_sc.empty:
        return "(No scorecard rows for this regime.)"
    parts: list[str] = [
        f"Sample: {scope_short}\n",
        "Strategy rows for this regime (terms). Entries are counted only when "
        "regime52_id matches this regime; signal math is shared across all regimes "
        "in the same quadrant — only labels differ.\n",
    ]
    sub = sub_sc.sort_values("strategy_key")
    order_kinds: list[str] = []
    for sk in sub["signal_kind"]:
        if sk not in order_kinds:
            order_kinds.append(sk)
    for _, row in sub.iterrows():
        sr = int(row["side_rule"])
        parts.append(
            f"• {row['strategy_key']}: {row['strategy_title']}\n"
            f"  signal_kind={row['signal_kind']!r}; {side_rule_label(sr)}"
        )
    parts.append("\nSignal kinds — numeric values and windows (same for every regime using that kind):\n")
    for sk in order_kinds:
        parts.append(f"\n[{sk}]\n{signal_kind_legend(sk, p)}")
    return "\n".join(parts)


def _occurrence_yearly_monthly(df: pd.DataFrame, regime_id: int) -> tuple[pd.Series, pd.Series]:
    sub = df.loc[df["regime52_id"] == int(regime_id), "time"].dropna()
    if sub.empty:
        return pd.Series(dtype=int), pd.Series(dtype=int)
    ts = pd.to_datetime(sub, utc=True)
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    yearly = ts.dt.year.value_counts().sort_index()
    monthly = ts.dt.to_period("M").value_counts().sort_index()
    monthly.index = monthly.index.astype(str)
    return yearly, monthly


def append_regime_detail_to_pdf(
    pdf: PdfPages,
    *,
    df: pd.DataFrame,
    scorecard: pd.DataFrame,
    regime_id: int,
    symbol: str = "",
    tf_label: str = "",
    total_bars: int | None = None,
    max_months_chart: int = 72,
    p: Regime52Params | None = None,
    tf_minutes: int | None = None,
    include_classifier_params: bool = True,
) -> None:
    """
    Append pages for one regime to an existing PdfPages instance.
    When ``include_classifier_params`` is False, skip the long Regime52Params page
    (use for regimes 2–52 in a combined institutional document).
    """
    if p is None:
        p = Regime52Params()
    rid = int(regime_id)
    name = REGIME_NAME.get(rid, f"ID {rid}")
    quad = quadrant_for_id(rid)

    sub_sc = scorecard[scorecard["regime_id"] == rid].copy()
    enriched = enrich_strategy_table(sub_sc)

    mask_r = df["regime52_id"] == rid
    n_regime = int(mask_r.sum())
    n_all = int(len(df)) if total_bars is None else int(total_bars)
    pct = 100.0 * n_regime / n_all if n_all else 0.0

    yearly, monthly = _occurrence_yearly_monthly(df, rid)
    if max_months_chart and len(monthly) > max_months_chart:
        monthly = monthly.iloc[-max_months_chart:]

    scope_short, scope_long = _sample_scope_lines(
        symbol=symbol, tf_label=tf_label, tf_minutes=tf_minutes, n_all=n_all
    )

    # --- Cover (per regime) ---
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.axis("off")
    title = f"Regime {rid}: {name}\n{quad}"
    ax.text(0.5, 0.90, title, ha="center", va="top", fontsize=18, fontweight="bold", wrap=True)
    ax.text(
        0.5,
        0.805,
        scope_short,
        ha="center",
        va="top",
        fontsize=12,
        fontweight="bold",
        color="#1a1a1a",
    )
    body = (
        f"{scope_long}\n\n"
        f"Bars with this regime (primary label): {n_regime:,} ({pct:.2f}% of sample)\n"
        f"Quadrant: {quad}\n\n"
        "Win rates (wr_1r–wr_4r): fraction of trades where price reached ≥1R…≥4R "
        "favorable excursion before ATR-based stop (see scorecard script).\n"
        "rank_score: blends wr_1r–wr_4r and lightly penalizes strategies with trades < 8.\n\n"
        "Next pages: Regime52Params (classifier + indicator windows) if included, this regime’s taxonomy line, "
        "then each strategy’s name, signal_kind, side rule, and numeric thresholds."
    )
    ax.text(0.08, 0.74, body, ha="left", va="top", fontsize=11, linespacing=1.45)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

    if include_classifier_params:
        _pdf_text_page(
            pdf,
            f"Regime detection — parameter terms and values (Regime52Params)\n{scope_short}",
            _format_regime52_params(p),
            fontsize=8.5,
        )
    doc = REGIME_DOC.get(rid)
    if doc:
        sec, defin = doc
        tax_body = f"Section: {sec}\n\nNarrative / rule summary:\n{defin}"
    else:
        tax_body = "(No REGIME_DOC entry for this id.)"
    _pdf_text_page(
        pdf,
        f"This regime (id {rid}) — taxonomy terms\n{scope_short}",
        tax_body,
        fontsize=10.0,
    )
    _pdf_text_page(
        pdf,
        f"Strategies for regime {rid} — names, keys, sides, signal values\n{scope_short}",
        _strategies_and_legends_body(sub_sc, p, scope_short),
        fontsize=8.3,
    )

    if n_regime == 0:
        _pdf_text_page(
            pdf,
            "Frequency",
            "No bars classified with this regime in the sample — yearly/monthly charts omitted.",
            fontsize=11.0,
        )
    else:
        # --- Yearly counts ---
        fig, ax = plt.subplots(figsize=(11, 6))
        ax.bar(yearly.index.astype(str), yearly.values, color="steelblue", edgecolor="navy", alpha=0.85)
        ax.set_title(f"Regime {rid} — bar counts by year (UTC)\n{scope_short}")
        ax.set_xlabel("Year")
        ax.set_ylabel("Bar count")
        plt.xticks(rotation=45, ha="right")
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # --- Monthly counts ---
        fig, ax = plt.subplots(figsize=(11, 6))
        x = np.arange(len(monthly))
        ax.bar(x, monthly.values, color="darkseagreen", edgecolor="darkgreen", alpha=0.85)
        ax.set_xticks(x[:: max(1, len(x) // 20)])
        ax.set_xticklabels(monthly.index[:: max(1, len(x) // 20)], rotation=60, ha="right", fontsize=8)
        ax.set_title(
            f"Regime {rid} — bar counts by month (UTC, last {len(monthly)} months)\n{scope_short}"
        )
        ax.set_ylabel("Bar count")
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

    # --- Strategy ranking table (text) ---
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.axis("off")
    ax.set_title(
        f"Strategies ranked by rank_score — regime {rid}\n{scope_short}",
        fontsize=14,
        fontweight="bold",
        pad=12,
    )

    if enriched.empty:
        ax.text(0.5, 0.5, "No strategy rows (scorecard empty).", ha="center", va="center", fontsize=12)
    else:
        display = enriched[
            [
                "strategy_key",
                "strategy_title",
                "trades",
                "wr_1r",
                "wr_2r",
                "wr_3r",
                "wr_4r",
                "score_wr_blend",
                "trades_per_1k_regime_bars",
                "rank_score",
            ]
        ].copy()
        display["strategy_title"] = display["strategy_title"].map(lambda s: _truncate_text(str(s), 50))
        # Format for readability
        for c in ["wr_1r", "wr_2r", "wr_3r", "wr_4r", "score_wr_blend", "rank_score"]:
            display[c] = display[c].map(lambda v: f"{float(v):.3f}")
        col_labels = [
            "key",
            "strategy_name",
            "trades",
            "wr_1r",
            "wr_2r",
            "wr_3r",
            "wr_4r",
            "wr_blend",
            "tr/1k_reg",
            "rank",
        ]
        table = ax.table(
            cellText=display.values,
            colLabels=col_labels,
            loc="center",
            cellLoc="center",
            colLoc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(7.5)
        table.scale(1.02, 1.5)
    fig.tight_layout()
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

    # --- Horizontal bar: rank_score ---
    if not enriched.empty and enriched["trades"].sum() > 0:
        d = enriched[enriched["trades"] > 0].head(8)
        if not d.empty:
            fig, ax = plt.subplots(figsize=(11, 5.5))
            labels = [
                f"{r['strategy_key']}: {_truncate_text(str(r['strategy_title']), 44)}"
                for _, r in d.iloc[::-1].iterrows()
            ]
            x = d["rank_score"].tolist()[::-1]
            ax.barh(labels, x, color="coral", edgecolor="darkred", alpha=0.9)
            ax.set_xlabel("rank_score (higher = better blended R-performance)")
            ax.set_title(f"Top strategies by rank_score — regime {rid}\n{scope_short}")
            ax.grid(axis="x", alpha=0.3)
            fig.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)


def write_regime_detail_pdf(
    output: Path,
    *,
    df: pd.DataFrame,
    scorecard: pd.DataFrame,
    regime_id: int,
    symbol: str = "",
    tf_label: str = "",
    total_bars: int | None = None,
    max_months_chart: int = 72,
    p: Regime52Params | None = None,
    tf_minutes: int | None = None,
) -> None:
    """
    One PDF per regime: cover stats, yearly/monthly bar incidence, ranked strategy table + bar chart.

    `df` must include `time`, `regime52_id` (from `prepare_regime_and_signals`).
    `scorecard` = full output of `build_scorecard_table` on the same `df`.
    `p` should match the params used to build `df` / scorecard (defaults to Regime52Params()).
    `tf_minutes` should match the MT5 chart period (e.g. 60 for H1) for explicit timeframe labeling.
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(str(output)) as pdf:
        append_regime_detail_to_pdf(
            pdf,
            df=df,
            scorecard=scorecard,
            regime_id=regime_id,
            symbol=symbol,
            tf_label=tf_label,
            total_bars=total_bars,
            max_months_chart=max_months_chart,
            p=p,
            tf_minutes=tf_minutes,
            include_classifier_params=True,
        )


def _tf_label_from_minutes(minutes: int) -> str:
    if minutes < 60:
        return f"M{minutes}"
    if minutes % 60 == 0:
        return f"H{minutes // 60}"
    return f"{minutes}m"


def append_cover_and_freq_to_pdf(
    pdf: PdfPages,
    *,
    df: pd.DataFrame,
    symbol: str,
    tf_minutes: int,
    live_quadrant: str | None = None,
    live_label: str | None = None,
    spread: str | None = None,
    generated_iso: str = "",
    p: Regime52Params | None = None,
) -> None:
    """Cover page + full-sample regime frequency bar chart (institutional header)."""
    if p is None:
        p = Regime52Params()
    tf_label = _tf_label_from_minutes(int(tf_minutes))
    n_all = len(df)
    scope_short, scope_long = _sample_scope_lines(
        symbol=symbol, tf_label=tf_label, tf_minutes=tf_minutes, n_all=n_all
    )
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.axis("off")
    ax.text(
        0.5,
        0.92,
        "Regime Engine — institutional analytics",
        ha="center",
        va="top",
        fontsize=20,
        fontweight="bold",
    )
    ax.text(
        0.5,
        0.84,
        f"{scope_short}",
        ha="center",
        va="top",
        fontsize=13,
        fontweight="bold",
    )
    cover_body = (
        f"{scope_long}\n"
        f"Generated (UTC): {generated_iso or '(local)'}\n\n"
        f"Live headline quadrant: {live_quadrant or '—'}\n"
        f"Live label: {live_label or '—'}\n"
        f"Spread (snapshot): {spread or '—'}\n\n"
        "Chunked report: cover + frequency overview; each regime is a separate PDF part merged client-side.\n\n"
        "Win rates are MFE hit rates vs ATR-based stop — not dollar equity."
    )
    ax.text(0.08, 0.72, cover_body, ha="left", va="top", fontsize=10.5, linespacing=1.42)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

    try:
        freq = df["regime52_id"].value_counts().sort_index()
        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.bar([f"R{i:02d}" for i in freq.index.astype(int)], freq.values, color="#4a90d9", alpha=0.85)
        ax.set_title(f"Bar count by regime52_id (sample)\n{scope_short}")
        ax.set_ylabel("Bars")
        plt.xticks(rotation=90, fontsize=7)
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)
    except Exception:
        pass


def pdf_bytes_cover_and_freq(
    *,
    df: pd.DataFrame,
    scorecard: pd.DataFrame,
    symbol: str,
    tf_minutes: int,
    live_quadrant: str | None = None,
    live_label: str | None = None,
    spread: str | None = None,
    generated_iso: str = "",
    p: Regime52Params | None = None,
) -> bytes:
    """Small PDF: cover + frequency chart only."""
    import io

    bio = io.BytesIO()
    with PdfPages(bio) as pdf:
        append_cover_and_freq_to_pdf(
            pdf,
            df=df,
            symbol=symbol,
            tf_minutes=tf_minutes,
            live_quadrant=live_quadrant,
            live_label=live_label,
            spread=spread,
            generated_iso=generated_iso,
            p=p,
        )
    return bio.getvalue()


def pdf_bytes_single_regime(
    *,
    df: pd.DataFrame,
    scorecard: pd.DataFrame,
    regime_id: int,
    symbol: str,
    tf_minutes: int,
    include_classifier_params: bool,
    p: Regime52Params | None = None,
    max_months_chart: int = 48,
) -> bytes:
    """PDF for one regime (typical chunk for chunked HTTP)."""
    import io

    n_all = len(df)
    tf_label = _tf_label_from_minutes(int(tf_minutes))
    bio = io.BytesIO()
    with PdfPages(bio) as pdf:
        append_regime_detail_to_pdf(
            pdf,
            df=df,
            scorecard=scorecard,
            regime_id=int(regime_id),
            symbol=symbol,
            tf_label=tf_label,
            total_bars=n_all,
            max_months_chart=max_months_chart,
            p=p,
            tf_minutes=tf_minutes,
            include_classifier_params=include_classifier_params,
        )
    return bio.getvalue()


def write_institutional_regime52_pdf(
    output: Path,
    *,
    df: pd.DataFrame,
    scorecard: pd.DataFrame,
    symbol: str,
    tf_minutes: int,
    live_quadrant: str | None = None,
    live_label: str | None = None,
    spread: str | None = None,
    generated_iso: str = "",
    p: Regime52Params | None = None,
    max_months_chart: int = 48,
) -> None:
    """
    Single PDF: institutional cover + optional global summary, then regimes 1–52 sequentially
    (four strategies each via scorecard rows). First regime includes classifier params reference;
    regimes 2–52 omit the duplicate params appendix.
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if p is None:
        p = Regime52Params()
    tf_label = _tf_label_from_minutes(int(tf_minutes))
    n_all = len(df)

    with PdfPages(str(output)) as pdf:
        append_cover_and_freq_to_pdf(
            pdf,
            df=df,
            symbol=symbol,
            tf_minutes=tf_minutes,
            live_quadrant=live_quadrant,
            live_label=live_label,
            spread=spread,
            generated_iso=generated_iso,
            p=p,
        )

        for rid in range(1, 53):
            append_regime_detail_to_pdf(
                pdf,
                df=df,
                scorecard=scorecard,
                regime_id=rid,
                symbol=symbol,
                tf_label=tf_label,
                total_bars=n_all,
                max_months_chart=max_months_chart,
                p=p,
                tf_minutes=tf_minutes,
                include_classifier_params=(rid == 1),
            )
