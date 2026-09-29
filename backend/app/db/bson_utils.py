"""BSON has no ``date`` type, only ``datetime`` - these are the one pair of
conversion functions used everywhere a ``datetime.date`` (``travel_date``)
crosses the boundary into or out of a MongoDB document.
"""
from datetime import date, datetime, time, timezone


def date_to_datetime(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def datetime_to_date(value: datetime) -> date:
    return value.date()
