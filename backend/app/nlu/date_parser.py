"""
Relative/absolute date expression parser for the `date_range` entity (entity-taxonomy.md).

Rule-based by design, consistent with Phase 6's default rule-based classification strategy —
date phrasing in this domain ("yesterday", "last week", "last 7 days") is a small, well-defined
vocabulary, not open-ended language. Returns None when no recognizable date expression is
found, rather than guessing; callers decide whether that means "no date filter" or
"ask for clarification."
"""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_MONTHS = {
    name: i
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may", "may"),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for name in names
}

_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAY_MONTH_YEAR_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-zA-Z]+)(?:\s+(\d{4}))?\b"
)
_LAST_N_DAYS_RE = re.compile(r"\b(?:last|past)\s+(\d+)\s+days?\b")


def _today(now: datetime, tz: ZoneInfo) -> date:
    return now.astimezone(tz).date()



def _day_bounds(d: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime(d.year, d.month, d.day, tzinfo=tz)
    return start, start + timedelta(days=1)


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())  # Monday


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_month(d: date) -> date:
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1)
    return d.replace(month=d.month + 1)


def _parse_single_date(text: str, today: date) -> date | None:
    text = text.strip().lower()

    if text == "today":
        return today
    if text == "yesterday":
        return today - timedelta(days=1)
    if text == "tomorrow":
        return today + timedelta(days=1)

    m = _ISO_DATE_RE.search(text)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None

    m = _DAY_MONTH_YEAR_RE.search(text)
    if m:
        day_num, month_name, year = m.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            try:
                return date(int(year) if year else today.year, month, int(day_num))
            except ValueError:
                return None

    return None


def parse_date_range(
    text: str, now: datetime, tz_name: str = "Asia/Kolkata"
) -> tuple[datetime, datetime] | None:
    """Returns (start, end) as tz-aware datetimes spanning whole days, or None if no
    recognizable date expression is present in `text`."""
    tz = ZoneInfo(tz_name)
    today = _today(now, tz)
    lowered = text.strip().lower()
    if not lowered:
        return None

    if "yesterday" in lowered:
        start, end = _day_bounds(today - timedelta(days=1), tz)
        return start, end
    if "today" in lowered:
        start, end = _day_bounds(today, tz)
        return start, end

    if "this week" in lowered:
        start = datetime.combine(_week_start(today), datetime.min.time(), tzinfo=tz)
        return start, now.astimezone(tz)
    if "last week" in lowered:
        this_week_start = _week_start(today)
        start = datetime.combine(this_week_start - timedelta(days=7), datetime.min.time(), tzinfo=tz)
        end = datetime.combine(this_week_start, datetime.min.time(), tzinfo=tz)
        return start, end

    if "this month" in lowered:
        start = datetime.combine(_month_start(today), datetime.min.time(), tzinfo=tz)
        return start, now.astimezone(tz)
    if "last month" in lowered:
        this_month_start = _month_start(today)
        last_month_end = this_month_start
        last_month_start = _month_start(last_month_end - timedelta(days=1))
        start = datetime.combine(last_month_start, datetime.min.time(), tzinfo=tz)
        end = datetime.combine(last_month_end, datetime.min.time(), tzinfo=tz)
        return start, end

    m = _LAST_N_DAYS_RE.search(lowered)
    if m:
        n = int(m.group(1))
        start = datetime.combine(today - timedelta(days=n), datetime.min.time(), tzinfo=tz)
        return start, now.astimezone(tz)

    range_match = re.search(r"(?:from|between)\s+(.+?)\s+(?:to|and)\s+(.+)", lowered)
    if range_match:
        left_raw, right_raw = range_match.groups()
        left = _parse_single_date(left_raw, today)
        right = _parse_single_date(right_raw, today)
        if left and right:
            start = datetime.combine(left, datetime.min.time(), tzinfo=tz)
            end = datetime.combine(right, datetime.min.time(), tzinfo=tz) + timedelta(days=1)
            return start, end
        return None

    single = _parse_single_date(lowered, today)
    if single:
        return _day_bounds(single, tz)

    return None
