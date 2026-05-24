from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from forex_regime.config import RegimeParams
from forex_regime.regime import REGIME_RANGE, REGIME_TREND_DOWN, REGIME_TREND_UP, add_regime_columns

REGIME_ORDER = [REGIME_TREND_UP, REGIME_RANGE, REGIME_TREND_DOWN]


def format_timeframe_minutes(minutes: int) -> str:
    m = int(minutes)
    if m < 60:
        fx = {1: "M1", 2: "M2", 5: "M5", 10: "M10", 15: "M15", 30: "M30"}.get(m)
        tag = fx or f"M{m}"
        return f"{m} minute{'s' if m != 1 else ''} ({tag})"
    if m % 60 == 0:
        h = m // 60
        return f"{h} hour{'s' if h != 1 else ''} (H{h})"
    return f"{m} minutes"


@dataclass(frozen=True)
class TimeframeSection:
    minutes: int
    bars_requested: int
    bars_loaded: int
    bars_after_warmup: int
    utc_first: pd.Timestamp | None
    utc_last: pd.Timestamp | None
    year_rows: list[list[Any]]  # [year, up_n, up_pct, range_n, range_pct, dn_n, dn_pct, total]


def compute_year_breakdown(df_ohlc: pd.DataFrame, rp: RegimeParams) -> pd.DataFrame:
    """Return DataFrame with columns year, TREND_UP, RANGE, TREND_DOWN, TOTAL + pct_*"""
    out = add_regime_columns(df_ohlc.copy(), rp).dropna(subset=["regime", "atr"]).reset_index(drop=True)
    out["year"] = out["time"].dt.year
    ct = out.groupby(["year", "regime"]).size().unstack(fill_value=0)
    for col in REGIME_ORDER:
        if col not in ct.columns:
            ct[col] = 0
    ct = ct[REGIME_ORDER].copy()
    ct["TOTAL"] = ct.sum(axis=1)
    denom = ct["TOTAL"].replace(0, pd.NA)
    for col in REGIME_ORDER:
        ct[f"pct_{col}"] = (ct[col] / denom * 100.0).fillna(0.0)
    ct = ct.reset_index()
    return ct


def sections_from_ohlc(
    minutes: int,
    bars_requested: int,
    df_ohlc: pd.DataFrame,
    rp: RegimeParams,
) -> TimeframeSection:
    if df_ohlc.empty:
        return TimeframeSection(
            minutes=minutes,
            bars_requested=bars_requested,
            bars_loaded=0,
            bars_after_warmup=0,
            utc_first=None,
            utc_last=None,
            year_rows=[],
        )
    df = df_ohlc.sort_values("time").reset_index(drop=True)
    warm = add_regime_columns(df, rp).dropna(subset=["regime", "atr"])
    ct = compute_year_breakdown(df, rp)
    rows: list[list[Any]] = []
    for _, r in ct.sort_values("year").iterrows():
        y = int(r["year"])
        rows.append(
            [
                y,
                int(r[REGIME_TREND_UP]),
                float(r[f"pct_{REGIME_TREND_UP}"]),
                int(r[REGIME_RANGE]),
                float(r[f"pct_{REGIME_RANGE}"]),
                int(r[REGIME_TREND_DOWN]),
                float(r[f"pct_{REGIME_TREND_DOWN}"]),
                int(r["TOTAL"]),
            ]
        )
    return TimeframeSection(
        minutes=minutes,
        bars_requested=bars_requested,
        bars_loaded=len(df_ohlc),
        bars_after_warmup=len(warm),
        utc_first=df["time"].iloc[0],
        utc_last=df["time"].iloc[-1],
        year_rows=rows,
    )


def write_regime_year_pdf(
    output: Path,
    *,
    symbol: str,
    regime_params: RegimeParams,
    sections: list[TimeframeSection],
    title: str = "Regime frequency by year and timeframe",
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    page = landscape(letter)
    doc = SimpleDocTemplate(
        str(output),
        pagesize=page,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title=title,
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        name="H1Custom",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=12,
        alignment=TA_CENTER,
    )
    h2 = ParagraphStyle(name="H2Custom", parent=styles["Heading2"], fontSize=12, spaceAfter=8)
    body = ParagraphStyle(name="BodySmall", parent=styles["Normal"], fontSize=9, spaceAfter=6)
    mono = ParagraphStyle(name="Mono", parent=styles["Code"], fontSize=8, spaceAfter=4)

    story: list[Any] = []
    story.append(Paragraph(title, h1))
    story.append(
        Paragraph(
            f"Generated (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} &nbsp; Symbol: <b>{symbol}</b>",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph("Methodology (operational classifier)", h2))
    story.append(
        Paragraph(
            "This PDF counts how many <b>closed bars</b> fell into each <i>coded</i> regime, by <b>calendar year (UTC)</b> "
            "and by <b>candle timeframe</b>. Regime names are:",
            body,
        )
    )
    story.append(
        Paragraph(
            "<b>TREND_UP</b> — bullish spread of EMAs vs ATR; "
            "<b>TREND_DOWN</b> — bearish spread; "
            "<b>RANGE</b> — neutral / tight spread per threshold rules.",
            body,
        )
    )
    story.append(
        Paragraph(
            f"Parameters: EMA fast={regime_params.ema_fast}, slow={regime_params.ema_slow}, "
            f"ATR period={regime_params.atr_period} (SMA of true range), "
            f"trend ATR mult=±{regime_params.trend_atr_mult}, range ATR mult={regime_params.range_atr_mult}.",
            mono,
        )
    )
    story.append(
        Paragraph(
            "<i>Note:</i> The 52-label narrative taxonomy in <b>catalog/</b> is documentation-only unless you implement "
            "detectors for each label. This report reflects the Python/MT5 EMA–ATR regime engine only.",
            body,
        )
    )
    story.append(PageBreak())

    for sec in sections:
        label = format_timeframe_minutes(sec.minutes)
        story.append(Paragraph(f"Timeframe: {label}", h2))
        if sec.utc_first is not None and sec.utc_last is not None:
            story.append(
                Paragraph(
                    f"OHLC window (UTC): {sec.utc_first} &nbsp;→&nbsp; {sec.utc_last}<br/>"
                    f"Bars loaded: {sec.bars_loaded} (requested up to {sec.bars_requested}) — "
                    f"after indicator warmup: {sec.bars_after_warmup}",
                    body,
                )
            )
        else:
            story.append(Paragraph("<b>No data</b> returned for this timeframe (check server history).", body))
            story.append(PageBreak())
            continue

        hdr = [
            "Year (UTC)",
            "TREND_UP count",
            "TREND_UP %",
            "RANGE count",
            "RANGE %",
            "TREND_DOWN count",
            "TREND_DOWN %",
            "BAR TOTAL",
        ]
        data: list[list[str]] = [hdr]
        for row in sec.year_rows:
            y, up_n, up_p, rg_n, rg_p, dn_n, dn_p, tot = row
            data.append(
                [
                    str(y),
                    f"{up_n:,}",
                    f"{up_p:.1f}",
                    f"{rg_n:,}",
                    f"{rg_p:.1f}",
                    f"{dn_n:,}",
                    f"{dn_p:.1f}",
                    f"{tot:,}",
                ]
            )
        col_widths = [0.9 * inch, 1.0 * inch, 0.75 * inch, 1.0 * inch, 0.75 * inch, 1.05 * inch, 0.85 * inch, 1.0 * inch]
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#f0f4f8")]),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 0.12 * inch))
        story.append(PageBreak())

    if story and isinstance(story[-1], PageBreak):
        story.pop()
    doc.build(story)
