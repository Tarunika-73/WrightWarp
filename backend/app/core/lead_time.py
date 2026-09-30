"""Advance-purchase (lead-time / booking-window) configuration.

SIH26056 requires observations at T+1, T+7, T+15, T+30 and T+45 days
before travel. Rather than scattering the literal integers 1/7/15/30/45
through scrapers, validators and the index engine, every part of the
system imports ``LEAD_TIME_WINDOWS`` (or looks up a window via
``get_lead_time_window``) so a window can be added in one place.

The set is configurable without code changes through the
``BOOKING_WINDOWS`` environment variable (comma-separated day counts,
e.g. ``BOOKING_WINDOWS=1,7,15,30,45,60``). It is read once at import
time - booking windows define the shape of stored data, so changing
them is a deliberate redeploy, not a per-request option.
"""
import os
from dataclasses import dataclass

DEFAULT_WINDOW_DAYS: tuple[int, ...] = (1, 7, 15, 30, 45)


@dataclass(frozen=True)
class LeadTimeWindow:
    """A single advance-purchase window."""

    name: str
    days: int


def parse_window_days(raw: str | None) -> tuple[int, ...]:
    if not raw or not raw.strip():
        return DEFAULT_WINDOW_DAYS
    days: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        value = int(part)
        if value < 0 or value > 365:
            raise ValueError(f"booking window T+{value} is outside 0..365 days")
        days.add(value)
    if not days:
        return DEFAULT_WINDOW_DAYS
    return tuple(sorted(days))


LEAD_TIME_WINDOWS: tuple[LeadTimeWindow, ...] = tuple(
    LeadTimeWindow(name=f"T+{d}", days=d) for d in parse_window_days(os.environ.get("BOOKING_WINDOWS"))
)

LEAD_TIME_DAYS: tuple[int, ...] = tuple(w.days for w in LEAD_TIME_WINDOWS)

_BY_DAYS = {w.days: w for w in LEAD_TIME_WINDOWS}
_BY_NAME = {w.name: w for w in LEAD_TIME_WINDOWS}


def is_supported_lead_day(days: int) -> bool:
    return days in _BY_DAYS


def window_name(days: int) -> str:
    return f"T+{days}"


def get_lead_time_window(*, days: int | None = None, name: str | None = None) -> LeadTimeWindow:
    if days is not None:
        try:
            return _BY_DAYS[days]
        except KeyError as exc:
            raise ValueError(f"Unsupported lead-time window: T+{days}") from exc
    if name is not None:
        try:
            return _BY_NAME[name]
        except KeyError as exc:
            raise ValueError(f"Unsupported lead-time window: {name}") from exc
    raise ValueError("Must supply either days or name")
