# WrightWarp Phase 2 — Source Adapters & Compliance Review

## The adapter pattern

Every source (airline or OTA) is a class implementing `SourceAdapter`
(`backend/app/collection/adapters/base.py`):

```python
class SourceAdapter(ABC):
    @property
    @abstractmethod
    def source_id(self) -> str: ...

    @abstractmethod
    async def search(self, request: CollectionRequest) -> AdapterSearchOutcome: ...
```

An adapter's only job is "given a request, go find fares and return raw
findings" - it never touches the database (that's `CollectionRepository`)
and never decides whether it's allowed to run (that's
`CollectionService`, checking `app.core.sources` before ever calling the
adapter). `AdapterRegistry` (`app/collection/adapters/registry.py`) maps
a `source_id` to its adapter instance; only sources present in that
registry can ever be dispatched to, and only `MockSourceAdapter` is
registered today.

## Registration vs. implementation vs. compliance clearance

Three independent things, easy to conflate:

1. **Registered** (`app/core/sources.py`) - the source is known to the
   system (name, type, compliance metadata). Every source in the SIH26056
   problem statement's list is registered.
2. **Implemented** (`SourceStatus.IMPLEMENTED`) - a `SourceAdapter` class
   exists for it. Only `MOCK` is implemented in Phase 2.
3. **Enabled** (`SourceDefinition.enabled`) - `CollectionService` refuses
   to dispatch to a source unless it is *both* `IMPLEMENTED` and
   `enabled`. Every real source is registered with `enabled=False`.

Registering a source never implies its scraper exists, and no source
reaches `IMPLEMENTED` without the compliance review below.

## Compliance review (Phase 2, 2026-09-29)

Before any real source can move off `PENDING_REVIEW`, its robots.txt and
Terms of Service must be inspected and the decision documented here -
never assumed, never skipped. Fetches below were made by requesting the
plain-text `robots.txt` file each site publishes for exactly this
purpose; no page requiring a login or JavaScript execution was accessed,
and no search/booking flow was exercised.

| Source | robots.txt result | Automated fare-search collection permitted? |
|---|---|---|
| ixigo (`IXIGO`) | `Disallow: /flights/search`, `/flights/review`, `/search/result/` | **No** - explicitly disallowed |
| Cleartrip (`CLEARTRIP`) | `Disallow: /flights/search*` | **No** - explicitly disallowed |
| EaseMyTrip (`EASEMYTRIP`) | `Disallow: /flight-search/listing*`, `/cheap_flights/`, `/cheap-flights/` | **No** - explicitly disallowed |
| SpiceJet (`SG`) | `Disallow: /api/v1`, `/public/`, `/externalBooking` | **No** - disallows the site's programmatic fare API |
| Akasa Air (`QP`) | No `Disallow` rules (sitemaps only) | **Not cleared** - robots.txt alone is permissive, but the Terms of Use fetch returned HTTP 504 (timeout) and could not be reviewed. A permissive robots.txt does not clear a source on its own; ToS review must also pass. |
| IndiGo (`6E`), Air India (`AI`), MakeMyTrip (`MAKEMYTRIP`) | robots.txt fetch timed out during review | **Not reviewed** - review incomplete |
| Air India Express (`IX`), Yatra (`YATRA`), Goibibo (`GOIBIBO`) | Not attempted in this pass | **Not reviewed** |

**Decision: no source is cleared for real implementation in Phase 2.**
Every entry above stays `PENDING_REVIEW` in `app/core/sources.py`, with
the specific finding (or the reason review is incomplete) recorded in
that source's `notes` field. `MockSourceAdapter` is used for all pipeline
testing and development instead - exactly the fallback the Phase 2 spec
calls for when a source does not clear review.

This is expected to change over time only through the same process: fetch
robots.txt, fetch/read the Terms of Service, record the finding here and
in `app/core/sources.py`, and only then write an adapter - never the
other way around.

## What "PENDING_REVIEW" does at runtime

`CollectionService._check_compliance` refuses to run any request whose
source is not `IMPLEMENTED` *and* `enabled`, returning
`CollectionOutcome.BLOCKED` with `CollectionErrorType.COMPLIANCE_BLOCKED`
and the source's `notes` as `detail`. This is enforced in code, not just
in configuration - there is no request parameter that bypasses it, and
`POST /api/v1/collections` never accepts an arbitrary URL (see
`app/api/collections.py`): the client selects a `source_id`, and the
registry/adapter pairing controls what is actually accessed.

## What Phase 2 explicitly does not do

No CAPTCHA bypass, no anti-bot stealth/fingerprint evasion, no
unauthorized proxy/IP rotation, no authentication bypass, and no
rate-limit bypass exist anywhere in this codebase, and none are planned.
`app/collection/browser.py` establishes a Playwright launch/context/page
abstraction for a *future* real adapter, but launches nothing
automatically and is not wired into any adapter yet.
