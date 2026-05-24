from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from systems.analysis import db as analysis_db


def _signal_payload(sig: Any) -> dict[str, Any] | None:
    if sig is None:
        return None
    if is_dataclass(sig) and not isinstance(sig, type):
        return asdict(sig)
    if hasattr(sig, "__dict__"):
        return {k: v for k, v in vars(sig).items() if not k.startswith("_")}
    return {"repr": str(sig)}


def list_journal(limit: int = 100) -> list[dict[str, Any]]:
    return analysis_db.list_decisions(limit=limit)


def append_journal(payload: dict[str, Any]) -> dict[str, Any]:
    return analysis_db.append_decision(payload)


def log_decision(result: Any) -> None:
    """Persist one decision: SQLite journal + append-only JSONL under data/analysis (via analysis_db)."""
    regime = getattr(result, "regime_result", None)
    regime_id = getattr(regime, "regime_id", None) if regime else None
    meta = getattr(result, "metadata", None) or {}
    sel = getattr(result, "selected_signal", None)
    analysis_db.append_decision(
        {
            "decision_id": getattr(result, "decision_id", None),
            "symbol": getattr(result, "symbol", None),
            "timeframe": meta.get("timeframe"),
            "regime_id": regime_id,
            "strategy_id": getattr(sel, "strategy_id", None) if sel else None,
            "action": getattr(result, "final_action", None),
            "reason": "; ".join((getattr(result, "reasons", None) or [])[-6:]),
            "payload": {
                "regime": regime_id,
                "regime_confidence": getattr(regime, "confidence", None) if regime else None,
                "signal": _signal_payload(sel),
                "mode": meta.get("mode"),
                "metadata": meta,
                "reasons": getattr(result, "reasons", None),
            },
        }
    )


def load_history(limit: int = 200, action_filter: str = "all") -> list[dict[str, Any]]:
    """Same source as the Journal UI (SQLite): newest first. Shape matches legacy JSONL API (final_action, timestamp)."""
    raw = analysis_db.list_decisions(limit=max(limit * 4, limit))
    out: list[dict[str, Any]] = []
    for row in raw:
        action = row.get("action") or ""
        if action_filter != "all" and action != action_filter:
            continue
        payload = row.get("payload") or {}
        out.append(
            {
                "decision_id": row.get("decision_id"),
                "timestamp": row.get("created_at"),
                "symbol": row.get("symbol"),
                "regime_id": row.get("regime_id"),
                "confidence": payload.get("regime_confidence"),
                "final_action": action,
                "reasons": payload.get("reasons") or ([row["reason"]] if row.get("reason") else []),
                "metadata": payload.get("metadata") or payload,
            }
        )
        if len(out) >= limit:
            break
    return out
