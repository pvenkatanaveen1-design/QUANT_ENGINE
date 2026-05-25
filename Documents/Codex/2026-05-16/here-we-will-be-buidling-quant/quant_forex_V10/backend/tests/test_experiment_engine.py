from __future__ import annotations

from backend import experiment_engine


def _fake_backtest(payload, persist=False):
    alpha = payload.get("filters", {}).get("min_alpha_score", 5)
    hard_killzone = payload.get("filters", {}).get("killzone_mode") == "hard_filter" or payload.get("killzone_mode") == "hard_filter"
    improvement = 0.08 if alpha >= 8 else 0.0
    pf = 1.32 if hard_killzone else 1.15
    expectancy = 0.12 + improvement
    trades = 55 if hard_killzone else 70
    return {
        "run_id": f"run_{alpha}_{hard_killzone}",
        "summary": {
            "total_trades": trades,
            "win_rate": 0.45,
            "profit_factor": pf,
            "expectancy_R": expectancy,
            "average_R": expectancy,
            "average_win_R": 1.7,
            "average_loss_R": -1.0,
            "break_even_win_rate": 0.37,
            "max_drawdown_R": -5.5,
            "max_losing_streak": 4,
            "net_profit": 2400 if hard_killzone else 1500,
            "roi_percent": 2.4 if hard_killzone else 1.5,
            "skipped_setups": 12,
        },
        "trades": [{"result_R": expectancy} for _ in range(trades)],
        "data_health": {},
        "feature_summary": {},
        "regime_confidence": [],
    }


def test_ab_experiment_accepts_variant_that_beats_baseline(monkeypatch):
    monkeypatch.setattr(experiment_engine, "run_backtest", _fake_backtest)
    request = {
        "name": "R01 strict filter",
        "hypothesis": "Stricter alpha improves expectancy.",
        "baseline_label": "Baseline",
        "base_payload": {
            "symbol": "EURUSD",
            "timeframe": "M15",
            "start_date": "2025-11-01",
            "end_date": "2026-05-01",
            "regime_filter": "R01",
            "strategy_filter": "T1",
            "filters": {"min_alpha_score": 5, "killzone_mode": "score_only"},
        },
        "variants": [
            {
                "label": "Hard killzone alpha 8",
                "changes": {"killzone_mode": "hard_filter", "filters": {"killzone_mode": "hard_filter", "min_alpha_score": 8}},
            }
        ],
        "decision_rules": {
            "min_trades": 30,
            "min_profit_factor": 1.2,
            "min_expectancy_R": 0,
            "min_expectancy_improvement_R": 0.02,
            "max_drawdown_R": 10,
            "max_drawdown_worsening_R": 2,
        },
        "persist": False,
    }
    result = experiment_engine.run_ab_experiment(request)
    assert result["summary"]["status"] == "VARIANT_ACCEPTED"
    assert result["comparison"][0]["status"] == "ACCEPT_VARIANT"
    assert result["comparison"][0]["delta_expectancy_R"] > 0


def test_deep_merge_keeps_nested_baseline_fields():
    merged = experiment_engine._deep_merge(
        {"filters": {"min_alpha_score": 5, "max_spread_percentile": 70}, "rr": 2.0},
        {"filters": {"min_alpha_score": 8}},
    )
    assert merged["filters"]["min_alpha_score"] == 8
    assert merged["filters"]["max_spread_percentile"] == 70
    assert merged["rr"] == 2.0

