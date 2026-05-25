from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv


DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_URL = "http://127.0.0.1:11434"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _compact_list(items: list[dict[str, Any]] | None, limit: int = 12) -> list[dict[str, Any]]:
    return list(items or [])[:limit]


def _context(request: dict[str, Any]) -> dict[str, Any]:
    backtest = request.get("backtest") if isinstance(request.get("backtest"), dict) else {}
    mt5 = request.get("mt5_comparison") if isinstance(request.get("mt5_comparison"), dict) else {}
    tester = request.get("mt5_tester") if isinstance(request.get("mt5_tester"), dict) else {}
    payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
    optimizer = request.get("optimizer") if isinstance(request.get("optimizer"), dict) else {}
    walk_forward = request.get("walk_forward") if isinstance(request.get("walk_forward"), dict) else {}
    monte_carlo = request.get("monte_carlo") if isinstance(request.get("monte_carlo"), dict) else {}
    selected_regime = request.get("selected_regime")

    return {
        "selected_regime": selected_regime,
        "payload": payload,
        "backtest_summary": backtest.get("summary", {}),
        "data_health": backtest.get("data_health", {}),
        "feature_summary": backtest.get("feature_summary", {}),
        "top_regime_performance": _compact_list(backtest.get("regime_performance"), 15),
        "top_strategy_performance": _compact_list(backtest.get("strategy_performance"), 20),
        "pattern_performance": _compact_list(backtest.get("pattern_performance"), 20),
        "mt5_model_comparison": mt5.get("rows") or backtest.get("mt5_model_comparison", []),
        "mt5_stability": mt5.get("stability", {}),
        "mt5_checks": mt5.get("checks", []),
        "mt5_tester_status": tester.get("status"),
        "approval_checklist": _compact_list(backtest.get("approval_checklist"), 20),
        "skipped_setups": _compact_list(backtest.get("skipped_setups"), 30),
        "optimizer_summary": optimizer.get("summary", {}),
        "optimizer_top_results": _compact_list(optimizer.get("results"), 10),
        "walk_forward_summary": walk_forward.get("summary", {}),
        "monte_carlo_summary": monte_carlo.get("summary", {}),
        "monte_carlo_risk": monte_carlo.get("risk_of_ruin", {}),
    }


def _rule_based_review(ctx: dict[str, Any]) -> dict[str, Any]:
    summary = ctx.get("backtest_summary", {})
    trades = _safe_int(summary.get("total_trades") or summary.get("trade_count"))
    pf = _safe_float(summary.get("profit_factor"))
    exp = _safe_float(summary.get("expectancy_R"))
    win = _safe_float(summary.get("win_rate"))
    skipped = _safe_int(summary.get("skipped_setups"))
    mt5_rows = ctx.get("mt5_model_comparison") or []
    real_tick = next((r for r in mt5_rows if r.get("model") == "every_tick_real_ticks"), {})
    real_pf = _safe_float(real_tick.get("profit_factor"))
    real_exp = _safe_float(real_tick.get("expectancy_R"))
    real_trades = _safe_int(real_tick.get("trade_count"))
    stability = ctx.get("mt5_stability") or {}
    data_health = ctx.get("data_health") or {}

    strengths: list[str] = []
    weaknesses: list[str] = []
    blockers: list[str] = []
    next_tests: list[str] = []
    ui_notes: list[str] = []

    if trades >= 100:
        strengths.append("Backtest has enough trades for first-pass statistical review.")
    elif trades > 0:
        weaknesses.append(f"Only {trades} trades found; treat any edge as provisional until sample size improves.")
    else:
        blockers.append("No local backtest trades are available for review.")

    if pf >= 1.2 and exp > 0:
        strengths.append(f"Local backtest edge is positive: PF {pf:.2f}, expectancy {exp:.3f}R.")
    elif pf > 1.0 and exp > 0:
        weaknesses.append(f"Local edge is small: PF {pf:.2f}, expectancy {exp:.3f}R. Good for research, not approval.")
    else:
        blockers.append(f"Local result is not approved: PF {pf:.2f}, expectancy {exp:.3f}R.")

    if win:
        strengths.append(f"Win rate is {(win * 100):.1f}%; compare this to break-even for selected RR before approval.")

    if skipped:
        weaknesses.append(f"{skipped} setup candidates were blocked. Review skipped reasons to learn where strategy logic fails.")

    if data_health.get("status") and data_health.get("status") != "OK":
        blockers.append(f"Data health is {data_health.get('status')}; fix data quality before trusting results.")

    if real_tick:
        if real_trades <= 0:
            blockers.append("Real-tick MT5 report is imported but has no realized trades.")
        elif real_pf >= 1.1 and real_exp > 0:
            strengths.append(f"Real-tick validation remains positive: PF {real_pf:.2f}, expectancy {real_exp:.3f}R.")
        else:
            blockers.append(f"Real-tick validation is weak: PF {real_pf:.2f}, expectancy {real_exp:.3f}R.")
    else:
        blockers.append("Real-tick MT5 report is missing. Do not approve tight-SL/scalping setups without it.")

    if stability.get("profit_factor_drift_1m_to_real_ticks") is not None:
        drift = _safe_float(stability.get("profit_factor_drift_1m_to_real_ticks"))
        if abs(drift) <= 0.35:
            strengths.append(f"Model PF drift is controlled at {drift:.2f}.")
        else:
            weaknesses.append(f"Model PF drift is large at {drift:.2f}; execution assumptions may be too optimistic.")

    next_tests.extend(
        [
            "Run the same setup on 1-Min OHLC, Every Tick, and Real Ticks, then compare PF/expectancy drift.",
            "Split the test into in-sample, out-of-sample, walk-forward, and Monte Carlo before funded-account use.",
            "Group failed trades by regime, strategy, session, spread percentile, pattern score, and alpha score.",
            "Raise min alpha and hard-filter spread/killzone for strict funded-account validation.",
        ]
    )
    ui_notes.extend(
        [
            "Show reviewer verdict beside MT5 model comparison so the user can see why a setup is approved or blocked.",
            "Keep skipped setup reasons visible because they explain why a strategy fails, not only whether it failed.",
        ]
    )

    if not blockers and len(weaknesses) <= 2:
        verdict = "RESEARCH_PASS_REVIEW_REQUIRED"
    elif strengths and not blockers:
        verdict = "WATCHLIST_ONLY"
    else:
        verdict = "NOT_APPROVED"

    return {
        "verdict": verdict,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "blockers": blockers,
        "next_tests": next_tests,
        "ui_notes": ui_notes,
        "risk_notes": [
            "This is research analysis only, not live trade permission.",
            "For funded accounts, approval should require real-tick validation, max drawdown control, and enough trades.",
        ],
    }


def _review_prompt(ctx: dict[str, Any]) -> str:
    return (
        "You are a senior quantitative forex research reviewer. "
        "Review this quant_forex_V10 backtest and MT5 validation context. "
        "Focus on practical funded-account readiness, regime purity, strategy failure reasons, "
        "pattern usefulness, execution/model stability, and what to test next. "
        "Return concise JSON only with keys: verdict, strengths, weaknesses, blockers, next_tests, ui_notes, risk_notes. "
        "Do not recommend live trading unless real-tick validation and sample size are acceptable.\n\n"
        f"CONTEXT_JSON:\n{json.dumps(ctx, ensure_ascii=True, default=str)[:30000]}"
    )


def _call_ollama(prompt: str, model: str, url: str, timeout: int) -> tuple[str | None, str | None]:
    endpoint = url.rstrip("/") + "/api/generate"
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json"}).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return None, str(exc)
    except TimeoutError as exc:
        return None, str(exc)
    try:
        parsed = json.loads(raw)
        return str(parsed.get("response") or ""), None
    except json.JSONDecodeError:
        return raw, None


def _parse_json_response(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(cleaned[start : end + 1])
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def run_ollama_review(request: dict[str, Any]) -> dict[str, Any]:
    load_dotenv()
    ctx = _context(request)
    fallback = _rule_based_review(ctx)
    model = str(request.get("model") or os.getenv("OLLAMA_MODEL") or DEFAULT_MODEL)
    url = str(request.get("ollama_url") or os.getenv("OLLAMA_URL") or DEFAULT_URL)
    timeout = max(5, min(int(request.get("timeout_seconds") or 120), 600))
    use_ollama = bool(request.get("use_ollama", True))
    prompt = _review_prompt(ctx)

    result: dict[str, Any] = {
        "review_id": f"review-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "ollama_url": url,
        "used_ollama": False,
        "status": "RULE_BASED_FALLBACK",
        "review": fallback,
        "raw_response": None,
        "warnings": [],
        "context_used": ctx,
    }

    if not use_ollama:
        result["warnings"].append("use_ollama=false, so only deterministic rule-based review was used.")
        return result

    raw, error = _call_ollama(prompt, model, url, timeout)
    if error:
        result["warnings"].append(f"Ollama unavailable: {error}. Rule-based review returned instead.")
        return result

    parsed = _parse_json_response(raw)
    result["raw_response"] = raw
    if not parsed:
        result["warnings"].append("Ollama responded but JSON parsing failed. Rule-based review returned instead.")
        return result

    merged = dict(fallback)
    for key in ["verdict", "strengths", "weaknesses", "blockers", "next_tests", "ui_notes", "risk_notes"]:
        if key in parsed:
            merged[key] = parsed[key]
    result["review"] = merged
    result["used_ollama"] = True
    result["status"] = "OLLAMA_REVIEW_COMPLETE"
    return result
