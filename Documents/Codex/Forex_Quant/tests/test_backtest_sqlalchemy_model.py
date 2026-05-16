"""SQLite + SQLAlchemy backtest run model sanity checks."""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from core.models.backtest import BacktestRun, Base


def test_backtest_run_schema_roundtrip():
    # In-memory + StaticPool avoids Windows file locks on temp directory cleanup.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    try:
        Base.metadata.create_all(bind=engine)
        with Session(engine) as session:
            row = BacktestRun(
                regime_id="Q3_M04",
                strategy_id="Q3_M04_S01",
                slot="primary",
                total_trades=10,
                wins=6,
                losses=4,
                win_rate=0.6,
                profit_factor=1.4,
                sharpe=0.9,
                sortino=1.1,
                max_drawdown=2.0,
                expectancy=0.15,
                net_profit=120.0,
                avg_rr_achieved=2.2,
                kill_zone_win_rate=0.71,
                no_kill_zone_win_rate=0.51,
                kill_zone_count=4,
                no_kill_zone_count=6,
                trades_json=[{"id": "t1"}],
                equity_curve_json=[{"trade_no": 1, "equity": 10050.0}],
                settings_json={"killzone_enabled": True},
                validated=False,
                validation_note="insufficient sample",
            )
            session.add(row)
            session.commit()
            fetched = session.execute(
                select(BacktestRun).where(BacktestRun.regime_id == "Q3_M04")
            ).scalar_one()
            assert fetched.strategy_id == "Q3_M04_S01"
            assert fetched.trades_json == [{"id": "t1"}]
    finally:
        engine.dispose()

