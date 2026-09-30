"""Data-quality engine: one raw fare observation in, one quality decision out.

Every rule is a small pure function returning ``RuleResult``s, so each can
be unit-tested alone, and ``assess`` combines them with a fixed severity
order. Nothing is ever deleted here: the decision (status + reasons +
flags) is stored on the observation, and the index engine includes only
``INDEX_ELIGIBLE_QUALITY`` statuses. Suspicious data stays auditable.

Severity (highest wins):
    REJECTED > MISSING > SOLD_OUT > DUPLICATE > REVIEW_REQUIRED > OUTLIER > PROVISIONAL > VALIDATED

The context the engine needs from outside - "have we already seen this
observation?" and "what does a normal fare on this route/window look
like?" - is passed in through ``QualityContext``, so the engine never
queries a database itself. ``app.quality.context`` builds that context
from MongoDB for live collection; the demo backfill builds it in memory.
"""
import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from app.core.enums import AvailabilityStatus, QualityStatus
from app.core.lead_time import is_supported_lead_day
from app.core.routes import is_monitored_route
from app.normalization.fares import NormalizedFare

QUALITY_RULES_VERSION = "quality-rules/1.0"

SUPPORTED_CURRENCIES = frozenset({"INR"})

# Plausibility bounds for a one-way domestic economy fare, INR. These are
# deliberately wide sanity limits (a typo or a unit error), not a
# statistical filter - statistical outliers are the job of the robust
# z-score rule below.
MIN_PLAUSIBLE_FARE_INR = 500.0
MAX_PLAUSIBLE_FARE_INR = 150_000.0

MAX_ADVANCE_DAYS = 365

# Component-sum tolerance: max(absolute, relative * total).
COMPONENT_TOLERANCE_ABS = 1.0
COMPONENT_TOLERANCE_REL = 0.01

# Robust z-score threshold (Iglewicz & Hoaglin's modified z-score, 3.5 is
# their recommended cut-off) and the minimum reference sample size below
# which no outlier call is made at all.
OUTLIER_Z_THRESHOLD = 3.5
MIN_REFERENCE_SAMPLE = 10

_SEVERITY: tuple[QualityStatus, ...] = (
    QualityStatus.REJECTED,
    QualityStatus.MISSING,
    QualityStatus.SOLD_OUT,
    QualityStatus.DUPLICATE,
    QualityStatus.REVIEW_REQUIRED,
    QualityStatus.OUTLIER,
    QualityStatus.PROVISIONAL,
    QualityStatus.VALIDATED,
)


@dataclass(frozen=True)
class FareObservation:
    """The fields the quality rules look at, already normalized."""

    source: str | None
    origin: str | None
    destination: str | None
    travel_date: date | None
    search_datetime: datetime | None  # UTC-aware
    observation_date: date | None  # IST calendar date
    lead_days: int | None
    airline_code: str | None
    flight_number: str | None
    cabin_class: str | None
    availability_status: str
    fare: NormalizedFare

    @property
    def route_code(self) -> str | None:
        if self.origin and self.destination:
            return f"{self.origin}-{self.destination}"
        return None


@dataclass(frozen=True)
class ReferenceStats:
    """Robust summary of recent valid log-fares for one route x booking window."""

    median_log_fare: float
    mad_log_fare: float
    sample_size: int


@dataclass
class QualityContext:
    """External knowledge the rules need. Both hooks are optional."""

    is_duplicate: Callable[[str], bool] = lambda _key: False
    reference_for: Callable[[str, int], ReferenceStats | None] = lambda _route, _lead: None


@dataclass(frozen=True)
class RuleResult:
    status: QualityStatus
    reason: str


@dataclass
class QualityAssessment:
    status: QualityStatus
    reasons: list[str]
    flags: list[str] = field(default_factory=list)
    score: float = 1.0
    dedup_key: str | None = None
    robust_z: float | None = None
    rules_version: str = QUALITY_RULES_VERSION

    @property
    def reason(self) -> str | None:
        return "; ".join(self.reasons) if self.reasons else None


# ---------------------------------------------------------------- rules


def check_required_fields(obs: FareObservation) -> list[RuleResult]:
    missing = [
        name
        for name, value in (
            ("source", obs.source),
            ("origin", obs.origin),
            ("destination", obs.destination),
            ("travel_date", obs.travel_date),
            ("search_datetime", obs.search_datetime),
            ("lead_days", obs.lead_days),
        )
        if value in (None, "")
    ]
    return [RuleResult(QualityStatus.REJECTED, f"missing_required_field:{name}") for name in missing]


def check_route(obs: FareObservation) -> list[RuleResult]:
    if not obs.origin or not obs.destination:
        return []
    results = []
    for label, code in (("origin", obs.origin), ("destination", obs.destination)):
        if len(code) != 3 or not code.isalpha() or not code.isupper():
            results.append(RuleResult(QualityStatus.REJECTED, f"invalid_airport_code:{label}={code}"))
    if obs.origin == obs.destination:
        results.append(RuleResult(QualityStatus.REJECTED, "origin_equals_destination"))
    if not results and not is_monitored_route(obs.origin, obs.destination):
        results.append(RuleResult(QualityStatus.REVIEW_REQUIRED, f"route_not_in_master:{obs.route_code}"))
    return results


def check_travel_date(obs: FareObservation) -> list[RuleResult]:
    if obs.travel_date is None or obs.observation_date is None:
        return []
    if obs.travel_date < obs.observation_date:
        return [RuleResult(QualityStatus.REJECTED, "travel_date_before_observation_date")]
    if (obs.travel_date - obs.observation_date).days > MAX_ADVANCE_DAYS:
        return [RuleResult(QualityStatus.REJECTED, "travel_date_too_far_ahead")]
    return []


def check_search_timestamp(obs: FareObservation, *, now: datetime | None = None) -> list[RuleResult]:
    if obs.search_datetime is None:
        return []
    if obs.search_datetime.tzinfo is None:
        return [RuleResult(QualityStatus.REJECTED, "search_datetime_not_timezone_aware")]
    now = now or datetime.now(timezone.utc)
    if (obs.search_datetime - now).total_seconds() > 300:
        return [RuleResult(QualityStatus.REJECTED, "search_datetime_in_future")]
    return []


def check_lead_time(obs: FareObservation) -> list[RuleResult]:
    if obs.lead_days is None:
        return []
    if not is_supported_lead_day(obs.lead_days):
        return [RuleResult(QualityStatus.REJECTED, f"unsupported_booking_window:T+{obs.lead_days}")]
    if obs.travel_date is not None and obs.observation_date is not None:
        actual = (obs.travel_date - obs.observation_date).days
        # A one-day slip is expected around midnight IST (a search at 23:59
        # UTC-converted vs the source's own clock); more is a real mismatch.
        if abs(actual - obs.lead_days) > 1:
            return [RuleResult(QualityStatus.REVIEW_REQUIRED, f"lead_time_mismatch:declared={obs.lead_days},actual={actual}")]
    return []


def check_availability(obs: FareObservation) -> list[RuleResult]:
    status = obs.availability_status
    if status in (AvailabilityStatus.SOLD_OUT.value, AvailabilityStatus.CANCELLED.value):
        return [RuleResult(QualityStatus.SOLD_OUT, f"availability:{status}")]
    if status in (AvailabilityStatus.NOT_FOUND.value, AvailabilityStatus.SCRAPE_FAILED.value):
        return [RuleResult(QualityStatus.MISSING, f"availability:{status}")]
    if status == AvailabilityStatus.INVALID_QUOTE.value:
        return [RuleResult(QualityStatus.REJECTED, "availability:INVALID_QUOTE")]
    if status == AvailabilityStatus.UNKNOWN.value and obs.fare.total_fare is not None:
        return [RuleResult(QualityStatus.REVIEW_REQUIRED, "availability_unknown_but_fare_present")]
    return []


def check_currency(obs: FareObservation) -> list[RuleResult]:
    if obs.fare.total_fare is None:
        return []
    if obs.fare.currency is None:
        return [RuleResult(QualityStatus.REJECTED, "missing_currency")]
    if obs.fare.currency not in SUPPORTED_CURRENCIES:
        # No FX conversion: converting would mean choosing a rate and date
        # the source never showed. A human decides.
        return [RuleResult(QualityStatus.REVIEW_REQUIRED, f"unsupported_currency:{obs.fare.currency}")]
    return []


def check_fare_value(obs: FareObservation) -> list[RuleResult]:
    fare = obs.fare
    results = [RuleResult(QualityStatus.REJECTED, f"unparseable_fare_field:{err}") for err in fare.parse_errors]
    available = obs.availability_status == AvailabilityStatus.AVAILABLE.value
    if fare.total_fare is None:
        if available:
            results.append(RuleResult(QualityStatus.MISSING, "missing_total_fare"))
        return results
    if fare.total_fare <= 0:
        results.append(RuleResult(QualityStatus.REJECTED, "non_positive_fare"))
    elif fare.currency == "INR" and not (MIN_PLAUSIBLE_FARE_INR <= fare.total_fare <= MAX_PLAUSIBLE_FARE_INR):
        results.append(RuleResult(QualityStatus.REJECTED, f"implausible_fare:{fare.total_fare:.2f}"))
    return results


def check_fare_components(obs: FareObservation) -> list[RuleResult]:
    fare = obs.fare
    results = [
        RuleResult(QualityStatus.REJECTED, f"negative_component:{name}")
        for name, value in fare.components.items()
        if value is not None and value < 0
    ]
    if results or fare.total_fare is None:
        return results
    component_sum = fare.mandatory_component_sum
    if component_sum is None:
        return []  # Total-only source: nothing to reconcile, and nothing is invented.
    tolerance = max(COMPONENT_TOLERANCE_ABS, COMPONENT_TOLERANCE_REL * fare.total_fare)
    if abs(component_sum - fare.total_fare) > tolerance:
        return [RuleResult(QualityStatus.REVIEW_REQUIRED, f"component_sum_mismatch:sum={component_sum:.2f},total={fare.total_fare:.2f}")]
    return []


def compute_dedup_key(obs: FareObservation) -> str | None:
    """Identity of "the same fare seen twice": source, flight, travel date, cabin, observation day.

    The fare amount is intentionally not part of the key - a second,
    different price for the same flight from the same source on the same
    day is a re-observation to be reviewed, not an independent data point.
    """
    if not (obs.source and obs.route_code and obs.travel_date and obs.observation_date):
        return None
    parts = [
        obs.source,
        obs.route_code,
        obs.travel_date.isoformat(),
        str(obs.lead_days),
        obs.airline_code or "-",
        obs.flight_number or "-",
        obs.cabin_class or "-",
        obs.observation_date.isoformat(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def check_duplicate(dedup_key: str | None, context: QualityContext) -> list[RuleResult]:
    if dedup_key is not None and context.is_duplicate(dedup_key):
        return [RuleResult(QualityStatus.DUPLICATE, "duplicate_of_earlier_observation")]
    return []


def robust_z_score(log_fare: float, reference: ReferenceStats) -> float | None:
    if reference.mad_log_fare <= 0:
        return None
    return 0.6745 * (log_fare - reference.median_log_fare) / reference.mad_log_fare


def check_outlier(obs: FareObservation, context: QualityContext) -> tuple[list[RuleResult], float | None, bool]:
    """Returns (results, robust_z, had_reference)."""
    if obs.fare.total_fare is None or obs.fare.total_fare <= 0 or obs.route_code is None or obs.lead_days is None:
        return [], None, False
    reference = context.reference_for(obs.route_code, obs.lead_days)
    if reference is None or reference.sample_size < MIN_REFERENCE_SAMPLE:
        return [], None, False
    z = robust_z_score(math.log(obs.fare.total_fare), reference)
    if z is None:
        return [], None, True
    if abs(z) > OUTLIER_Z_THRESHOLD:
        return [RuleResult(QualityStatus.OUTLIER, f"robust_z={z:.2f}")], z, True
    return [], z, True


# ------------------------------------------------------------ combinator


def assess(obs: FareObservation, context: QualityContext | None = None, *, now: datetime | None = None) -> QualityAssessment:
    context = context or QualityContext()
    results: list[RuleResult] = []
    results += check_required_fields(obs)
    results += check_route(obs)
    results += check_search_timestamp(obs, now=now)
    results += check_travel_date(obs)
    results += check_lead_time(obs)
    results += check_availability(obs)
    results += check_currency(obs)
    results += check_fare_value(obs)
    results += check_fare_components(obs)

    dedup_key = compute_dedup_key(obs)
    results += check_duplicate(dedup_key, context)

    robust_z: float | None = None
    had_reference = False
    if not any(r.status in (QualityStatus.REJECTED, QualityStatus.MISSING, QualityStatus.SOLD_OUT) for r in results):
        outlier_results, robust_z, had_reference = check_outlier(obs, context)
        results += outlier_results

    flags: list[str] = []
    if not obs.fare.components_complete and obs.fare.total_fare is not None:
        flags.append("components_unavailable")
    if not had_reference:
        flags.append("no_outlier_reference")

    if results:
        status = min((r.status for r in results), key=_SEVERITY.index)
    elif had_reference:
        status = QualityStatus.VALIDATED
    else:
        status = QualityStatus.PROVISIONAL

    reasons = [r.reason for r in results]
    if status == QualityStatus.PROVISIONAL:
        reasons.append("passed_all_rules;no_outlier_reference_yet")

    # A simple, explainable score: 1.0 for clean data, reduced per issue.
    score = 1.0
    if status not in (QualityStatus.VALIDATED, QualityStatus.PROVISIONAL):
        score = 0.0 if status in (QualityStatus.REJECTED, QualityStatus.MISSING) else 0.5
    elif status == QualityStatus.PROVISIONAL:
        score = 0.8
    if "components_unavailable" in flags and score > 0:
        score = round(score - 0.1, 2)

    return QualityAssessment(
        status=status,
        reasons=reasons,
        flags=flags,
        score=max(score, 0.0),
        dedup_key=dedup_key,
        robust_z=round(robust_z, 3) if robust_z is not None else None,
    )


def reference_from_log_fares(log_fares: list[float]) -> ReferenceStats | None:
    """Median/MAD summary of a sample of log fares (used by both live and backfill paths)."""
    if not log_fares:
        return None
    ordered = sorted(log_fares)
    median = _median(ordered)
    mad = _median(sorted(abs(x - median) for x in ordered))
    return ReferenceStats(median_log_fare=median, mad_log_fare=mad, sample_size=len(ordered))


def _median(ordered: list[float]) -> float:
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2
