from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.nlu.date_parser import parse_date_range

TZ = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 7, 28, 10, 0, tzinfo=TZ)  # a Tuesday


def test_yesterday():
    start, end = parse_date_range("show trips yesterday", NOW, "Asia/Kolkata")
    assert start == datetime(2026, 7, 27, tzinfo=TZ)
    assert end == datetime(2026, 7, 28, tzinfo=TZ)


def test_today():
    start, end = parse_date_range("alerts today", NOW, "Asia/Kolkata")
    assert start == datetime(2026, 7, 28, tzinfo=TZ)
    assert end == datetime(2026, 7, 29, tzinfo=TZ)


def test_this_week():
    start, end = parse_date_range("trips this week", NOW, "Asia/Kolkata")
    assert start == datetime(2026, 7, 27, tzinfo=TZ)  # Monday of that week
    assert end == NOW


def test_last_week():
    start, end = parse_date_range("trips last week", NOW, "Asia/Kolkata")
    assert start == datetime(2026, 7, 20, tzinfo=TZ)
    assert end == datetime(2026, 7, 27, tzinfo=TZ)


def test_this_month():
    start, end = parse_date_range("distance this month", NOW, "Asia/Kolkata")
    assert start == datetime(2026, 7, 1, tzinfo=TZ)
    assert end == NOW


def test_last_month():
    start, end = parse_date_range("alerts last month", NOW, "Asia/Kolkata")
    assert start == datetime(2026, 6, 1, tzinfo=TZ)
    assert end == datetime(2026, 7, 1, tzinfo=TZ)


def test_last_n_days():
    start, end = parse_date_range("alerts in the last 7 days", NOW, "Asia/Kolkata")
    assert start == datetime(2026, 7, 21, tzinfo=TZ)
    assert end == NOW


def test_iso_date():
    start, end = parse_date_range("trips on 2026-07-15", NOW, "Asia/Kolkata")
    assert start == datetime(2026, 7, 15, tzinfo=TZ)
    assert end == datetime(2026, 7, 16, tzinfo=TZ)


def test_day_month_year():
    start, end = parse_date_range("trips on 15 July 2026", NOW, "Asia/Kolkata")
    assert start == datetime(2026, 7, 15, tzinfo=TZ)
    assert end == datetime(2026, 7, 16, tzinfo=TZ)


def test_day_month_without_year_defaults_to_current_year():
    start, _ = parse_date_range("trips on 3 July", NOW, "Asia/Kolkata")
    assert start.year == 2026


def test_explicit_range():
    start, end = parse_date_range("trips from 1 July to 15 July", NOW, "Asia/Kolkata")
    assert start == datetime(2026, 7, 1, tzinfo=TZ)
    assert end == datetime(2026, 7, 16, tzinfo=TZ)  # end-of-day inclusive of the 15th


def test_no_date_expression_returns_none():
    assert parse_date_range("show me my trips", NOW, "Asia/Kolkata") is None


def test_empty_string_returns_none():
    assert parse_date_range("", NOW, "Asia/Kolkata") is None


def test_unsupported_vague_phrase_returns_none():
    assert parse_date_range("sometime a while back", NOW, "Asia/Kolkata") is None
