"""Suggested trade signals (read-only orchestration; execution separate)."""

from forex_regime.signals.signal_generator import Signal, generate_signal

__all__ = ["Signal", "generate_signal"]
