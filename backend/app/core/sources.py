"""Source registry.

This is a static configuration registry, not a database table: there is
no per-source runtime state (rate-limit counters, last-run timestamps)
that would justify one, and it lets us disable or flag a source purely
by editing this file - no application code changes, no migration.

Every entry carries the ethical-scraping flags required by SIH26056 up
front (``robots_url``, ``terms_url``, ``requires_robots_review``,
``requires_terms_review``, ``rate_limit_per_minute``) so that no adapter
can be wired in without also declaring how it will respect robots.txt,
each source's Terms of Service, and a reasonable request rate.

``status`` (``SourceStatus``) is deliberately separate from ``enabled``:
registering a source here is just bookkeeping (it lets the API list what
exists and what compliance state it is in) and never implies a scraper
exists. Only a source whose ``status`` is ``IMPLEMENTED`` *and* whose
``enabled`` is ``True`` may be dispatched to by ``CollectionService`` -
see ``docs/architecture/source-adapters.md`` for the reviewed compliance
decision behind every entry below (as of 2026-09-29, every real source is
``PENDING_REVIEW``; only ``MOCK`` is ``IMPLEMENTED``).
"""
from dataclasses import dataclass

from app.core.enums import SourceStatus, SourceType


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    display_name: str
    source_type: SourceType
    enabled: bool
    status: SourceStatus
    robots_url: str | None
    terms_url: str | None
    rate_limit_per_minute: float
    requires_browser: bool
    requires_terms_review: bool
    requires_robots_review: bool
    notes: str
    adapter_name: str | None = None


AIRLINE_SOURCES: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        source_id="6E",
        display_name="IndiGo",
        source_type=SourceType.AIRLINE,
        enabled=False,
        status=SourceStatus.PENDING_REVIEW,
        robots_url="https://www.goindigo.in/robots.txt",
        terms_url="https://www.goindigo.in/legal/terms-of-use.html",
        rate_limit_per_minute=6,
        requires_browser=True,
        requires_terms_review=True,
        requires_robots_review=True,
        notes="robots.txt fetch timed out during Phase 2 review; ToS not yet reviewed. Compliance review incomplete.",
    ),
    SourceDefinition(
        source_id="AI",
        display_name="Air India",
        source_type=SourceType.AIRLINE,
        enabled=False,
        status=SourceStatus.PENDING_REVIEW,
        robots_url="https://www.airindia.com/robots.txt",
        terms_url="https://www.airindia.com/in/en/legal/terms-of-use.html",
        rate_limit_per_minute=6,
        requires_browser=True,
        requires_terms_review=True,
        requires_robots_review=True,
        notes="robots.txt fetch timed out during Phase 2 review; ToS not yet reviewed. Compliance review incomplete.",
    ),
    SourceDefinition(
        source_id="IX",
        display_name="Air India Express",
        source_type=SourceType.AIRLINE,
        enabled=False,
        status=SourceStatus.PENDING_REVIEW,
        robots_url="https://www.airindiaexpress.com/robots.txt",
        terms_url="https://www.airindiaexpress.com/terms-of-use",
        rate_limit_per_minute=6,
        requires_browser=True,
        requires_terms_review=True,
        requires_robots_review=True,
        notes="Not yet reviewed in Phase 2.",
    ),
    SourceDefinition(
        source_id="QP",
        display_name="Akasa Air",
        source_type=SourceType.AIRLINE,
        enabled=False,
        status=SourceStatus.PENDING_REVIEW,
        robots_url="https://www.akasaair.com/robots.txt",
        terms_url="https://www.akasaair.com/terms-and-conditions",
        rate_limit_per_minute=6,
        requires_browser=True,
        requires_terms_review=True,
        requires_robots_review=True,
        notes=(
            "robots.txt fetched 2026-09-29: no Disallow rules (sitemaps only). "
            "Terms-of-use fetch timed out (HTTP 504), so automated-access permission "
            "could not be confirmed. A permissive robots.txt alone does not clear a "
            "source - ToS review must also pass. Stays PENDING_REVIEW until it does."
        ),
    ),
    SourceDefinition(
        source_id="SG",
        display_name="SpiceJet",
        source_type=SourceType.AIRLINE,
        enabled=False,
        status=SourceStatus.PENDING_REVIEW,
        robots_url="https://www.spicejet.com/robots.txt",
        terms_url="https://www.spicejet.com/TermsOfUse.aspx",
        rate_limit_per_minute=6,
        requires_browser=True,
        requires_terms_review=True,
        requires_robots_review=True,
        notes=(
            "robots.txt fetched 2026-09-29: Disallow: /api/v1, /public/, "
            "/externalBooking - covers the site's programmatic fare API. "
            "Automated fare collection not confirmed permitted."
        ),
    ),
)

# OTA sources are registered for future configuration only. No adapter
# exists for any of them; every entry reviewed so far in Phase 2 was
# found to disallow automated fare-search collection (see
# docs/architecture/source-adapters.md for the fetched robots.txt
# evidence). Scraping any of these remains explicitly out of scope.
OTA_SOURCES: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        source_id="MAKEMYTRIP",
        display_name="MakeMyTrip",
        source_type=SourceType.OTA,
        enabled=False,
        status=SourceStatus.PENDING_REVIEW,
        robots_url="https://www.makemytrip.com/robots.txt",
        terms_url="https://www.makemytrip.com/legal/terms_of_use.html",
        rate_limit_per_minute=4,
        requires_browser=True,
        requires_terms_review=True,
        requires_robots_review=True,
        notes="robots.txt fetch timed out during Phase 2 review. Not reviewed.",
    ),
    SourceDefinition(
        source_id="YATRA",
        display_name="Yatra",
        source_type=SourceType.OTA,
        enabled=False,
        status=SourceStatus.PENDING_REVIEW,
        robots_url="https://www.yatra.com/robots.txt",
        terms_url="https://www.yatra.com/terms-of-use",
        rate_limit_per_minute=4,
        requires_browser=True,
        requires_terms_review=True,
        requires_robots_review=True,
        notes="Not yet reviewed in Phase 2.",
    ),
    SourceDefinition(
        source_id="CLEARTRIP",
        display_name="Cleartrip",
        source_type=SourceType.OTA,
        enabled=False,
        status=SourceStatus.PENDING_REVIEW,
        robots_url="https://www.cleartrip.com/robots.txt",
        terms_url="https://www.cleartrip.com/terms",
        rate_limit_per_minute=4,
        requires_browser=True,
        requires_terms_review=True,
        requires_robots_review=True,
        notes=(
            "robots.txt fetched 2026-09-29: Disallow: /flights/search* - explicitly "
            "blocks automated access to flight-search results. Collection not permitted."
        ),
    ),
    SourceDefinition(
        source_id="IXIGO",
        display_name="ixigo",
        source_type=SourceType.OTA,
        enabled=False,
        status=SourceStatus.PENDING_REVIEW,
        robots_url="https://www.ixigo.com/robots.txt",
        terms_url="https://www.ixigo.com/terms-of-use",
        rate_limit_per_minute=4,
        requires_browser=True,
        requires_terms_review=True,
        requires_robots_review=True,
        notes=(
            "robots.txt fetched 2026-09-29: Disallow: /flights/search, "
            "/flights/review, /search/result/ - explicitly blocks automated access "
            "to flight-search results. Collection not permitted."
        ),
    ),
    SourceDefinition(
        source_id="GOIBIBO",
        display_name="Goibibo",
        source_type=SourceType.OTA,
        enabled=False,
        status=SourceStatus.PENDING_REVIEW,
        robots_url="https://www.goibibo.com/robots.txt",
        terms_url="https://www.goibibo.com/terms-conditions/",
        rate_limit_per_minute=4,
        requires_browser=True,
        requires_terms_review=True,
        requires_robots_review=True,
        notes="Not yet reviewed in Phase 2.",
    ),
    SourceDefinition(
        source_id="EASEMYTRIP",
        display_name="EaseMyTrip",
        source_type=SourceType.OTA,
        enabled=False,
        status=SourceStatus.PENDING_REVIEW,
        robots_url="https://www.easemytrip.com/robots.txt",
        terms_url="https://www.easemytrip.com/terms-conditions.html",
        rate_limit_per_minute=4,
        requires_browser=True,
        requires_terms_review=True,
        requires_robots_review=True,
        notes=(
            "robots.txt fetched 2026-09-29: Disallow: /flight-search/listing*, "
            "/cheap_flights/, /cheap-flights/ - blocks automated access to "
            "flight-search listing pages. Collection not permitted."
        ),
    ),
)

# The deterministic, synthetic-data source used to exercise the entire
# Phase 2 pipeline end-to-end without touching any live website. This is
# the only source whose status is IMPLEMENTED.
MOCK_SOURCES: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        source_id="MOCK",
        display_name="Mock Source (synthetic, pipeline testing only)",
        source_type=SourceType.AIRLINE,
        enabled=True,
        status=SourceStatus.IMPLEMENTED,
        robots_url=None,
        terms_url=None,
        rate_limit_per_minute=600,
        requires_browser=False,
        requires_terms_review=False,
        requires_robots_review=False,
        notes="Synthetic adapter. Never returns real fares; every observation is tagged DataProvenance.SYNTHETIC.",
        adapter_name="mock",
    ),
)

ALL_SOURCES: tuple[SourceDefinition, ...] = AIRLINE_SOURCES + OTA_SOURCES + MOCK_SOURCES

_BY_ID = {s.source_id: s for s in ALL_SOURCES}


def get_source(source_id: str) -> SourceDefinition:
    try:
        return _BY_ID[source_id]
    except KeyError as exc:
        raise ValueError(f"Unknown source_id: {source_id}") from exc


def list_sources() -> tuple[SourceDefinition, ...]:
    return ALL_SOURCES
