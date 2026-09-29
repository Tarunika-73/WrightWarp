# WrightWarp Index Methodology

**Status: NOT IMPLEMENTED YET.**

This document is a placeholder for Phase 3+. No index formula, weighting
scheme, or aggregation logic exists in the codebase as of Phase 1.

## Planned direction (subject to change, not yet built)

- Multiple candidate formulas: Laspeyres, Paasche, Fisher, Jevons —
  computed side by side so they can be compared rather than committing to
  one prematurely.
- Route weighting sourced from official DGCA/MoSPI market-share data
  where available; `routes.weight` stays `NULL` until such data is
  supplied. No invented weight will ever be presented as an official
  figure.
- Backtesting against at least 30 days of publicly available DGCA/
  reference data before any index value is described as validated.
- Every published index value will be labeled with the provenance
  (`REAL` / `SYNTHETIC` / `SIMULATED`) and quality (`RAW` / `VALIDATED` /
  `PROVISIONAL` / ...) of the observations that fed it — see
  `docs/architecture/data_model.md`.

Nothing in this file should be read as a description of current
behavior.
