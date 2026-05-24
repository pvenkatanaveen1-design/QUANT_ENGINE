from __future__ import annotations

from core.models.signal import Signal, SignalScore, StrategyCandidate


def order_candidates(candidates: list[StrategyCandidate]) -> list[StrategyCandidate]:
    slot_order = {"primary": 0, "secondary": 1, "confirmation": 2, "fallback": 3}
    return sorted(candidates, key=lambda candidate: slot_order.get(candidate.slot, 99))


def choose_top_signal(scores: list[SignalScore]) -> Signal | None:
    if not scores:
        return None
    return max(scores, key=lambda item: item.score).signal

