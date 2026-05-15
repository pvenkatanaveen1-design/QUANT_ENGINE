"""Kelly-style fractional sizing helpers (documentation math; sizing UI uses risk_rules + position_sizer)."""

from __future__ import annotations


def kelly_full_fraction(*, win_rate: float, payoff_ratio: float) -> float:
    """
    f* = (p * b - q) / b  with p = win rate, b = avg_win / avg_loss, q = 1 - p.
    Returns fraction of equity (0..1+); can exceed 1 for extreme edge — callers must cap.
    """
    p = max(0.0, min(1.0, float(win_rate)))
    b = max(1e-12, float(payoff_ratio))
    q = 1.0 - p
    return (p * b - q) / b


def kelly_quarter_fraction(*, win_rate: float, payoff_ratio: float) -> float:
    """Quarter Kelly (common practice firm recommendation)."""
    return kelly_full_fraction(win_rate=win_rate, payoff_ratio=payoff_ratio) / 4.0


def prop_capped_risk_fraction(
    *,
    win_rate: float,
    payoff_ratio: float,
    max_risk_fraction: float = 0.02,
    kelly_scale: float = 0.25,
) -> float:
    """
    Apply fractional Kelly then cap at max risk per trade (e.g. 2% prop ceiling).
    kelly_scale 0.25 = quarter Kelly.
    """
    p = max(0.0, min(1.0, float(win_rate)))
    b = max(1e-12, float(payoff_ratio))
    raw = kelly_full_fraction(win_rate=p, payoff_ratio=b) * float(kelly_scale)
    cap = max(0.0, float(max_risk_fraction))
    return max(0.0, min(cap, raw))
