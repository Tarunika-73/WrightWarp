"""Advance-purchase (lead-time) window configuration.

SIH26056 requires observations at T+1, T+7, T+15, T+30 and T+45 days
before travel. Rather than scattering the literal integers 1/7/15/30/45
through scrapers, validators and the index engine, every part of the
system should import ``LEAD_TIME_WINDOWS`` (or look up a window by name
via ``get_lead_time_window``) so a future window can be added in one
place without touching business logic.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class LeadTimeWindow:
    """A single advance-purchase window."""

    name: str
    days: int


LEAD_TIME_WINDOWS: tuple[LeadTimeWindow, ...] = (
    LeadTimeWindow(name="T+1", days=1),
    LeadTimeWindow(name="T+7", days=7),
    LeadTimeWindow(name="T+15", days=15),
    LeadTimeWindow(name="T+30", days=30),
    LeadTimeWindow(name="T+45", days=45),
)

LEAD_TIME_DAYS: tuple[int, ...] = tuple(w.days for w in LEAD_TIME_WINDOWS)

_BY_DAYS = {w.days: w for w in LEAD_TIME_WINDOWS}
_BY_NAME = {w.name: w for w in LEAD_TIME_WINDOWS}


def is_supported_lead_day(days: int) -> bool:
    return days in _BY_DAYS


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
