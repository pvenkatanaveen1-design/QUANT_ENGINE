"""
PDF Report Generator — ReportLab snapshot report.

Reads ``state/regime.json``, ``state/strategy.json``, ``state/data.json`` (optional)
and ``logs/trades.csv``. Use ``write_quick_report_state(snapshot)`` after an MT5
``build_snapshot`` to populate those files before ``generate_report()``.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

import pytz
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = _ROOT / "state"
OUTPUT_DIR = _ROOT / "reports" / "output"
STATE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

IST = pytz.timezone("Asia/Kolkata")

# Color palette
C_GREEN = colors.HexColor("#1d9e75")
C_RED = colors.HexColor("#e24b4a")
C_AMBER = colors.HexColor("#ef9f27")
C_BLUE = colors.HexColor("#378add")
C_DARK = colors.HexColor("#1a1a2e")
C_GRAY = colors.HexColor("#888780")
C_BG = colors.HexColor("#f8f9fa")
C_WHITE = colors.white

REGIME_COLORS = {
    "Q1": C_GREEN,
    "Q2": C_AMBER,
    "Q3": C_BLUE,
    "Q4": C_RED,
    "DEAD": C_GRAY,
}


def _pdf_direction(raw: str | None) -> str:
    d = str(raw or "NEUTRAL").upper()
    if d == "BUY":
        return "LONG"
    if d == "SELL":
        return "SHORT"
    return d if d in ("LONG", "SHORT", "NEUTRAL") else "NEUTRAL"


def _strategy_doc(snapshot: dict) -> dict:
    sel = snapshot.get("strategy_selection") or {}
    strategies = list(sel.get("strategies") or [])
    pick: dict = {}
    armed = next((s for s in strategies if s.get("status") == "ARMED"), None)
    if armed is not None:
        pick = armed
    elif strategies:
        pick = max(strategies, key=lambda s: float(s.get("score") or 0.0))
    score_100 = float(pick.get("score") or 0.0)
    score_10 = min(10, max(0, int(round(score_100 / 10.0))))
    checks = snapshot.get("signal_checks") or {}
    chk_labels = {
        "score_ok": "Signal score",
        "spread_ok": "Spread",
        "session_ok": "Session",
        "rr_ok": "Risk/reward",
        "regime_ok": "Regime",
    }
    reasons: list[tuple[str, bool]] = [(chk_labels.get(k, k), bool(v)) for k, v in sorted(checks.items())]
    cs = snapshot.get("current_signal")
    rrr = None
    if isinstance(cs, dict):
        rrr = cs.get("rr_ratio")
    return {
        "strategy_name": str(pick.get("name") or "—"),
        "score": score_10,
        "max_score": 10,
        "rrr_target": rrr if rrr is not None else "—",
        "description": str(sel.get("reason") or snapshot.get("label") or "—"),
        "reasons": reasons,
        "size_multiplier": float(sel.get("size_multiplier") or 0.0),
        "score_pct": int(round(min(100.0, max(0.0, score_100)))),
    }


def write_quick_report_state(snapshot: dict) -> None:
    """Persist dashboard snapshot dict to ``state/*.json`` for :func:`generate_report`."""
    try:
        conf_raw = snapshot.get("confidence")
        conf = int(round(float(conf_raw))) if conf_raw is not None else 0
    except (TypeError, ValueError):
        conf = 0
    quad = str(snapshot.get("quadrant") or "—").upper()
    regime_doc = {
        "regime": quad,
        "label": str(snapshot.get("label") or "Unknown"),
        "confidence": conf,
        "direction": _pdf_direction(snapshot.get("direction")),
        "session": str(snapshot.get("session") or "—"),
        "indicators": {
            "adx": snapshot.get("adx_14"),
            "rsi": "—",
            "atr_ratio": snapshot.get("atr_pct"),
            "current_price": snapshot.get("last_price"),
            "structure": "—",
        },
        "voters": {
            "indicator": {
                "vote": quad,
                "confidence": conf,
                "adx": snapshot.get("adx_14"),
                "atr_pct": snapshot.get("atr_pct"),
            },
            "structure": {"vote": "—", "confidence": 0, "note": "n/a"},
            "session": {
                "vote": str(snapshot.get("session") or "—"),
                "confidence": 50,
            },
        },
    }
    (STATE_DIR / "regime.json").write_text(json.dumps(regime_doc, indent=2), encoding="utf-8")
    (STATE_DIR / "strategy.json").write_text(json.dumps(_strategy_doc(snapshot), indent=2), encoding="utf-8")
    data_doc = {
        "meta": snapshot.get("meta") or {},
        "delivery_targets": {},
        "account": snapshot.get("account") or {},
        "tick": {"bid": snapshot.get("last_price"), "ask": snapshot.get("last_price")},
    }
    (STATE_DIR / "data.json").write_text(json.dumps(data_doc, indent=2), encoding="utf-8")


def read_state(filename: str) -> dict:
    path = STATE_DIR / f"{filename}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def read_trade_log() -> list[dict]:
    log_path = _ROOT / "logs" / "trades.csv"
    if not log_path.exists():
        return []
    try:
        with log_path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def make_styles() -> dict[str, ParagraphStyle]:
    _base = getSampleStyleSheet()
    _ = _base
    return {
        "title": ParagraphStyle(
            "title",
            fontSize=22,
            textColor=C_DARK,
            fontName="Helvetica-Bold",
            spaceAfter=4,
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            fontSize=11,
            textColor=C_GRAY,
            fontName="Helvetica",
            spaceAfter=20,
            alignment=TA_CENTER,
        ),
        "section": ParagraphStyle(
            "section",
            fontSize=13,
            textColor=C_DARK,
            fontName="Helvetica-Bold",
            spaceBefore=16,
            spaceAfter=8,
            borderPad=4,
        ),
        "body": ParagraphStyle(
            "body",
            fontSize=10,
            textColor=C_DARK,
            fontName="Helvetica",
            spaceAfter=6,
            leading=15,
        ),
        "small": ParagraphStyle(
            "small",
            fontSize=8,
            textColor=C_GRAY,
            fontName="Helvetica",
            spaceAfter=4,
        ),
        "regime_label": ParagraphStyle(
            "regime_label",
            fontSize=16,
            textColor=C_WHITE,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
            spaceAfter=2,
        ),
        "metric_val": ParagraphStyle(
            "metric_val",
            fontSize=18,
            textColor=C_DARK,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        ),
        "metric_label": ParagraphStyle(
            "metric_label",
            fontSize=8,
            textColor=C_GRAY,
            fontName="Helvetica",
            alignment=TA_CENTER,
        ),
    }


def make_header_table(now_ist: datetime, symbol: str) -> Table:
    sym = symbol or "—"
    data = [
        [
            Paragraph(
                "⚡ QUANT ENGINE 2026",
                ParagraphStyle("h", fontSize=18, fontName="Helvetica-Bold", textColor=C_DARK),
            ),
            Paragraph(
                f"{sym} · {now_ist.strftime('%d %b %Y %H:%M')} IST",
                ParagraphStyle(
                    "ts",
                    fontSize=9,
                    textColor=C_GRAY,
                    fontName="Helvetica",
                    alignment=TA_RIGHT,
                ),
            ),
        ]
    ]
    t = Table(data, colWidths=[10 * cm, 9 * cm])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, C_GRAY),
            ]
        )
    )
    return t


def make_regime_card(regime_data: dict, styles: dict) -> Table:
    _ = styles
    regime = regime_data.get("regime", "—")
    label = regime_data.get("label", "Unknown")
    confidence = regime_data.get("confidence", 0)
    direction = regime_data.get("direction", "NEUTRAL")
    session = regime_data.get("session", "—")
    color = REGIME_COLORS.get(str(regime).upper(), C_GRAY)

    indicators = regime_data.get("indicators", {})
    adx = indicators.get("adx", "—")
    rsi = indicators.get("rsi", "—")
    atr_ratio = indicators.get("atr_ratio", "—")
    price = indicators.get("current_price", "—")
    structure = indicators.get("structure", "—")

    dir_arrow = "▲ LONG" if direction == "LONG" else "▼ SHORT" if direction == "SHORT" else "◆ NEUTRAL"

    header_data = [
        [
            Paragraph(
                f"{regime}",
                ParagraphStyle(
                    "rl",
                    fontSize=20,
                    fontName="Helvetica-Bold",
                    textColor=C_WHITE,
                    alignment=TA_CENTER,
                ),
            ),
            Paragraph(
                f"{label}",
                ParagraphStyle("ll", fontSize=13, fontName="Helvetica-Bold", textColor=C_WHITE),
            ),
            Paragraph(
                f"Confidence: {confidence}%\n{dir_arrow}",
                ParagraphStyle("cl", fontSize=10, fontName="Helvetica", textColor=C_WHITE, alignment=TA_RIGHT),
            ),
        ]
    ]
    header = Table(header_data, colWidths=[3 * cm, 9 * cm, 6 * cm])
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), color),
                ("PADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )

    ind_data = [
        ["ADX", "RSI", "ATR Ratio", "Price", "Structure", "Session"],
        [str(adx), str(rsi), str(atr_ratio), str(price), structure, session],
    ]
    ind_table = Table(ind_data, colWidths=[3 * cm] * 6)
    ind_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), C_BG),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("PADDING", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.3, C_GRAY),
                ("TEXTCOLOR", (0, 1), (-1, 1), C_DARK),
            ]
        )
    )

    wrapper = Table([[header], [ind_table]], colWidths=[18 * cm])
    wrapper.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, C_GRAY),
                ("PADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return wrapper


def make_voter_table(regime_data: dict) -> Table:
    voters = regime_data.get("voters", {})

    headers = ["Voter", "Vote", "Confidence", "Details"]
    rows: list[list[str]] = [headers]

    voter_map = {
        "indicator": "Indicator (ADX+ATR+RSI)",
        "structure": "Market Structure",
        "session": "Session Timing",
    }

    for key, display in voter_map.items():
        v = voters.get(key, {})
        vote = v.get("vote", "—")
        conf = v.get("confidence", 0)

        details_parts: list[str] = []
        for k2, v2 in v.items():
            if k2 not in ("vote", "confidence"):
                details_parts.append(f"{k2}={v2}")
        details = " | ".join(details_parts[:3])

        rows.append([display, str(vote), f"{conf}%", details])

    t = Table(rows, colWidths=[5 * cm, 4 * cm, 3 * cm, 6 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), C_DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("ALIGN", (2, 0), (2, -1), "CENTER"),
                ("PADDING", (0, 0), (-1, -1), 7),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_BG]),
                ("GRID", (0, 0), (-1, -1), 0.3, C_GRAY),
            ]
        )
    )
    return t


def make_strategy_table(strategy_data: dict) -> Table | Paragraph:
    if not strategy_data:
        return Paragraph("No strategy data available", ParagraphStyle("ns", fontSize=9, textColor=C_GRAY))

    score = strategy_data.get("score", 0)
    max_score = strategy_data.get("max_score", 10)
    reasons = strategy_data.get("reasons", [])

    headers = ["Check", "Result", "Points"]
    rows: list[list[str]] = [headers]

    for reason_text, passed in reasons:
        rows.append(
            [
                str(reason_text),
                "✓ Pass" if passed else "✗ Fail",
                "+2" if passed else "0",
            ]
        )

    rows.append(["TOTAL SCORE", f"{score} / {max_score}", f"{strategy_data.get('score_pct', 0)}%"])

    t = Table(rows, colWidths=[9 * cm, 5 * cm, 4 * cm])

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), C_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -2), "Helvetica"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("PADDING", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.3, C_GRAY),
        ("BACKGROUND", (0, -1), (-1, -1), C_BG),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [C_WHITE, C_BG]),
    ]

    for i, (_, passed) in enumerate(reasons, start=1):
        bg = colors.HexColor("#e8f8f2") if passed else colors.HexColor("#fdf0f0")
        style.append(("BACKGROUND", (0, i), (-1, i), bg))
        text_color = C_GREEN if passed else C_RED
        style.append(("TEXTCOLOR", (1, i), (1, i), text_color))

    t.setStyle(TableStyle(style))
    return t


def make_delivery_targets_table(targets: dict) -> Table | Paragraph:
    if not targets:
        return Paragraph("No delivery targets", ParagraphStyle("nd", fontSize=9, textColor=C_GRAY))

    current = targets.get("current_price", 0)

    level_map = [
        ("Previous Day High", "prev_day_high", "resistance"),
        ("Previous Day Low", "prev_day_low", "support"),
        ("Weekly High", "weekly_high", "resistance"),
        ("Weekly Low", "weekly_low", "support"),
        ("Asian Session High", "asian_high", "resistance"),
        ("Asian Session Low", "asian_low", "support"),
        ("Round Number Above", "round_above", "magnet"),
        ("Round Number Below", "round_below", "magnet"),
    ]

    rows: list[list[str]] = [["Level", "Price", "Distance", "Type"]]
    row_level_types: list[str] = []

    for display, key, level_type in level_map:
        if key in targets and targets[key] not in (None, "", 0):
            try:
                price = float(targets[key])
            except (TypeError, ValueError):
                continue
            try:
                cur = float(current)
            except (TypeError, ValueError):
                cur = 0.0
            dist: float | str = round(price - cur, 2) if cur else "—"
            dist_str = f"+{dist}" if isinstance(dist, float) and dist > 0 else str(dist)
            rows.append([display, f"{price:.2f}", dist_str, level_type])
            row_level_types.append(level_type)

    if len(rows) == 1:
        return Paragraph(
            "No delivery targets calculated",
            ParagraphStyle("nd", fontSize=9, textColor=C_GRAY),
        )

    t = Table(rows, colWidths=[6 * cm, 4 * cm, 4 * cm, 4 * cm])

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), C_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("PADDING", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.3, C_GRAY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_BG]),
    ]

    for i, level_type in enumerate(row_level_types, start=1):
        if level_type == "resistance":
            style.append(("TEXTCOLOR", (1, i), (1, i), C_RED))
        elif level_type == "support":
            style.append(("TEXTCOLOR", (1, i), (1, i), C_GREEN))

    t.setStyle(TableStyle(style))
    return t


def make_trades_table(trades: list[dict]) -> Table:
    if not trades:
        rows = [["No trades logged yet"]]
        t = Table(rows, colWidths=[18 * cm])
        t.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("TEXTCOLOR", (0, 0), (-1, -1), C_GRAY),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return t

    headers = ["Time", "Dir", "Strategy", "Regime", "Score", "Entry", "P&L"]
    rows: list[list[str]] = [headers]

    total_pnl = 0.0
    for trade in trades[-20:]:
        pnl_raw = trade.get("pnl", "0")
        try:
            pnl = float(pnl_raw)
            total_pnl += pnl
            pnl_str = f"${pnl:+.2f}"
        except (TypeError, ValueError):
            pnl_str = str(pnl_raw)
            pnl = 0.0

        time_str = str(trade.get("timestamp", ""))[:16]
        strat = str(trade.get("strategy", "—"))
        rows.append(
            [
                time_str,
                str(trade.get("direction", "—")),
                strat[:15],
                str(trade.get("regime", "—")),
                str(trade.get("score", "—")),
                str(trade.get("entry_price", "—")),
                pnl_str,
            ]
        )

    rows.append(["", "", "", "", "TOTAL P&L", "", f"${total_pnl:+.2f}"])

    t = Table(rows, colWidths=[3.5 * cm, 1.5 * cm, 4 * cm, 2 * cm, 1.5 * cm, 2.5 * cm, 3 * cm])

    style: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), C_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -2), "Helvetica"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.3, C_GRAY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [C_WHITE, C_BG]),
        ("BACKGROUND", (0, -1), (-1, -1), C_BG),
    ]

    for i, trade in enumerate(trades[-20:], start=1):
        try:
            pnl = float(trade.get("pnl", 0))
            style.append(("TEXTCOLOR", (6, i), (6, i), C_GREEN if pnl >= 0 else C_RED))
        except (TypeError, ValueError):
            pass

        direction = str(trade.get("direction", ""))
        if direction == "BUY":
            style.append(("TEXTCOLOR", (1, i), (1, i), C_GREEN))
        elif direction == "SELL":
            style.append(("TEXTCOLOR", (1, i), (1, i), C_RED))

    t.setStyle(TableStyle(style))
    return t


def generate_report(output_path: str | None = None) -> str:
    now_ist = datetime.now(IST)

    if output_path is None:
        filename = f"QUANT_REPORT_{now_ist.strftime('%Y%m%d_%H%M')}.pdf"
        output_path = str(OUTPUT_DIR / filename)

    regime_data = read_state("regime")
    strategy_data = read_state("strategy")
    data_snapshot = read_state("data")
    trades = read_trade_log()

    delivery_targets = data_snapshot.get("delivery_targets", {})
    account = data_snapshot.get("account", {})
    header_symbol = str((data_snapshot.get("meta") or {}).get("symbol") or "—")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = make_styles()
    story: list = []

    story.append(make_header_table(now_ist, header_symbol))
    story.append(Spacer(1, 16))

    if account:
        balance = float(account.get("balance", 0) or 0)
        equity = float(account.get("equity", 0) or 0)
        profit = float(account.get("profit", 0) or 0)
        is_demo = bool(account.get("is_demo", True))

        acc_data = [
            ["Balance", "Equity", "Open P&L", "Account Type"],
            [
                f"${balance:,.2f}",
                f"${equity:,.2f}",
                f"${profit:+.2f}",
                "DEMO" if is_demo else "LIVE",
            ],
        ]
        acc_table = Table(acc_data, colWidths=[4.5 * cm] * 4)
        acc_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), C_BG),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("PADDING", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.3, C_GRAY),
                    ("TEXTCOLOR", (2, 1), (2, 1), C_GREEN if profit >= 0 else C_RED),
                    ("TEXTCOLOR", (3, 1), (3, 1), C_BLUE if is_demo else C_RED),
                ]
            )
        )
        story.append(acc_table)
        story.append(Spacer(1, 16))

    story.append(Paragraph("Current Market Regime", styles["section"]))

    if regime_data:
        story.append(make_regime_card(regime_data, styles))
        story.append(Spacer(1, 12))
        story.append(Paragraph("Three Voter Analysis", styles["section"]))
        story.append(make_voter_table(regime_data))
        story.append(Spacer(1, 12))
    else:
        story.append(Paragraph("No regime data available. Run the engine or call write_quick_report_state first.", styles["body"]))

    story.append(Paragraph("Strategy Selection & Scoring", styles["section"]))

    if strategy_data:
        strat_name = strategy_data.get("strategy_name", "—")
        score = strategy_data.get("score", 0)
        rrr = strategy_data.get("rrr_target", "—")
        desc = strategy_data.get("description", "—")

        summary_data = [
            ["Selected Strategy", "Score", "Target RRR", "Size"],
            [
                str(strat_name),
                f"{score}/10",
                f"1:{rrr}" if rrr not in ("", "—", None) else "—",
                f"{int(float(strategy_data.get('size_multiplier', 1) or 0) * 100)}%",
            ],
        ]
        sum_table = Table(summary_data, colWidths=[7 * cm, 3 * cm, 4 * cm, 4 * cm])
        sum_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), C_BG),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("PADDING", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.3, C_GRAY),
                    (
                        "TEXTCOLOR",
                        (1, 1),
                        (1, 1),
                        C_GREEN
                        if int(float(score)) >= 7
                        else C_AMBER
                        if int(float(score)) >= 5
                        else C_RED,
                    ),
                ]
            )
        )
        story.append(sum_table)
        story.append(Spacer(1, 8))
        story.append(Paragraph(f"Strategy: {desc}", styles["body"]))
        story.append(Spacer(1, 8))
        story.append(make_strategy_table(strategy_data))
        story.append(Spacer(1, 12))
    else:
        story.append(Paragraph("No strategy selected yet.", styles["body"]))

    story.append(Paragraph("Delivery Targets", styles["section"]))
    story.append(
        Paragraph(
            "Institutional price levels — entry, stop, and profit targets align to these.",
            styles["small"],
        )
    )
    story.append(Spacer(1, 6))
    story.append(make_delivery_targets_table(delivery_targets))
    story.append(Spacer(1, 12))

    story.append(PageBreak())
    story.append(make_header_table(now_ist, header_symbol))
    story.append(Spacer(1, 16))
    story.append(Paragraph("Trade Log — Last 20 Trades", styles["section"]))
    story.append(make_trades_table(trades))
    story.append(Spacer(1, 12))

    story.append(HRFlowable(width="100%", thickness=0.5, color=C_GRAY))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            f"Generated by QUANT ENGINE 2026 · {now_ist.strftime('%d %b %Y %H:%M:%S')} IST · DEMO ACCOUNT ONLY",
            ParagraphStyle(
                "footer",
                fontSize=7,
                textColor=C_GRAY,
                fontName="Helvetica",
                alignment=TA_CENTER,
            ),
        )
    )

    doc.build(story)
    print(f"PDF generated: {output_path}")
    return output_path


if __name__ == "__main__":
    out = generate_report()
    print(f"Done: {out}")
