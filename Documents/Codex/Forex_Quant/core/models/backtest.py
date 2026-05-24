"""
SQLAlchemy persistence for backtest run summaries (SQLite, zero extra services).

Kept separate from systems/analysis DuckDB paths so this model can be queried
with standard ORM patterns without migrating legacy tables.
"""

from __future__ import annotations

import datetime
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "analysis" / "backtest_runs_sa.sqlite"

Base = declarative_base()


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    regime_id = Column(String, index=True)  # "Q1_M04"
    strategy_id = Column(String)  # "Q1_M04_S01"
    slot = Column(String)  # "primary"
    symbol = Column(String, default="EURUSD")
    timeframe = Column(String, default="M15")
    investment = Column(Float, default=10000.0)
    risk_per_trade = Column(Float, default=0.01)

    # Metrics
    total_trades = Column(Integer)
    wins = Column(Integer)
    losses = Column(Integer)
    win_rate = Column(Float)
    profit_factor = Column(Float)
    sharpe = Column(Float)
    sortino = Column(Float)
    max_drawdown = Column(Float)  # in R
    expectancy = Column(Float)  # avg R per trade
    net_profit = Column(Float)  # in $
    avg_rr_achieved = Column(Float)

    # Kill zone breakdown
    kill_zone_win_rate = Column(Float, nullable=True)
    no_kill_zone_win_rate = Column(Float, nullable=True)
    kill_zone_count = Column(Integer, default=0)
    no_kill_zone_count = Column(Integer, default=0)

    # Failure analysis
    institutional_trap_failures = Column(Integer, default=0)
    sweep_failures = Column(Integer, default=0)
    spread_rejections = Column(Integer, default=0)

    # Raw data
    trades_json = Column(JSON)
    equity_curve_json = Column(JSON)
    settings_json = Column(JSON)

    validated = Column(Boolean, default=False)
    validation_note = Column(Text)
    created_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )


_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def _get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_backtest_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
    return _SessionFactory


def get_backtest_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request."""
    db = _get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def get_backtest_engine(*, sqlite_path: Path | None = None) -> Engine:
    """Singleton SQLite engine for backtest_runs_sa.sqlite."""
    global _engine
    if _engine is not None:
        return _engine
    path = sqlite_path or DEFAULT_SQLITE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{path.as_posix()}",
        echo=False,
        future=True,
    )
    return _engine


def init_backtest_db(engine: Engine | None = None) -> Engine:
    """Create tables if missing. Call once at app startup."""
    eng = engine or get_backtest_engine()
    Base.metadata.create_all(bind=eng)
    return eng


def reset_engine_for_tests() -> None:
    """Clear cached engine (pytest isolation)."""
    global _engine, _SessionFactory
    _engine = None
    _SessionFactory = None
