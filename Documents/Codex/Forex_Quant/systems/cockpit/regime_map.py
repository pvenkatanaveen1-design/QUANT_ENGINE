from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict

from core.config_manager import ConfigManager
from systems.strategy.signals import SIGNAL_CODE_TO_TEMPLATE
from systems.strategy_router import backend as strategy_backend


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class StrategyDef(TypedDict):
    id: str
    strategy_id: str
    regime_id: str
    name: str
    slot: str
    family: str
    signal_fn: str
    signal_template: str
    entry_logic: str
    entry_trigger: str
    stop_rule: str
    tp_rule: str
    min_rr: float
    expected_wr_low: float
    expected_wr_high: float
    expected_rrr: float
    expected_ev_r: float
    size_mult: float
    filters: list[str]
    invalidations: list[str]
    evidence: list[str]
    sources: list[dict[str, Any]]
    notes: str
    status: str
    research_active: bool
    live_allowed: bool


class RegimeDef(TypedDict):
    regime_id: str
    description: str
    base_regime: str
    modifier: str
    detection_summary: str
    tradable: bool
    risk_posture: str
    priority: str
    focus: str
    base_wr_adjustment: float
    base_rrr_adjustment: float
    size_multiplier: float
    risk_multiplier: float
    thresholds_source: str
    modifier_definition: dict[str, Any]
    primary: StrategyDef
    secondary: StrategyDef
    confirmation: StrategyDef
    fallback: StrategyDef
    strategies: list[StrategyDef]
    research_model: dict[str, Any]


MODIFIER_DEFINITIONS: dict[str, dict[str, Any]] = {
    "M01": {
        "name": "Clean Liquid Market",
        "detection": "No other modifier triggered. Normal session, spread, volume.",
        "delta_wr": 0.0,
        "delta_rrr": 0.0,
        "size_mult": 1.0,
        "risk_mult": 1.0,
        "tradable": True,
        "notes": "Baseline. No adjustment to strategy values.",
    },
    "M02": {
        "name": "Volatility Compression",
        "detection": "BB_width_percentile <= 25th over last 20 bars. [A Bollerslev1986]",
        "delta_wr": 0.02,
        "delta_rrr": 0.3,
        "size_mult": 0.75,
        "risk_mult": 0.75,
        "tradable": True,
        "notes": "80% probability of expansion within 5-10 bars. Direction: 65% in prior trend. [P]",
    },
    "M03": {
        "name": "Asia Session (00:00-06:00 GMT)",
        "detection": "classify_session() returns 'Asia'.",
        "delta_wr": -0.04,
        "delta_rrr": -0.3,
        "size_mult": 0.5,
        "risk_mult": 0.5,
        "tradable": True,
        "notes": "BIS: Asia = lowest volume. JPY/AUD/NZD pairs most active. Spread widens on EUR/USD.",
    },
    "M04": {
        "name": "London Open Kill Zone (07:00-10:00 GMT)",
        "detection": "classify_session() returns 'London_Open'. kill_zone_active = True.",
        "delta_wr": 0.06,
        "delta_rrr": 0.4,
        "size_mult": 1.0,
        "risk_mult": 1.0,
        "tradable": True,
        "notes": (
            "WHY M04 ADDS +6% WR: London open is the highest-volume single window in 24h "
            "(BIS data). Institutional order flow is largest in first 3 hours. Asian range "
            "sweep occurs 3-4 of 5 days (Zaye Capital [P]). Smart money uses this window "
            "to fill large orders by triggering retail stops above/below the Asian range, "
            "creating the sweep pattern. Both Q1_M04 and Q3_M04 are the highest-probability "
            "setups in their families. NY Open (12:00-13:00 GMT) has same kill_zone_active=True "
            "and same delta values."
        ),
        "kill_zone_hours_gmt": "07:00-10:00 and 12:00-13:00",
        "academic_basis": "BIS Triennial Survey: London handles largest FX volume share.",
        "practitioner_basis": "ICT Kill Zones, Zaye Capital Markets, SMC community. 3-4/5 days frequency.",
    },
    "M05": {
        "name": "London-NY Overlap (13:00-16:00 GMT)",
        "detection": "classify_session() returns 'London_NY_Overlap'.",
        "delta_wr": 0.03,
        "delta_rrr": 0.2,
        "size_mult": 1.0,
        "risk_mult": 1.0,
        "tradable": True,
        "notes": "Highest absolute volume of the day. Both sessions active simultaneously.",
    },
    "M06": {
        "name": "Late Session (20:00-22:00 GMT) / Rollover (22:00-23:15)",
        "detection": "session = 'NY_Late' or 'Rollover'.",
        "delta_wr": -0.10,
        "delta_rrr": -0.5,
        "size_mult": 0.0,
        "risk_mult": 0.0,
        "tradable": False,
        "notes": "No new entries. Manage trailing stops on open positions only. Rollover = spreads spike.",
    },
    "M07": {
        "name": "Pre-News Lock",
        "detection": "High-impact economic event within 30-60 minutes (NFP, FOMC, CPI, rate decisions).",
        "delta_wr": -0.20,
        "delta_rrr": -1.0,
        "size_mult": 0.0,
        "risk_mult": 0.0,
        "tradable": False,
        "notes": (
            "Pre-FOMC drift: +0.5% avg in 24h before [A Lucca&Moench2015]. "
            "But spread widens 5-15x, making entry cost exceed edge. Cancel pending "
            "orders. Do NOT add new positions."
        ),
    },
    "M08": {
        "name": "Post-News Active",
        "detection": "High-impact event passed within last 15-60 minutes. Spread normalizing.",
        "delta_wr": 0.02,
        "delta_rrr": 0.1,
        "size_mult": 0.5,
        "risk_mult": 0.5,
        "tradable": True,
        "notes": "Wait 15 min for spread to normalize. Post-news continuation when data beats >1SD: 60-65% [P].",
    },
    "M09": {
        "name": "Sweep Conditions",
        "detection": "sweep_high=True OR sweep_low=True from _sweep_flags() in service.py.",
        "delta_wr": 0.07,
        "delta_rrr": 0.6,
        "size_mult": 1.0,
        "risk_mult": 1.0,
        "tradable": True,
        "notes": (
            "Sweep without MSS: 45-52% WR (coin flip). [P][I] Sweep WITH MSS confirmation: "
            "62-70% WR. The +7% WR comes from the presence of the sweep setup, not the "
            "sweep alone. CRITICAL: _sweep_flags() must check body reclaim. wick > 45% "
            "of candle + close back inside = valid sweep. Body close outside = breakout, "
            "not sweep -> wrong regime."
        ),
    },
    "M10": {
        "name": "Spread Stress",
        "detection": "spread_pctile >= 90th percentile of historical spread.",
        "delta_wr": -0.20,
        "delta_rrr": -1.0,
        "size_mult": 0.0,
        "risk_mult": 0.0,
        "tradable": False,
        "notes": "Direct math: EV = (WR * pip_gain) - spread_cost. When spread > edge, EV < 0. [A]",
    },
    "M11": {
        "name": "Trend Exhaustion",
        "detection": "price > EMA50 + 2.5*ATR AND RSI divergence AND ADX >= 22 AND wick rejection.",
        "delta_wr": -0.04,
        "delta_rrr": -0.4,
        "size_mult": 0.5,
        "risk_mult": 0.5,
        "tradable": True,
        "notes": (
            "Trend is intact (ADX>=22) but price has extended too far. Breakout in exhaustion "
            "zone: only 38-45% success [P]. Still trade in trend direction (not reversal) "
            "but smaller size."
        ),
    },
    "M12": {
        "name": "Multi-Timeframe Alignment",
        "detection": "base_regime(M15) == base_regime(H4). Both timeframes agree on Q1/Q2/Q3/Q4.",
        "delta_wr": 0.08,
        "delta_rrr": 0.5,
        "size_mult": 1.0,
        "risk_mult": 1.0,
        "tradable": True,
        "notes": (
            "AQR: multi-signal momentum > single signal [Q]. +8-12% WR improvement from TF "
            "alignment documented [P]. Requires actual H4 data to be loaded and classified. "
            "Currently: detect_multi_tf_regime() in backend.py feeds context flag."
        ),
    },
    "M13": {
        "name": "Macro Correlation Shock",
        "detection": "DXY and EUR/USD moving same direction (correlation > threshold) OR rate differential anomaly.",
        "delta_wr": 0.08,
        "delta_rrr": 0.5,
        "size_mult": 0.75,
        "risk_mult": 0.75,
        "tradable": True,
        "notes": (
            "Carry + momentum combined: Higher Sharpe than either alone [A Serban2010]. "
            "DXY correlation EUR/USD: -0.7 to -0.9 historically [P][A]. Macro shock: "
            "divergence from normal correlation = setup opportunity. Intermarket divergence "
            "resolution: 2-10 days [P]. 0.75x size because macro is slower - not intraday precision."
        ),
    },
}


@lru_cache(maxsize=1)
def _regime_config() -> dict[str, Any]:
    return ConfigManager(PROJECT_ROOT).load_yaml("config/regimes.yaml")


@lru_cache(maxsize=1)
def _research_config() -> dict[str, Any]:
    return ConfigManager(PROJECT_ROOT).load_yaml("config/regime_research.yaml")


def regime_ids() -> list[str]:
    config = _regime_config()
    return [f"{base}_{modifier}" for base in config.get("base_regimes", {}) for modifier in config.get("modifiers", {})]


def _source_details(keys: list[str]) -> list[dict[str, Any]]:
    clean = sorted({str(key) for key in keys if key})
    sources = _research_config().get("sources", {})
    return [{**{"key": key}, **dict(sources.get(key, {}))} for key in clean]


def _mid(value: list[float] | tuple[float, float] | None) -> float:
    if not value:
        return 0.0
    if len(value) == 1:
        return float(value[0])
    return (float(value[0]) + float(value[1])) / 2.0


def _clamp_rate(value: float) -> float:
    return max(0.0, min(0.85, value))


def _expected_value(win_rate: float, rrr: float) -> float:
    if win_rate <= 0.0 or rrr <= 0.0:
        return 0.0
    return round((win_rate * rrr) - ((1.0 - win_rate) * 1.0), 3)


@lru_cache(maxsize=64)
def _regime_model(regime_id: str) -> dict[str, Any]:
    cfg = _research_config()
    rid = regime_id.upper()
    base, _, modifier = rid.partition("_")
    base_model = dict(cfg.get("base_models", {}).get(base, {}))
    modifier_model = dict(cfg.get("modifier_adjustments", {}).get(modifier, {}))
    override = dict(cfg.get("regime_overrides", {}).get(rid, {}))
    base_range = base_model.get("expected_win_rate", [0.0, 0.0])
    shifted = [
        _clamp_rate(float(base_range[0]) + float(modifier_model.get("win_rate_shift", 0.0))),
        _clamp_rate(float(base_range[1]) + float(modifier_model.get("win_rate_shift", 0.0))),
    ]
    win_range = override.get("expected_win_rate", shifted)
    rrr = float(override.get("expected_rrr", float(base_model.get("expected_rrr", 0.0)) + float(modifier_model.get("rrr_shift", 0.0))))
    risk_multiplier = float(base_model.get("risk_multiplier", 0.0)) * float(modifier_model.get("risk_multiplier", 1.0))
    if base == "Q4":
        risk_multiplier = 0.0
    win_mid = _mid(win_range)
    return {
        "regime_id": rid,
        "base": base,
        "modifier": modifier,
        "priority": override.get("priority", "normal" if base != "Q4" else "defensive"),
        "focus": override.get("focus") or modifier_model.get("trap_focus") or base_model.get("thesis"),
        "expected_win_rate": [round(float(win_range[0]) * 100, 2), round(float(win_range[1]) * 100, 2)] if win_range else [0.0, 0.0],
        "expected_win_rate_mid": round(win_mid * 100, 2),
        "expected_rrr": round(max(0.0, rrr), 2),
        "expected_ev_r": _expected_value(win_mid, max(0.0, rrr)),
        "risk_multiplier": round(max(0.0, risk_multiplier), 3),
        "evidence": sorted(set(base_model.get("evidence", []) + override.get("evidence", []))),
        "sources": base_model.get("sources", []) + override.get("sources", []),
        "thesis": base_model.get("thesis"),
        "trap_focus": modifier_model.get("trap_focus"),
    }


def _family_spec(family: str) -> dict[str, Any]:
    cfg = _research_config()
    if family == "liquidity":
        family = "sweep_reversal"
    if family in {"news", "macro_correlation"}:
        family = "general"
    specs = cfg.get("strategy_family_specs", {})
    return dict(specs.get(family, specs.get("general", {})))


@lru_cache(maxsize=1)
def _registry_by_regime() -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    slot_order = {"primary": 0, "secondary": 1, "confirmation": 2, "fallback": 3}
    for item in strategy_backend.get_registry():
        grouped.setdefault(str(item.get("regime_id", "")).upper(), []).append(item)
    return {key: sorted(value, key=lambda row: slot_order.get(str(row.get("slot")), 99)) for key, value in grouped.items()}


def _modifier_adjustment(modifier: str) -> dict[str, Any]:
    research_adjustment = dict(_research_config().get("modifier_adjustments", {}).get(modifier, {}))
    modifier_definition = MODIFIER_DEFINITIONS.get(modifier, {})
    research_adjustment.setdefault("win_rate_shift", modifier_definition.get("delta_wr", 0.0))
    research_adjustment.setdefault("rrr_shift", modifier_definition.get("delta_rrr", 0.0))
    research_adjustment.setdefault("risk_multiplier", modifier_definition.get("risk_mult", 1.0))
    return research_adjustment


def _template_spec(signal_fn: str) -> dict[str, Any]:
    specs: dict[str, dict[str, Any]] = {
        "S01_ema_pullback": {
            "entry_logic": "Trade a pullback to the fast EMA in the confirmed trend direction, then require a close back in that direction.",
            "entry_trigger": "trend_filter_true AND ema_pullback_touched AND close_reclaims_ema",
            "stop_rule": "swing_extreme +/- ATR buffer from current volatility",
            "tp_rule": "entry +/- expected_rrr * entry_risk",
            "min_rr": 2.0,
            "filters": ["base_regime in Q1/Q2", "trend evidence from config thresholds", "spread below cost guard"],
            "invalidations": ["Q4 defensive regime", "spread stress", "trend exhaustion breakout chase", "news lock"],
        },
        "S02_donchian": {
            "entry_logic": "Trade a channel breakout or continuation only when regime context supports directional expansion.",
            "entry_trigger": "close_breaks_prior_channel AND trend_filter_true",
            "stop_rule": "opposite recent swing +/- ATR buffer",
            "tp_rule": "entry +/- expected_rrr * entry_risk",
            "min_rr": 2.5,
            "filters": ["trend or compression context", "not first unconfirmed breakout", "spread below cost guard"],
            "invalidations": ["failed retest", "range regime fade context", "spread stress"],
        },
        "S03_bb_fade": {
            "entry_logic": "Fade range extremes only when trend evidence is weak and range/mean-reversion context is active.",
            "entry_trigger": "price_at_outer_band_or_range_extreme AND range_filter_true",
            "stop_rule": "beyond band/range extreme +/- ATR buffer",
            "tp_rule": "range_midpoint, VWAP, or opposite boundary depending on strategy note",
            "min_rr": 1.5,
            "filters": ["base_regime == Q3", "ADX/ER range thresholds from config", "spread below range cost guard"],
            "invalidations": ["trend threshold active", "body breakout beyond range", "news lock"],
        },
        "S04_asian_sweep": {
            "entry_logic": "Use Asian range high/low as the reference, then trade a London kill-zone sweep/reclaim only after the candle closes back inside.",
            "entry_trigger": "asian_extreme_swept AND close_reclaims_range AND kill_zone_active",
            "stop_rule": "beyond swept wick +/- ATR buffer",
            "tp_rule": "opposite Asian range boundary or expected_rrr target",
            "min_rr": 2.5,
            "filters": ["Asian range available", "kill zone active", "sweep has reclaim", "spread normal"],
            "invalidations": ["body closes beyond Asian extreme", "no reclaim", "spread stress", "news lock"],
        },
        "S05_sweep_reclaim": {
            "entry_logic": "Trade liquidity sweep plus reclaim at prior/session/range extremes; the wick must reject the swept level.",
            "entry_trigger": "prior_extreme_swept AND wick_rejection AND close_reclaims_level",
            "stop_rule": "beyond swept extreme +/- ATR buffer",
            "tp_rule": "opposite liquidity pool or expected_rrr target",
            "min_rr": 2.5,
            "filters": ["sweep flag true", "reclaim confirmed", "prefer kill zone", "spread normal"],
            "invalidations": ["sweep without reclaim", "body breakout", "spread stress"],
        },
        "S06_failed_bo_fade": {
            "entry_logic": "Fade the failed first breakout after price closes back inside the range.",
            "entry_trigger": "prior_bar_breaks_range AND current_close_returns_inside",
            "stop_rule": "beyond failed breakout extreme +/- ATR buffer",
            "tp_rule": "range midpoint or opposite boundary",
            "min_rr": 2.0,
            "filters": ["range context", "failed breakout confirmed", "spread normal"],
            "invalidations": ["second close outside range", "trend threshold active"],
        },
        "S07_carry_drift": {
            "entry_logic": "Use carry/momentum drift as a low-size fallback only when directional bias is confirmed and spread is controlled.",
            "entry_trigger": "directional_bias_true AND spread_normal AND carry_or_momentum_proxy_available",
            "stop_rule": "ATR-based protective stop",
            "tp_rule": "expected_rrr target from research model",
            "min_rr": 1.5,
            "filters": ["Q1 trend context", "spread normal", "sufficient history or carry proxy"],
            "invalidations": ["spread stress", "missing directional bias", "external carry data unavailable for strict mode"],
        },
        "S08_no_trade": {
            "entry_logic": "No new entry. Protect capital, observe, trail existing exposure, or wait for regime confirmation.",
            "entry_trigger": "defensive_or_cost_block_condition",
            "stop_rule": "N/A",
            "tp_rule": "N/A",
            "min_rr": 0.0,
            "filters": [],
            "invalidations": [],
        },
    }
    return dict(specs.get(signal_fn, specs["S08_no_trade"]))


def _slot_defaults(slot: str) -> dict[str, float]:
    if slot == "primary":
        return {"size_mult": 1.0}
    if slot == "secondary":
        return {"size_mult": 0.75}
    if slot == "confirmation":
        return {"size_mult": 0.5}
    return {"size_mult": 0.0}


def _strategy_size(strategy: dict[str, Any], regime_model: dict[str, Any]) -> float:
    if strategy.get("size_override") is not None:
        return float(strategy.get("size_override") or 0.0)
    if str(strategy.get("signal_fn")) == "S08_no_trade" or str(strategy.get("family")) == "defensive":
        return 0.0
    return round(float(regime_model.get("risk_multiplier") or 0.0) * _slot_defaults(str(strategy.get("slot")))["size_mult"], 3)


def _strategy_definition(strategy: dict[str, Any], regime_id: str, regime_model: dict[str, Any]) -> StrategyDef:
    signal_fn = str(strategy.get("signal_fn") or "S08_no_trade")
    template = _template_spec(signal_fn)
    spec = _family_spec(str(strategy.get("family", "general")))
    wr_low = float(strategy.get("win_rate_low") or 0.0)
    wr_high = float(strategy.get("win_rate_high") or 0.0)
    expected_rrr = float(strategy.get("rrr") or spec.get("expected_rrr") or regime_model.get("expected_rrr") or 0.0)
    expected_ev = float(strategy.get("ev") or spec.get("expected_ev_r") or 0.0)
    source_keys = list(regime_model.get("sources") or []) + list(spec.get("sources") or [])
    evidence = []
    for item in [strategy.get("evidence"), *(regime_model.get("evidence") or []), *(spec.get("evidence") or [])]:
        if item:
            evidence.append(str(item))
    notes = str(strategy.get("notes") or strategy.get("description") or strategy.get("regime_logic") or "")
    family_logic = str(spec.get("entry_logic") or "")
    return {
        "id": str(strategy.get("id")),
        "strategy_id": str(strategy.get("id")),
        "regime_id": regime_id,
        "name": str(strategy.get("name")),
        "slot": str(strategy.get("slot")),
        "family": str(strategy.get("family")),
        "signal_fn": signal_fn,
        "signal_template": SIGNAL_CODE_TO_TEMPLATE.get(signal_fn, "no_trade"),
        "entry_logic": f"{template['entry_logic']} {family_logic}".strip(),
        "entry_trigger": str(template["entry_trigger"]),
        "stop_rule": str(template["stop_rule"]),
        "tp_rule": str(template["tp_rule"]),
        "min_rr": float(template["min_rr"]),
        "expected_wr_low": wr_low,
        "expected_wr_high": wr_high,
        "expected_rrr": expected_rrr,
        "expected_ev_r": expected_ev,
        "size_mult": _strategy_size(strategy, regime_model),
        "filters": list(template["filters"]),
        "invalidations": list(template["invalidations"]) + ([str(spec.get("invalid_when"))] if spec.get("invalid_when") else []),
        "evidence": sorted(set(evidence)),
        "sources": _source_details(source_keys),
        "notes": notes,
        "status": str(strategy.get("status") or "not_tested"),
        "research_active": bool(strategy.get("research_active")),
        "live_allowed": bool(strategy.get("live_allowed")),
    }


def strategies_for_regime(regime_id: str) -> list[StrategyDef]:
    regime_id = regime_id.upper()
    regime_model = _regime_model(regime_id)
    strategies = _registry_by_regime().get(regime_id, [])
    return [_strategy_definition(strategy, regime_id, regime_model) for strategy in strategies]


def _detection_summary(base: str, modifier: str, base_detail: dict[str, Any], modifier_detail: dict[str, Any]) -> str:
    thresholds = _regime_config().get("thresholds", {})
    modifier_definition = MODIFIER_DEFINITIONS.get(modifier, {})
    if base == "Q1":
        base_rule = "Trend condition from config: ADX >= thresholds.adx_trend_min and ER >= thresholds.efficiency_ratio_min with volatility below high-vol threshold."
    elif base == "Q2":
        base_rule = "Trend plus high-volatility condition from config: Q1 trend evidence with high_vol_percentile or high_vol_atr_percent active."
    elif base == "Q3":
        base_rule = "Range condition from config: ADX <= thresholds.adx_range_max and ER <= thresholds.efficiency_ratio_range_max."
    else:
        base_rule = "Defensive condition from config: transition, shock, spread stress, pre-news, macro/correlation block, or ambiguous regime."
    modifier_rule = (
        f"Modifier {modifier}: {modifier_definition.get('name') or modifier_detail.get('name', modifier)}; "
        f"posture {modifier_detail.get('risk_posture', 'n/a')}; "
        f"detection {modifier_definition.get('detection', 'See config/regimes.yaml')}."
    )
    threshold_keys = ", ".join(sorted(thresholds.keys()))
    return f"{base_detail.get('name', base)}. {base_rule} {modifier_rule} Threshold source keys: {threshold_keys}."


def _slot_map(strategies: list[StrategyDef]) -> dict[str, StrategyDef]:
    by_slot = {item["slot"]: item for item in strategies}
    empty = StrategyDef(
        id="",
        strategy_id="",
        regime_id="",
        name="Missing strategy slot",
        slot="",
        family="defensive",
        signal_fn="S08_no_trade",
        signal_template="s08_no_trade",
        entry_logic="Missing registry entry; no trade.",
        entry_trigger="missing_registry_entry",
        stop_rule="N/A",
        tp_rule="N/A",
        min_rr=0.0,
        expected_wr_low=0.0,
        expected_wr_high=0.0,
        expected_rrr=0.0,
        expected_ev_r=0.0,
        size_mult=0.0,
        filters=[],
        invalidations=[],
        evidence=["U"],
        sources=[],
        notes="Registry should provide exactly four strategy slots per regime.",
        status="missing",
        research_active=False,
        live_allowed=False,
    )
    return {
        "primary": by_slot.get("primary", empty),
        "secondary": by_slot.get("secondary", empty),
        "confirmation": by_slot.get("confirmation", empty),
        "fallback": by_slot.get("fallback", empty),
    }


def _regime_definition(regime_id: str) -> RegimeDef:
    config = _regime_config()
    base_regimes = config.get("base_regimes", {})
    modifiers = config.get("modifiers", {})
    base, _, modifier = regime_id.partition("_")
    base_detail = dict(base_regimes.get(base, {}))
    modifier_detail = dict(modifiers.get(modifier, {}))
    modifier_definition = dict(MODIFIER_DEFINITIONS.get(modifier, {}))
    research_model = _regime_model(regime_id)
    modifier_adjustment = _modifier_adjustment(modifier)
    strategies = strategies_for_regime(regime_id)
    slots = _slot_map(strategies)
    risk_multiplier = float(research_model.get("risk_multiplier") or 0.0)
    return {
        "regime_id": regime_id,
        "description": f"{base_detail.get('name', base)} - {modifier_detail.get('name', modifier)}",
        "base_regime": base,
        "modifier": modifier,
        "detection_summary": _detection_summary(base, modifier, base_detail, modifier_detail),
        "tradable": bool(base_detail.get("tradable")) and bool(modifier_detail.get("tradable")) and risk_multiplier > 0.0,
        "risk_posture": str(modifier_detail.get("risk_posture") or base_detail.get("risk_posture") or research_model.get("risk_multiplier")),
        "priority": str(research_model.get("priority") or "normal"),
        "focus": str(research_model.get("focus") or research_model.get("thesis") or ""),
        "base_wr_adjustment": float(modifier_adjustment.get("win_rate_shift") or 0.0),
        "base_rrr_adjustment": float(modifier_adjustment.get("rrr_shift") or 0.0),
        "size_multiplier": risk_multiplier,
        "risk_multiplier": risk_multiplier,
        "thresholds_source": "config/regimes.yaml",
        "modifier_definition": modifier_definition,
        "primary": slots["primary"],
        "secondary": slots["secondary"],
        "confirmation": slots["confirmation"],
        "fallback": slots["fallback"],
        "strategies": strategies,
        "research_model": research_model,
    }


@lru_cache(maxsize=1)
def full_regime_strategy_map() -> dict[str, Any]:
    regimes = [_regime_definition(regime_id) for regime_id in regime_ids()]
    ranking = sorted(
        [
            {
                "regime_id": regime["regime_id"],
                "primary_signal_fn": regime["primary"]["signal_fn"],
                "expected_wr": [regime["primary"]["expected_wr_low"], regime["primary"]["expected_wr_high"]],
                "expected_rrr": regime["primary"]["expected_rrr"],
                "expected_ev_r": regime["primary"]["expected_ev_r"],
                "evidence": regime["primary"]["evidence"],
            }
            for regime in regimes
            if regime["primary"]["expected_ev_r"] > 0
        ],
        key=lambda item: float(item["expected_ev_r"]),
        reverse=True,
    )
    return {
        "thresholds_source": "config/regimes.yaml",
        "thresholds": _regime_config().get("thresholds", {}),
        "regime_count": len(regimes),
        "strategy_count": sum(len(item["strategies"]) for item in regimes),
        "regimes": regimes,
        "expected_ev_ranking": ranking,
        "modifier_definitions": MODIFIER_DEFINITIONS,
        "registry_summary": strategy_backend.get_registry_summary(),
        "note": "Expected values are research priors only. Actual performance must come from MT5/CSV backtests and cockpit DB results.",
    }
