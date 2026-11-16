"""Period arithmetic and timezone helpers.

Storage is UTC; presentation is Asia/Tashkent. Every "day/month/year" boundary in
the product is therefore computed in the display timezone, then converted to UTC
for the SQL predicate — otherwise a "day" would silently start at 05:00 local.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.errors import ValidationFailed

TZ = ZoneInfo(settings.DISPLAY_TZ)

GRANULARITIES = {"hour", "day", "week", "month", "year"}


def local_now() -> datetime:
    return datetime.now(TZ)


def to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(TZ)


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ).astimezone(UTC)
    return dt.astimezone(UTC)


def iso_local(dt: datetime | None) -> str | None:
    return to_local(dt).isoformat() if dt else None


def period_bounds(period: str, ref: date | datetime | None = None) -> tuple[datetime, datetime]:
    """Return [start, end) in UTC for a named period, evaluated in local time."""
    anchor = ref or local_now().date()
    if isinstance(anchor, datetime):
        anchor = to_local(anchor).date()
    if period == "today" or period == "day":
        start_local = datetime(anchor.year, anchor.month, anchor.day, tzinfo=TZ)
        end_local = start_local + timedelta(days=1)
    elif period == "yesterday":
        start_local = datetime(anchor.year, anchor.month, anchor.day, tzinfo=TZ) - timedelta(days=1)
        end_local = start_local + timedelta(days=1)
    elif period == "week":
        start_local = datetime(anchor.year, anchor.month, anchor.day, tzinfo=TZ) - timedelta(
            days=anchor.weekday())
        end_local = start_local + timedelta(days=7)
    elif period == "month" or period == "this_month":
        start_local = datetime(anchor.year, anchor.month, 1, tzinfo=TZ)
        end_local = datetime(anchor.year + (anchor.month == 12),
                            1 if anchor.month == 12 else anchor.month + 1, 1, tzinfo=TZ)
    elif period == "last_month":
        first = datetime(anchor.year, anchor.month, 1, tzinfo=TZ)
        end_local = first
        start_local = datetime(first.year - (first.month == 1),
                               12 if first.month == 1 else first.month - 1, 1, tzinfo=TZ)
    elif period == "quarter":
        q_start_month = 3 * ((anchor.month - 1) // 3) + 1
        start_local = datetime(anchor.year, q_start_month, 1, tzinfo=TZ)
        end_local = (datetime(anchor.year + (q_start_month == 10),
                              (q_start_month + 3 - 1) % 12 + 1, 1, tzinfo=TZ))
    elif period == "year" or period == "this_year":
        start_local = datetime(anchor.year, 1, 1, tzinfo=TZ)
        end_local = datetime(anchor.year + 1, 1, 1, tzinfo=TZ)
    elif period == "last_year":
        start_local = datetime(anchor.year - 1, 1, 1, tzinfo=TZ)
        end_local = datetime(anchor.year, 1, 1, tzinfo=TZ)
    elif period == "last_7_days":
        end_local = datetime(anchor.year, anchor.month, anchor.day, tzinfo=TZ) + timedelta(days=1)
        start_local = end_local - timedelta(days=7)
    elif period == "last_30_days":
        end_local = datetime(anchor.year, anchor.month, anchor.day, tzinfo=TZ) + timedelta(days=1)
        start_local = end_local - timedelta(days=30)
    elif period == "last_90_days":
        end_local = datetime(anchor.year, anchor.month, anchor.day, tzinfo=TZ) + timedelta(days=1)
        start_local = end_local - timedelta(days=90)
    else:
        raise ValidationFailed(
            f"Unknown period '{period}'. Use today, yesterday, week, month, last_month, "
            f"quarter, year, last_year, last_7_days, last_30_days, last_90_days or custom.",
            code="invalid_period")
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def previous_period(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """The immediately preceding window of identical length (for period-over-period)."""
    span = end - start
    return start - span, start


def same_period_last_year(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    def shift(dt: datetime) -> datetime:
        try:
            return dt.replace(year=dt.year - 1)
        except ValueError:  # 29 February
            return dt.replace(year=dt.year - 1, day=28)
    return shift(start), shift(end)


def granularity_for(start: datetime, end: datetime) -> str:
    days = (end - start).days
    if days <= 2:
        return "hour"
    if days <= 62:
        return "day"
    if days <= 400:
        return "week"
    return "month"
