from __future__ import annotations

from core.models.risk import AccountState, PresentRiskSnapshot, RiskApproval


def check_funded_rules(account: AccountState, snapshot: PresentRiskSnapshot, rules: dict) -> RiskApproval:
    reasons: list[str] = []
    max_daily_loss = float(rules.get("max_daily_loss_percent", 3.0))
    buffer_percent = float(rules.get("daily_lock_buffer_percent", 60))
    lock_threshold = max_daily_loss * (buffer_percent / 100.0)
    if account.daily_loss_percent >= lock_threshold:
        reasons.append(f"Daily loss {account.daily_loss_percent:.2f}% is near the daily lock threshold {lock_threshold:.2f}%.")

    max_drawdown = float(rules.get("max_total_drawdown_percent", 8.0))
    if account.total_drawdown_percent >= max_drawdown:
        reasons.append(f"Total drawdown {account.total_drawdown_percent:.2f}% exceeds {max_drawdown:.2f}%.")

    if account.open_trades >= int(rules.get("max_open_trades", 2)):
        reasons.append("Maximum open trade count reached.")
    if account.symbol_open_trades >= int(rules.get("max_symbol_trades", 1)):
        reasons.append("Symbol already has the maximum allowed open trades.")
    if snapshot.news_lock_active and not bool(rules.get("news_trading_allowed", False)):
        reasons.append("News lock is active and news trading is disabled.")
    if snapshot.weekend_or_rollover and not bool(rules.get("weekend_holding_allowed", False)):
        reasons.append("Weekend/rollover rule blocks new risk.")

    if reasons:
        return RiskApproval(approved=False, action="rejected", reasons=reasons)
    return RiskApproval(approved=True, action="funded_rules_ok", reasons=["Funded-account rules pass."])

