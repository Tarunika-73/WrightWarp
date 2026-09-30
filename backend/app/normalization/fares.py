"""Source-independent fare normalization.

Turns the loosely-typed fare fields an adapter found (numbers, numeric
strings such as ``"₹5,234.00"``, currency symbols, missing keys) into a
standard internal representation, without inventing anything:

* A component the source did not provide stays ``None`` and is absent
  from ``components_available``. There is no "typical tax rate" fill-in.
* ``total_fare`` is never derived from components. If a source shows only
  a total, the total is kept and every component is marked unavailable;
  if it shows components but no total, the observation has no total and
  the quality engine marks it ``MISSING``.
* Timestamps are converted to timezone-aware UTC. A naive timestamp is
  assumed to be Indian Standard Time, the local time of every source in
  scope, and that assumption is recorded in ``timestamp_assumed_ist``.
* The *observation date* (the date the price was seen, which is what
  index periods are built on) is the IST calendar date of the search
  timestamp. An Indian index day is an Indian calendar day.

Pure functions only - no database access - so both the live collection
service and the historical demo backfill use exactly the same code.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

NORMALIZATION_VERSION = "fare-norm/1.0"

IST = timezone(timedelta(hours=5, minutes=30), name="IST")

# Fare components, in the order they are summed for consistency checks.
# ``total_fare`` is deliberately not in this list.
COMPONENT_FIELDS: tuple[str, ...] = (
    "base_fare",
    "taxes",
    "airport_charges",
    "user_development_fee",
    "fuel_surcharge",
    "convenience_fee",
    "baggage_fee",
    "seat_fee",
    "meal_fee",
    "other_fees",
)

# Components that are part of the mandatory price every passenger pays.
# Ancillaries (baggage/seat/meal) are optional purchases and are excluded
# from the airfare the index measures.
MANDATORY_COMPONENTS: tuple[str, ...] = (
    "base_fare",
    "taxes",
    "airport_charges",
    "user_development_fee",
    "fuel_surcharge",
    "convenience_fee",
    "other_fees",
)

# Aliases some sources use for the same concept.
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "base_fare": ("base_fare", "basefare", "base", "fare_base"),
    "taxes": ("taxes", "tax", "taxes_and_fees", "gst"),
    "airport_charges": ("airport_charges", "airport_fee", "psf", "passenger_service_fee"),
    "user_development_fee": ("user_development_fee", "udf"),
    "fuel_surcharge": ("fuel_surcharge", "yq"),
    "convenience_fee": ("convenience_fee", "conv_fee", "channel_fee"),
    "baggage_fee": ("baggage_fee",),
    "seat_fee": ("seat_fee",),
    "meal_fee": ("meal_fee",),
    "other_fees": ("other_fees", "other_charges"),
    "total_fare": ("total_fare", "total", "total_price", "price", "fare"),
}

_CURRENCY_SYMBOLS = {"₹": "INR", "RS": "INR", "RS.": "INR", "INR": "INR", "$": "USD", "USD": "USD", "€": "EUR", "EUR": "EUR"}

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


class FareParseError(ValueError):
    """A fare field was present but could not be read as a number."""


def parse_amount(value: object) -> float | None:
    """Read a money amount from a number or a display string.

    ``None``/``""`` -> ``None`` (absent, not zero). ``"₹5,234.50"`` -> 5234.5.
    Raises ``FareParseError`` for anything else that is not a number, so
    garbage is never silently read as a price.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise FareParseError(f"boolean is not an amount: {value!r}")
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        cleaned = text.replace(",", "").replace("₹", "").replace("INR", "").replace("Rs.", "").replace("Rs", "").strip()
        match = _NUMBER_RE.fullmatch(cleaned)
        if not match:
            raise FareParseError(f"not a numeric amount: {value!r}")
        return round(float(match.group(0)), 2)
    raise FareParseError(f"unsupported amount type {type(value).__name__}")


def normalize_currency(value: object, *, amount_hint: object = None) -> str | None:
    """Return an ISO-4217 code, inferring from a symbol in ``amount_hint`` if needed."""
    if isinstance(value, str) and value.strip():
        key = value.strip().upper()
        return _CURRENCY_SYMBOLS.get(key, key if len(key) == 3 and key.isalpha() else None)
    if isinstance(amount_hint, str):
        if "₹" in amount_hint or amount_hint.upper().startswith(("RS", "INR")):
            return "INR"
    return None


def to_utc(value: datetime) -> tuple[datetime, bool]:
    """Return ``(utc_datetime, assumed_ist)``. Naive input is taken as IST."""
    if value.tzinfo is None:
        return value.replace(tzinfo=IST).astimezone(timezone.utc), True
    return value.astimezone(timezone.utc), False


def observation_date(search_datetime_utc: datetime) -> date:
    """The IST calendar date a price was observed on - the index-period anchor."""
    return search_datetime_utc.astimezone(IST).date()


def _first_present(raw: dict, field_name: str) -> object:
    for alias in _FIELD_ALIASES.get(field_name, (field_name,)):
        if alias in raw and raw[alias] is not None and raw[alias] != "":
            return raw[alias]
    return None


@dataclass
class NormalizedFare:
    components: dict[str, float | None]
    total_fare: float | None
    currency: str | None
    components_available: list[str]
    parse_errors: list[str] = field(default_factory=list)
    version: str = NORMALIZATION_VERSION

    @property
    def mandatory_component_sum(self) -> float | None:
        """Sum of mandatory components, or ``None`` unless at least base fare and taxes are known."""
        if self.components.get("base_fare") is None or self.components.get("taxes") is None:
            return None
        return round(sum(self.components[c] or 0.0 for c in MANDATORY_COMPONENTS), 2)

    @property
    def components_complete(self) -> bool:
        return self.mandatory_component_sum is not None


def normalize_fare(raw: dict) -> NormalizedFare:
    """Extract fare components/total/currency from one raw payload. Never fabricates a value."""
    components: dict[str, float | None] = {}
    errors: list[str] = []
    for name in COMPONENT_FIELDS:
        try:
            components[name] = parse_amount(_first_present(raw, name))
        except FareParseError as exc:
            components[name] = None
            errors.append(f"{name}: {exc}")

    raw_total = _first_present(raw, "total_fare")
    try:
        total = parse_amount(raw_total)
    except FareParseError as exc:
        total = None
        errors.append(f"total_fare: {exc}")

    currency = normalize_currency(raw.get("currency"), amount_hint=raw_total)
    available = [name for name in COMPONENT_FIELDS if components[name] is not None]
    return NormalizedFare(
        components=components,
        total_fare=total,
        currency=currency,
        components_available=available,
        parse_errors=errors,
    )
