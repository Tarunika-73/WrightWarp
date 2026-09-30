# Ethical Collection Policy

WrightWarp collects only publicly accessible fare information, and only from sources that have
passed a documented compliance review.

## Rules enforced in code

- A source is dispatched to **only** if its registry entry (`backend/app/core/sources.py`) is
  `status=IMPLEMENTED` **and** `enabled=True`. Every other status (`PENDING_REVIEW`, `DISABLED`,
  `CONFIGURED`) returns `BLOCKED` before any network activity.
- The status is a code-reviewed decision. No API endpoint can enable a source or change its status.
- The API has no generic "scrape this URL" endpoint. Clients choose a registered `source_id`, and the
  server-side adapter decides what is accessed.
- A per-source rate limiter (`rate_limit_per_minute`, at most 6/min for airlines and 4/min for OTAs)
  enforces spacing with no burst allowance.
- Retries cover transient failures only (at most 3, exponential backoff). A compliance block or an
  auth error is never retried.
- An adapter that meets a CAPTCHA, a 403 on a disallowed path, or any other access control signals
  `blocked=True`. The run ends as `BLOCKED` and is not retried.
- No cookies, session tokens, or headers are stored. Raw observations hold parsed fare fields only.

## Never implemented

CAPTCHA solving, stealth or fingerprint-spoofing browser plugins, anti-bot evasion, proxy or IP
rotation, authentication bypass, session hijacking, rate-limit bypass, and collection behind a login.

## Current source status (review of 2026-09-29)

| Source | Status | Finding |
|---|---|---|
| ixigo, Cleartrip, EaseMyTrip | PENDING_REVIEW (not permitted) | robots.txt explicitly disallows flight-search result paths |
| SpiceJet | PENDING_REVIEW | robots.txt disallows `/api/v1` (the fare API) |
| Akasa Air | PENDING_REVIEW | robots.txt permissive, but Terms of Use could not be retrieved, so permission is unconfirmed |
| IndiGo, Air India, MakeMyTrip | PENDING_REVIEW | robots.txt fetch timed out; not reviewed |
| Air India Express, Yatra, Goibibo | PENDING_REVIEW | not yet reviewed |
| `DEMO_SIM` | IMPLEMENTED | market simulator; no network access; SIMULATED data |
| `MOCK` | IMPLEMENTED | deterministic test fixture; SYNTHETIC data; excluded from the index |

Because no real source is cleared, the deployed system runs on the simulator, and every output is
labeled DEMO.

## Onboarding a real source

1. Review robots.txt **and** the Terms of Use. Both must permit automated access to fare search.
   Record the evidence in `notes` and in `docs/architecture/source-adapters.md`.
2. Prefer an official API or data-sharing agreement (for example, through MoSPI/DGCA) over page
   collection.
3. Implement a `SourceAdapter` that returns parsed payloads and raises `CollectionException` with a
   specific error type. It must set `blocked=True` on any access-control response.
4. If a browser is required, use the `BrowserManager`/`PageManager` abstraction
   (`app/collection/browser.py`) and run it in a separate worker, not in the Vercel function (see
   `ARCHITECTURE.md`).
5. Only then set `status=IMPLEMENTED`, `enabled=True`, `data_provenance=REAL`, and add tests.
