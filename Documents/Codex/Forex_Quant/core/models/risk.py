from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AccountState:
    equity: float = 10000.0
    daily_loss_percent: float = 0.0
    total_drawdown_percent: float = 0.0
    open_trades: int = 0
    symbol_open_trades: int = 0
    correlated_open_trades: int = 0


@dataclass
class PresentRiskSnapshot:
    spread_percentile: float = 0.0
    data_quality_status: str = "ok"
    news_lock_active: bool = False
    weekend_or_rollover: bool = False
    broker_connected: bool = False
    manual_kill_switch: bool = False


@dataclass
class HistoricalTrustProfile:
    strategy_id: str = ""
    trades: int = 0
    profit_factor: float = 0.0
    expectancy_r: float = 0.0
    approved: bool = False


@dataclass
class PositionSizeResult:
    lot_size: float
    risk_amount: float
    final_risk_percent: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class RiskApproval:
    approved: bool
    action: str
    reasons: list[str] = field(default_factory=list)
    position_size: PositionSizeResult | None = None

