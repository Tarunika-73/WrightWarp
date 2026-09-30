"""Index period keys: daily, weekly (ISO week), monthly.

Periods are anchored on the observation date (the IST day a price was
seen), matching CPI practice of pricing in the period of observation.
"""
from datetime import date, timedelta
from enum import Enum


class Frequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


def period_key(d: date, frequency: Frequency) -> str:
    if frequency == Frequency.DAILY:
        return d.isoformat()
    if frequency == Frequency.WEEKLY:
        iso_year, iso_week, _ = d.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    return f"{d.year}-{d.month:02d}"


def period_start(key: str, frequency: Frequency) -> date:
    if frequency == Frequency.DAILY:
        return date.fromisoformat(key)
    if frequency == Frequency.WEEKLY:
        year, week = key.split("-W")
        return date.fromisocalendar(int(year), int(week), 1)
    year, month = key.split("-")
    return date(int(year), int(month), 1)


def period_end(key: str, frequency: Frequency) -> date:
    start = period_start(key, frequency)
    if frequency == Frequency.DAILY:
        return start
    if frequency == Frequency.WEEKLY:
        return start + timedelta(days=6)
    next_month = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return next_month - timedelta(days=1)
