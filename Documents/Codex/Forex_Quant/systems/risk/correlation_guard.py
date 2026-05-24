from __future__ import annotations

from core.models.risk import AccountState, RiskApproval


def check_correlation(account: AccountState, max_correlated_trades: int = 2) -> RiskApproval:
    if account.correlated_open_trades >= max_correlated_trades:
        return RiskApproval(
            approved=False,
            action="rejected",
            reasons=[f"Correlated exposure count {account.correlated_open_trades} exceeds limit {max_correlated_trades}."],
        )
    return RiskApproval(approved=True, action="correlation_ok", reasons=["Correlation exposure is within limits."])

