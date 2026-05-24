from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean, pstdev
from typing import Any

from core.models.regime import RegimeResult
from core.models.signal import Signal
from systems.strategy.signal_library_section5 import SignalResult, run_section5_signal
from systems.strategy.signal_routing import position_size_multiplier_for_regime, routing_settings, signal_code_for_regime

SIGNAL_CODE_TO_TEMPLATE: dict[str, str] = {
    "S01_ema_pullback": "ema_pullback",
    "S02_donchian": "donchian_breakout",
    "S03_bb_fade": "bollinger_fade",
    "S04_asian_sweep": "asian_range_sweep",
    "S05_sweep_reclaim": "sweep_reclaim",
    "S06_failed_bo_fade": "failed_breakout_fade",
    "S07_carry_drift": "carry_drift",
    "S08_no_trade": "s08_no_trade",
}


def compute_signal(rows: list[dict[str, Any]], regime_id: str) -> SignalResult:
    """
    Phase B / public API: dispatch Section 5 by regime_id string.
    Builds a minimal RegimeResult with features from calculate_feature_snapshot(rows)
    so ADX (Bollinger gate) and spreads match the data.
    """
    from systems.regime.service import calculate_feature_snapshot

    rid = str(regime_id).upper()
    if len(rid) >= 5 and rid[2] == "_":
        base, _, modifier = rid.partition("_")
    else:
        base, modifier = "Q4", "M01"
    features = calculate_feature_snapshot(rows)
    regime = RegimeResult(
        base_regime=base,
        modifier=modifier,
        regime_id=rid,
        confidence=0.5,
        tradable=True,
        risk_posture="normal",
        features=features,
    )
    return run_section5_signal(rows, regime)


@dataclass
class SignalEvaluation:
    strategy_id: str
    template: str
    passed: bool
    reason: str
    signal: Signal | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.signal:
            payload["signal"] = asdict(self.signal)
        return payload


def _values(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [float(row[key]) for row in rows]


def _ema(values: list[float], period: int) -> float:
    """
    SMA-seeded EMA. Seeds from mean of first period bars, NOT values[0].
    Starting from values[0] distorts first 50-100 bars.
    """
    if not values:
        return 0.0
    if len(values) < period:
        return sum(values) / len(values)
    seed = sum(values[:period]) / period
    multiplier = 2.0 / (period + 1)
    ema = seed
    for value in values[period:]:
        ema = (value - ema) * multiplier + ema
    return ema


def _atr(rows: list[dict[str, Any]], period: int = 14) -> float:
    if len(rows) < 2:
        return 0.0
    ranges: list[float] = []
    start = max(1, len(rows) - period)
    for index in range(start, len(rows)):
        high = float(rows[index]["high"])
        low = float(rows[index]["low"])
        prev_close = float(rows[index - 1]["close"])
        ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return mean(ranges) if ranges else 0.0


def _rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    for index in range(len(values) - period, len(values)):
        change = values[index] - values[index - 1]
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))
    avg_gain = mean(gains) if gains else 0.0
    avg_loss = mean(losses) if losses else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _bollinger(values: list[float], period: int = 20, width: float = 2.0) -> tuple[float, float, float]:
    if len(values) < period:
        basis = mean(values) if values else 0.0
        return basis, basis, basis
    window = values[-period:]
    basis = mean(window)
    sigma = pstdev(window) if len(window) > 1 else 0.0
    return basis - width * sigma, basis, basis + width * sigma


def _candle_ratios(row: dict[str, Any]) -> tuple[float, float, float]:
    high = float(row["high"])
    low = float(row["low"])
    open_ = float(row["open"])
    close = float(row["close"])
    size = max(high - low, 1e-12)
    body = abs(close - open_)
    upper = high - max(open_, close)
    lower = min(open_, close) - low
    return body / size, upper / size, lower / size


def _risk_box(rows: list[dict[str, Any]], direction: str, target_r: float = 2.0, atr_stop_mult: float = 1.0) -> tuple[float, float, float]:
    row = rows[-1]
    entry = float(row["close"])
    atr = max(_atr(rows), abs(float(row["high"]) - float(row["low"])), 1e-8)
    dist = atr * max(atr_stop_mult, 0.01)
    if direction == "long":
        stop = entry - dist
        target = entry + atr * target_r
    else:
        stop = entry + dist
        target = entry - atr * target_r
    return entry, stop, target


def _direction_from_trend(rows: list[dict[str, Any]]) -> str | None:
    closes = _values(rows, "close")
    if len(closes) < 35:
        return None
    close = closes[-1]
    ema20 = _ema(closes[-35:], 20)
    ema50 = _ema(closes[-80:], 50)
    if close > ema20 > ema50:
        return "long"
    if close < ema20 < ema50:
        return "short"
    if close > ema50 and close > closes[-2]:
        return "long"
    if close < ema50 and close < closes[-2]:
        return "short"
    return None


def _make_signal(
    strategy: dict[str, Any],
    symbol: str,
    direction: str,
    rows: list[dict[str, Any]],
    reason: str,
    metadata: dict[str, Any],
    target_r: float = 2.0,
    *,
    atr_stop_mult: float = 1.0,
    regime: RegimeResult | None = None,
) -> Signal:
    entry, stop, target = _risk_box(rows, direction, target_r=target_r, atr_stop_mult=atr_stop_mult)
    confidence = float(metadata.get("confidence") or 0.55)
    meta = dict(metadata)
    if regime is not None:
        meta.setdefault("regime_id", regime.regime_id)
        meta["regime_size_multiplier"] = position_size_multiplier_for_regime(regime.regime_id)
        meta["routed_signal"] = signal_code_for_regime(regime.regime_id)
    return Signal(
        strategy_id=str(strategy["id"]),
        symbol=symbol,
        direction=direction,
        entry=round(entry, 6),
        stop=round(stop, 6),
        target=round(target, 6),
        confidence=round(max(0.1, min(0.95, confidence)), 4),
        reason=reason,
        metadata=meta,
    )


def template_for_strategy(strategy: dict[str, Any]) -> str:
    name = str(strategy.get("name", "")).lower()
    family = str(strategy.get("family", "general")).lower()
    if family == "defensive" or "no trade" in name or "no-trade" in name or "wait" in name or "protect" in name:
        return "defensive_guard"
    if "asian" in name and "sweep" in name:
        return "asian_range_sweep"
    if family in {"liquidity", "sweep_reversal"} or "sweep" in name or "spring" in name or "utad" in name:
        return "sweep_reclaim"
    if "bollinger" in name:
        return "bollinger_fade"
    if "rsi" in name or "range" in name or "fade" in name or "vwap" in name:
        return "range_fade"
    if "donchian" in name or "channel" in name:
        return "donchian_breakout"
    if "break" in name or "retest" in name or "opening range" in name or "atr" in name:
        return "break_retest"
    if "ema" in name or "pullback" in name:
        return "ema_pullback"
    if family == "trend_momentum" or "momentum" in name or "continuation" in name or "carry" in name:
        return "momentum_continuation"
    if family in {"news", "macro_correlation"}:
        return "external_context_guard"
    return "momentum_continuation"


def _evaluate_s08_no_trade(strategy: dict[str, Any], symbol: str, rows: list[dict[str, Any]], regime: RegimeResult, timeframe: str) -> SignalEvaluation:
    code = signal_code_for_regime(regime.regime_id)
    return SignalEvaluation(
        str(strategy["id"]),
        "s08_no_trade",
        False,
        "S08_no_trade: primary route blocks new exposure",
        None,
        {"regime_id": regime.regime_id, "timeframe": timeframe, "symbol": symbol, "routed_signal": code},
    )


def _evaluate_carry_drift(strategy: dict[str, Any], symbol: str, rows: list[dict[str, Any]], regime: RegimeResult, timeframe: str) -> SignalEvaluation:
    if regime.base_regime != "Q1":
        return SignalEvaluation(str(strategy["id"]), "carry_drift", False, "carry drift applies in Q1 trend regimes only", None, {"regime_id": regime.regime_id})
    if regime.features.spread_percentile > 85:
        return SignalEvaluation(str(strategy["id"]), "carry_drift", False, "spread too wide for thin-session carry drift", None, {"spread_percentile": regime.features.spread_percentile})
    direction = _direction_from_trend(rows)
    if not direction:
        return SignalEvaluation(str(strategy["id"]), "carry_drift", False, "no directional drift (trend alignment missing)", None, {"regime_id": regime.regime_id})
    session = (regime.features.session_label or "").lower()
    if "asia" not in session and "tokyo" not in session:
        return SignalEvaluation(str(strategy["id"]), "carry_drift", False, "carry drift gated to Asia / thin liquidity session", None, {"session_label": regime.features.session_label})
    return SignalEvaluation(
        str(strategy["id"]),
        "carry_drift",
        True,
        "Q1 Asia-session carry-aligned drift (swap data optional; trend proxy only)",
        _make_signal(
            strategy,
            symbol,
            direction,
            rows,
            "Carry drift",
            {"regime_id": regime.regime_id, "timeframe": timeframe, "confidence": min(0.55, regime.confidence or 0.5)},
            2.0,
            regime=regime,
        ),
        {"session_label": regime.features.session_label},
    )


def _evaluate_failed_breakout_fade(strategy: dict[str, Any], symbol: str, rows: list[dict[str, Any]], regime: RegimeResult, timeframe: str) -> SignalEvaluation:
    if len(rows) < 25 or regime.base_regime != "Q3":
        return SignalEvaluation(str(strategy["id"]), "failed_breakout_fade", False, "range regime or history missing", None, {"regime_id": regime.regime_id})
    prior = rows[-21:-1]
    prior_high = max(float(row["high"]) for row in prior)
    prior_low = min(float(row["low"]) for row in prior)
    row = rows[-1]
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])
    if high > prior_high and close < prior_high:
        return SignalEvaluation(
            str(strategy["id"]),
            "failed_breakout_fade",
            True,
            "failed breakout above range — fade short",
            _make_signal(
                strategy,
                symbol,
                "short",
                rows,
                "Failed breakout fade",
                {"regime_id": regime.regime_id, "timeframe": timeframe, "prior_high": prior_high, "confidence": regime.confidence},
                2.0,
                regime=regime,
            ),
            {"prior_high": prior_high},
        )
    if low < prior_low and close > prior_low:
        return SignalEvaluation(
            str(strategy["id"]),
            "failed_breakout_fade",
            True,
            "failed breakdown below range — fade long",
            _make_signal(
                strategy,
                symbol,
                "long",
                rows,
                "Failed breakout fade",
                {"regime_id": regime.regime_id, "timeframe": timeframe, "prior_low": prior_low, "confidence": regime.confidence},
                2.0,
                regime=regime,
            ),
            {"prior_low": prior_low},
        )
    return SignalEvaluation(str(strategy["id"]), "failed_breakout_fade", False, "no failed breakout at range boundary", None, {"prior_high": prior_high, "prior_low": prior_low})


def _evaluate_defensive(strategy: dict[str, Any], symbol: str, rows: list[dict[str, Any]], regime: RegimeResult, timeframe: str) -> SignalEvaluation:
    return SignalEvaluation(str(strategy["id"]), "defensive_guard", False, "defensive strategy: no new entry", None, {"regime_id": regime.regime_id, "timeframe": timeframe, "symbol": symbol})


def _evaluate_external_context(strategy: dict[str, Any], symbol: str, rows: list[dict[str, Any]], regime: RegimeResult, timeframe: str) -> SignalEvaluation:
    return SignalEvaluation(
        str(strategy["id"]),
        "external_context_guard",
        False,
        "external news/macro/sentiment connector unavailable",
        None,
        {"regime_id": regime.regime_id, "timeframe": timeframe, "symbol": symbol, "requires_external_feed": True},
    )


def _evaluate_ema_pullback(strategy: dict[str, Any], symbol: str, rows: list[dict[str, Any]], regime: RegimeResult, timeframe: str) -> SignalEvaluation:
    closes = _values(rows, "close")
    if len(closes) < 55 or regime.base_regime not in {"Q1", "Q2"}:
        return SignalEvaluation(str(strategy["id"]), "ema_pullback", False, "trend regime or history missing", None, {"regime_id": regime.regime_id})
    close = closes[-1]
    ema20 = _ema(closes[-35:], 20)
    atr = _atr(rows)
    direction = _direction_from_trend(rows)
    pulled_back = atr > 0 and abs(close - ema20) <= atr * 3.0
    resumed = close > closes[-2] if direction == "long" else close < closes[-2] if direction == "short" else False
    if direction and pulled_back and resumed:
        settings = routing_settings()
        atr_m = float(settings.get("q2_stop_atr_mult", 1.5)) if regime.base_regime == "Q2" else 1.0
        return SignalEvaluation(
            str(strategy["id"]),
            "ema_pullback",
            True,
            "EMA pullback resumed in trend direction",
            _make_signal(
                strategy,
                symbol,
                direction,
                rows,
                "EMA pullback",
                {"regime_id": regime.regime_id, "timeframe": timeframe, "confidence": regime.confidence},
                2.5,
                atr_stop_mult=atr_m,
                regime=regime,
            ),
            {"ema20": ema20, "atr": atr},
        )
    return SignalEvaluation(str(strategy["id"]), "ema_pullback", False, "no EMA pullback confirmation", None, {"ema20": ema20, "atr": atr, "direction": direction})


def _evaluate_donchian(strategy: dict[str, Any], symbol: str, rows: list[dict[str, Any]], regime: RegimeResult, timeframe: str) -> SignalEvaluation:
    if len(rows) < 25 or regime.base_regime not in {"Q1", "Q2"}:
        return SignalEvaluation(str(strategy["id"]), "donchian_breakout", False, "trend regime or history missing", None, {"regime_id": regime.regime_id})
    prior = rows[-21:-1]
    close = float(rows[-1]["close"])
    prior_high = max(float(row["high"]) for row in prior)
    prior_low = min(float(row["low"]) for row in prior)
    if close > prior_high:
        return SignalEvaluation(
            str(strategy["id"]),
            "donchian_breakout",
            True,
            "20-bar Donchian upside break",
            _make_signal(
                strategy,
                symbol,
                "long",
                rows,
                "Donchian continuation",
                {"regime_id": regime.regime_id, "timeframe": timeframe, "channel_high": prior_high, "confidence": regime.confidence},
                3.0,
                regime=regime,
            ),
        )
    if close < prior_low:
        return SignalEvaluation(
            str(strategy["id"]),
            "donchian_breakout",
            True,
            "20-bar Donchian downside break",
            _make_signal(
                strategy,
                symbol,
                "short",
                rows,
                "Donchian continuation",
                {"regime_id": regime.regime_id, "timeframe": timeframe, "channel_low": prior_low, "confidence": regime.confidence},
                3.0,
                regime=regime,
            ),
        )
    return SignalEvaluation(str(strategy["id"]), "donchian_breakout", False, "no channel break", None, {"channel_high": prior_high, "channel_low": prior_low})


def _evaluate_bollinger(strategy: dict[str, Any], symbol: str, rows: list[dict[str, Any]], regime: RegimeResult, timeframe: str) -> SignalEvaluation:
    closes = _values(rows, "close")
    if len(closes) < 25 or regime.base_regime != "Q3":
        return SignalEvaluation(str(strategy["id"]), "bollinger_fade", False, "range regime or history missing", None, {"regime_id": regime.regime_id})
    max_adx = float(routing_settings().get("bollinger_max_adx", 20))
    if regime.features.adx > max_adx:
        return SignalEvaluation(
            str(strategy["id"]),
            "bollinger_fade",
            False,
            f"ADX {regime.features.adx:.1f} above {max_adx} (range fade requirement)",
            None,
            {"adx": regime.features.adx},
        )
    lower, basis, upper = _bollinger(closes)
    close = closes[-1]
    rsi = _rsi(closes)
    if close <= lower and rsi <= 40:
        return SignalEvaluation(
            str(strategy["id"]),
            "bollinger_fade",
            True,
            "lower Bollinger range fade",
            _make_signal(
                strategy,
                symbol,
                "long",
                rows,
                "Bollinger fade",
                {"regime_id": regime.regime_id, "timeframe": timeframe, "rsi": rsi, "confidence": regime.confidence},
                1.8,
                regime=regime,
            ),
        )
    if close >= upper and rsi >= 60:
        return SignalEvaluation(
            str(strategy["id"]),
            "bollinger_fade",
            True,
            "upper Bollinger range fade",
            _make_signal(
                strategy,
                symbol,
                "short",
                rows,
                "Bollinger fade",
                {"regime_id": regime.regime_id, "timeframe": timeframe, "rsi": rsi, "confidence": regime.confidence},
                1.8,
                regime=regime,
            ),
        )
    return SignalEvaluation(str(strategy["id"]), "bollinger_fade", False, "no Bollinger fade setup", None, {"lower": lower, "basis": basis, "upper": upper, "rsi": rsi})


def _evaluate_sweep(strategy: dict[str, Any], symbol: str, rows: list[dict[str, Any]], regime: RegimeResult, timeframe: str, template: str) -> SignalEvaluation:
    if len(rows) < 25:
        return SignalEvaluation(str(strategy["id"]), template, False, "history missing", None, {"regime_id": regime.regime_id})
    row = rows[-1]
    prior = rows[-21:-1]
    prior_high = max(float(item["high"]) for item in prior)
    prior_low = min(float(item["low"]) for item in prior)
    close = float(row["close"])
    _, upper_wick, lower_wick = _candle_ratios(row)
    micro = regime.features.extra or {}
    asian_high_swept = bool(micro.get("asian_high_swept"))
    asian_low_swept = bool(micro.get("asian_low_swept"))
    if (float(row["high"]) > prior_high and close < prior_high and upper_wick >= 0.35) or asian_high_swept:
        return SignalEvaluation(
            str(strategy["id"]),
            template,
            True,
            "swept high and reclaimed lower",
            _make_signal(
                strategy,
                symbol,
                "short",
                rows,
                "Sweep reclaim",
                {"regime_id": regime.regime_id, "timeframe": timeframe, "prior_high": prior_high, "asian_high_swept": asian_high_swept, "confidence": regime.confidence},
                3.0,
                regime=regime,
            ),
        )
    if (float(row["low"]) < prior_low and close > prior_low and lower_wick >= 0.35) or asian_low_swept:
        return SignalEvaluation(
            str(strategy["id"]),
            template,
            True,
            "swept low and reclaimed higher",
            _make_signal(
                strategy,
                symbol,
                "long",
                rows,
                "Sweep reclaim",
                {"regime_id": regime.regime_id, "timeframe": timeframe, "prior_low": prior_low, "asian_low_swept": asian_low_swept, "confidence": regime.confidence},
                3.0,
                regime=regime,
            ),
        )
    return SignalEvaluation(str(strategy["id"]), template, False, "sweep without reclaim", None, {"prior_high": prior_high, "prior_low": prior_low})


def _evaluate_break_retest(strategy: dict[str, Any], symbol: str, rows: list[dict[str, Any]], regime: RegimeResult, timeframe: str) -> SignalEvaluation:
    if len(rows) < 35:
        return SignalEvaluation(str(strategy["id"]), "break_retest", False, "history missing", None, {"regime_id": regime.regime_id})
    close = float(rows[-1]["close"])
    prior = rows[-31:-2]
    level_high = max(float(row["high"]) for row in prior)
    level_low = min(float(row["low"]) for row in prior)
    atr = _atr(rows)
    prev_close = float(rows[-2]["close"])
    if close > level_high and abs(prev_close - level_high) <= atr:
        return SignalEvaluation(
            str(strategy["id"]),
            "break_retest",
            True,
            "break and retest above resistance",
            _make_signal(
                strategy,
                symbol,
                "long",
                rows,
                "Break-retest",
                {"regime_id": regime.regime_id, "timeframe": timeframe, "level": level_high, "confidence": regime.confidence},
                2.5,
                regime=regime,
            ),
        )
    if close < level_low and abs(prev_close - level_low) <= atr:
        return SignalEvaluation(
            str(strategy["id"]),
            "break_retest",
            True,
            "break and retest below support",
            _make_signal(
                strategy,
                symbol,
                "short",
                rows,
                "Break-retest",
                {"regime_id": regime.regime_id, "timeframe": timeframe, "level": level_low, "confidence": regime.confidence},
                2.5,
                regime=regime,
            ),
        )
    return SignalEvaluation(str(strategy["id"]), "break_retest", False, "no break-retest confirmation", None, {"level_high": level_high, "level_low": level_low})


def _evaluate_momentum(strategy: dict[str, Any], symbol: str, rows: list[dict[str, Any]], regime: RegimeResult, timeframe: str) -> SignalEvaluation:
    if len(rows) < 35 or regime.base_regime not in {"Q1", "Q2"}:
        return SignalEvaluation(str(strategy["id"]), "momentum_continuation", False, "trend regime or history missing", None, {"regime_id": regime.regime_id})
    direction = _direction_from_trend(rows)
    closes = _values(rows, "close")
    if direction == "long" and closes[-1] > closes[-5]:
        return SignalEvaluation(
            str(strategy["id"]),
            "momentum_continuation",
            True,
            "positive continuation impulse",
            _make_signal(
                strategy,
                symbol,
                "long",
                rows,
                "Momentum continuation",
                {"regime_id": regime.regime_id, "timeframe": timeframe, "confidence": regime.confidence},
                2.5,
                regime=regime,
            ),
        )
    if direction == "short" and closes[-1] < closes[-5]:
        return SignalEvaluation(
            str(strategy["id"]),
            "momentum_continuation",
            True,
            "negative continuation impulse",
            _make_signal(
                strategy,
                symbol,
                "short",
                rows,
                "Momentum continuation",
                {"regime_id": regime.regime_id, "timeframe": timeframe, "confidence": regime.confidence},
                2.5,
                regime=regime,
            ),
        )
    return SignalEvaluation(str(strategy["id"]), "momentum_continuation", False, "no continuation impulse", None, {"direction": direction})


def _section5_to_evaluation(
    sr: SignalResult,
    strategy: dict[str, Any],
    symbol: str,
    regime: RegimeResult,
    timeframe: str,
) -> SignalEvaluation:
    """Map Section 5 SignalResult → core SignalEvaluation + Signal."""
    tpl = SIGNAL_CODE_TO_TEMPLATE.get(sr.strategy_id, sr.strategy_id.lower())
    meta_base: dict[str, Any] = {
        "routed_signal": signal_code_for_regime(regime.regime_id),
        "section5_library": True,
        "section5_strategy_id": sr.strategy_id,
        "timeframe": timeframe,
        "regime_id": regime.regime_id,
    }
    if sr.direction == "NONE":
        return SignalEvaluation(str(strategy["id"]), tpl, False, sr.reason, None, meta_base | {"rr_ratio": sr.rr_ratio})

    direction = "long" if sr.direction == "BUY" else "short"
    meta = meta_base | {
        "rr_ratio": sr.rr_ratio,
        "regime_size_multiplier": position_size_multiplier_for_regime(regime.regime_id),
    }
    if sr.size_override >= 0:
        meta["section5_size_override"] = sr.size_override

    sig = Signal(
        strategy_id=str(strategy["id"]),
        symbol=symbol,
        direction=direction,
        entry=round(sr.entry_price, 6),
        stop=round(sr.stop_price, 6),
        target=round(sr.tp_price, 6),
        confidence=round(max(0.1, min(0.95, sr.confidence)), 4),
        reason=sr.reason,
        metadata=meta,
    )
    return SignalEvaluation(str(strategy["id"]), tpl, True, sr.reason, sig, meta)


def _evaluate_range_fade(strategy: dict[str, Any], symbol: str, rows: list[dict[str, Any]], regime: RegimeResult, timeframe: str) -> SignalEvaluation:
    closes = _values(rows, "close")
    if len(closes) < 25 or regime.base_regime != "Q3":
        return SignalEvaluation(str(strategy["id"]), "range_fade", False, "range regime or history missing", None, {"regime_id": regime.regime_id})
    rsi = _rsi(closes)
    recent = rows[-21:-1]
    range_high = max(float(row["high"]) for row in recent)
    range_low = min(float(row["low"]) for row in recent)
    close = closes[-1]
    width = max(range_high - range_low, 1e-12)
    if close <= range_low + width * 0.20 and rsi <= 40:
        return SignalEvaluation(
            str(strategy["id"]),
            "range_fade",
            True,
            "range low fade",
            _make_signal(
                strategy,
                symbol,
                "long",
                rows,
                "Range fade",
                {"regime_id": regime.regime_id, "timeframe": timeframe, "rsi": rsi, "confidence": regime.confidence},
                1.8,
                regime=regime,
            ),
        )
    if close >= range_high - width * 0.20 and rsi >= 60:
        return SignalEvaluation(
            str(strategy["id"]),
            "range_fade",
            True,
            "range high fade",
            _make_signal(
                strategy,
                symbol,
                "short",
                rows,
                "Range fade",
                {"regime_id": regime.regime_id, "timeframe": timeframe, "rsi": rsi, "confidence": regime.confidence},
                1.8,
                regime=regime,
            ),
        )
    return SignalEvaluation(str(strategy["id"]), "range_fade", False, "not at range edge", None, {"range_high": range_high, "range_low": range_low, "rsi": rsi})


def evaluate_strategy_signal(
    rows: list[dict[str, Any]],
    strategy: dict[str, Any],
    regime: RegimeResult,
    *,
    symbol: str,
    timeframe: str,
) -> SignalEvaluation:
    if len(rows) < 20:
        return SignalEvaluation(str(strategy["id"]), "data_guard", False, "not enough bars for signal", None, {"bars": len(rows)})
    slot = str(strategy.get("slot", "primary")).lower()
    signal_fn = str(strategy.get("signal_fn") or "").strip()
    registry_template = SIGNAL_CODE_TO_TEMPLATE.get(signal_fn)
    # Legacy strategies without signal_fn: primary uses Section 5 router only.
    if slot == "primary" and registry_template is None:
        sr = run_section5_signal(rows, regime)
        return _section5_to_evaluation(sr, strategy, symbol, regime, timeframe)
    template = registry_template if registry_template is not None else template_for_strategy(strategy)
    if template == "defensive_guard":
        return _evaluate_defensive(strategy, symbol, rows, regime, timeframe)
    if template == "external_context_guard":
        return _evaluate_external_context(strategy, symbol, rows, regime, timeframe)
    if template == "s08_no_trade":
        return _evaluate_s08_no_trade(strategy, symbol, rows, regime, timeframe)
    if template == "carry_drift":
        return _evaluate_carry_drift(strategy, symbol, rows, regime, timeframe)
    if template == "failed_breakout_fade":
        return _evaluate_failed_breakout_fade(strategy, symbol, rows, regime, timeframe)
    if template == "ema_pullback":
        return _evaluate_ema_pullback(strategy, symbol, rows, regime, timeframe)
    if template == "donchian_breakout":
        return _evaluate_donchian(strategy, symbol, rows, regime, timeframe)
    if template == "bollinger_fade":
        return _evaluate_bollinger(strategy, symbol, rows, regime, timeframe)
    if template == "asian_range_sweep":
        return _evaluate_sweep(strategy, symbol, rows, regime, timeframe, template)
    if template == "sweep_reclaim":
        return _evaluate_sweep(strategy, symbol, rows, regime, timeframe, template)
    if template == "break_retest":
        return _evaluate_break_retest(strategy, symbol, rows, regime, timeframe)
    if template == "range_fade":
        return _evaluate_range_fade(strategy, symbol, rows, regime, timeframe)
    return _evaluate_momentum(strategy, symbol, rows, regime, timeframe)
