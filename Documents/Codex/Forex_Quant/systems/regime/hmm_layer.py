"""
Optional HMM regime layer (Hamilton 1989 / hybrid detectors per QUANTA master Phase G).

Not implemented: stays behind this module so core Q1–Q4 classifier remains authoritative.
Wire `try_hmm_refinement` when research validates baseline regimes on long samples.
"""

from __future__ import annotations

from typing import Any


def hmm_refinement_available() -> bool:
    return False


def try_hmm_refinement(rows: list[dict[str, Any]], symbol: str, timeframe: str) -> dict[str, Any] | None:
    """
    Future: return posterior state probs / suggested regime adjustments.
    Currently always None — does not change routing.
    """
    if not rows:
        return None
    return None
