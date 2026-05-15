from __future__ import annotations

from typing import Any


def hmm_status() -> dict[str, Any]:
    return {
        "status": "future_phase",
        "model": "Hamilton-style hidden Markov regime layer",
        "enabled": False,
        "reason": "Kept behind the research gate until deterministic regime detection, backtest persistence, and paper validation are stable.",
        "required_before_enable": [
            "minimum backtest runs saved",
            "paper-trade journal populated",
            "walk-forward validation complete",
            "operator approval",
        ],
    }

