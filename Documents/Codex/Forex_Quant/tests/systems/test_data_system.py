from __future__ import annotations

import pytest

from core.time_utils import classify_session, time_in_window, to_utc
from systems.data.service import build_quality_report, read_csv_rows


def test_valid_csv_loading_and_quality_report(tmp_path):
    csv_path = tmp_path / "EURUSD_M15.csv"
    csv_path.write_text(
        "time,open,high,low,close,tick_volume,spread\n"
        "2026-01-01 00:00:00,1.1000,1.1010,1.0990,1.1005,100,1\n"
        "2026-01-01 00:15:00,1.1005,1.1015,1.1000,1.1010,110,1\n"
        "2026-01-01 00:30:00,1.1010,1.1020,1.1005,1.1015,120,20\n",
        encoding="utf-8",
    )
    rows, rows_in, issues = read_csv_rows(csv_path)
    report = build_quality_report("EURUSD", "M15", rows, rows_in, issues)
    assert rows_in == 3
    assert report.rows_out == 3
    assert any(issue.code == "abnormal_spread" for issue in report.issues)


def test_missing_required_column_fails(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("time,open,high,low,close,spread\n2026-01-01 00:00:00,1,1,1,1,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing required CSV columns"):
        read_csv_rows(csv_path)


def test_invalid_ohlc_rows_removed(tmp_path):
    csv_path = tmp_path / "bad_ohlc.csv"
    csv_path.write_text(
        "time,open,high,low,close,tick_volume,spread\n"
        "2026-01-01 00:00:00,1.1,1.0,1.2,1.1,100,1\n"
        "2026-01-01 00:15:00,1.1,1.2,1.0,1.1,100,1\n",
        encoding="utf-8",
    )
    rows, rows_in, issues = read_csv_rows(csv_path)
    assert rows_in == 2
    assert len(rows) == 1
    assert any(issue.code == "invalid_ohlc" for issue in issues)


def test_session_time_utility_crosses_midnight():
    moment = to_utc("2026-01-01 22:30:00")
    assert time_in_window(moment, "22:00", "01:00")
    label = classify_session(moment, {"timezone": "UTC", "sessions": [{"id": "Rollover", "start": "22:00", "end": "23:15", "modifier": "M06"}]})
    assert label["modifier"] == "M06"

