from __future__ import annotations

from typing import Any


def explain_regime_detection(features: dict[str, Any], regime_result: dict[str, Any], modifiers: dict[str, Any]) -> str:
    if regime_result["regime_id"] == "NONE":
        return "No tradable regime is active because: " + "; ".join(regime_result.get("reasons", []))
    passed = "; ".join(regime_result.get("reasons", [])[:6])
    modifier_text = "; ".join(modifiers.get("reasons", [])[:4])
    return f"{regime_result['regime_id']} {regime_result['regime_name']} was evaluated with confidence {regime_result['confidence']:.2f}. Passed: {passed}. Modifiers: {modifier_text or 'none'}."


def explain_trade_entry(strategy_result: dict[str, Any], alpha_score: dict[str, Any]) -> str:
    if not strategy_result.get("triggered"):
        return strategy_result.get("reason", "Strategy entry conditions are not met.")
    return f"{strategy_result['strategy_name']} triggered because {strategy_result['reason']} Alpha decision: {alpha_score['decision']} with score {alpha_score['alpha_score']}."


def explain_backtest_summary(summary: dict[str, Any], regime_performance: list[dict[str, Any]], strategy_performance: list[dict[str, Any]]) -> dict[str, list[str]]:
    what_worked: list[str] = []
    what_failed: list[str] = []
    warnings: list[str] = []

    for item in regime_performance:
        if item["trade_count"] >= 20 and item["expectancy_R"] > 0:
            what_worked.append(
                f"{item['regime_id']} {item['regime_name']} showed positive expectancy ({item['expectancy_R']:.2f}R) with profit factor {item['profit_factor']:.2f}."
            )
        elif item["trade_count"] >= 20 and item["expectancy_R"] <= 0:
            what_failed.append(
                f"{item['regime_id']} {item['regime_name']} failed with expectancy {item['expectancy_R']:.2f}R. Review filters, spread sensitivity, and session behavior."
            )
        elif item["trade_count"] < 20:
            warnings.append(f"{item['regime_id']} {item['regime_name']} has fewer than 20 trades, so it is not enough evidence.")

    for item in strategy_performance:
        if item["trade_count"] >= 20 and item["expectancy_R"] <= 0:
            what_failed.append(
                f"{item['strategy_id']} {item['strategy_name']} did not hold up in this sample. It may be firing in the wrong regime or after weak confirmation."
            )

    if not what_worked:
        warnings.append("No regime-strategy combination has enough positive evidence yet.")
    if summary.get("total_trades", 0) < 100:
        warnings.append("Overall trade count is below 100, so approval should remain conservative.")

    return {"what_worked": what_worked, "what_failed": what_failed, "warnings": warnings}
