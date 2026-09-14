"""Date/week window helpers shared by subscription, reservation, and QR logic.

WEEK DEFINITION (documented business rule, see docs/frontend/QR_AND_BOARDING.md):

- A "week" is a deterministic calendar week running MONDAY through SUNDAY,
  evaluated in the project's business timezone.
- The whole backend stores and compares dates in UTC (subscription start/end
  dates, boarding timestamps, and every existing date calculation use UTC),
  so the business timezone here is UTC as well. The week-start constant below
  is the single point of change if the business adopts a local timezone.
- Weekly usage = number of DISTINCT calendar dates with at least one successful
  QR scan (outbound or return) inside the current week window.
- Outbound + return scans on the same calendar date count as ONE usage day.
- Unused weekly allowance does NOT roll over; each week starts fresh with
  ``days_per_week`` allowance.
"""

from datetime import date, datetime, time, timedelta, timezone

# 0 = Monday ... 6 = Sunday (ISO weekday index).
WEEK_START_WEEKDAY: int = 0

# The project's canonical business timezone: UTC. All existing date handling
# (subscriptions, boarding, payments) already uses UTC; this constant exists so
# the choice is explicit and centralized rather than accidental.
BUSINESS_TIMEZONE = timezone.utc


def business_today() -> date:
    """Return the current calendar date in the business timezone (UTC)."""
    return datetime.now(BUSINESS_TIMEZONE).date()


def week_start(day: date) -> date:
    """Return the MONDAY that starts the calendar week containing ``day``."""
    offset = (day.weekday() - WEEK_START_WEEKDAY) % 7
    return day - timedelta(days=offset)


def week_end(day: date) -> date:
    """Return the SUNDAY that ends the calendar week containing ``day``."""
    return week_start(day) + timedelta(days=6)


def week_window(day: date) -> tuple[date, date]:
    """Return the inclusive (start, end) calendar-week window for ``day``."""
    return week_start(day), week_end(day)


def next_day(day: date | None = None) -> date:
    """Return the day after ``day`` (or after today in the business timezone)."""
    if day is None:
        day = business_today()
    return day + timedelta(days=1)


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """Return the timezone-aware [start, end) datetimes of a business-date day."""
    start = datetime.combine(day, time.min, tzinfo=BUSINESS_TIMEZONE)
    end = start + timedelta(days=1)
    return start, end
