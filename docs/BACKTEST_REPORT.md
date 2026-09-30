# Backtest Report

> **DEMO DATA - NOT OFFICIAL.** Every observation behind these numbers came from the
> WrightWarp market simulator, and the reference series is the simulator's own ground truth.
> The results measure how well the pipeline *recovers a known index* from noisy, gappy,
> partly corrupted observations. They are **not** a validation against official statistics.

- Backtest id: `4a1704d7245344abb1741c4e1f90bdd1` (index run `ca0830f36b1f4f45b7d1db4e582f5d13`)
- Generated: 2026-09-30 07:50 UTC
- Base year: 2024 = 100. Base-year periods are excluded from the error metrics.
- Headline methodology: LASPEYRES
- Observations: 50355 total, 47919 index-eligible, 2436 excluded by the quality engine
- Observation days: 2024-01-01 .. 2026-09-29
- Weighting: DEMO-2024.1 (DEMO)

## Reference: DEMO DATA - simulator ground truth, NOT OFFICIAL

Latent price process of the demo market simulator. Measures how accurately the pipeline recovers a known index from noisy, gappy, partly corrupted observations. This is NOT a comparison with official statistics.

### Overall index by methodology

| Methodology | Frequency | Periods | MAE (pts) | RMSE (pts) | MAPE % | Bias (pts) | Max abs err | Corr | Direction agreement % |
|---|---|---|---|---|---|---|---|---|---|
| LASPEYRES | daily | 379 | 0.513 | 0.647 | 0.461 | -0.034 | 2.214 | 0.997 | 87.6 |
| LASPEYRES | weekly | 91 | 0.266 | 0.348 | 0.240 | -0.036 | 1.192 | 0.999 | 98.9 |
| LASPEYRES | monthly | 21 | 0.143 | 0.173 | 0.128 | -0.042 | 0.367 | 1.000 | 95.0 |
| JEVONS | daily | 379 | 0.461 | 0.583 | 0.416 | 0.007 | 1.734 | 0.997 | 89.2 |
| JEVONS | weekly | 91 | 0.248 | 0.320 | 0.223 | 0.004 | 1.002 | 0.999 | 95.6 |
| JEVONS | monthly | 21 | 0.135 | 0.168 | 0.121 | -0.008 | 0.352 | 1.000 | 100.0 |
| PAASCHE | daily | 379 | 0.513 | 0.648 | 0.460 | -0.029 | 2.250 | 0.997 | 87.8 |
| PAASCHE | weekly | 91 | 0.266 | 0.349 | 0.239 | -0.031 | 1.219 | 0.999 | 97.8 |
| PAASCHE | monthly | 21 | 0.141 | 0.171 | 0.126 | -0.037 | 0.343 | 1.000 | 95.0 |
| FISHER | daily | 379 | 0.513 | 0.647 | 0.460 | -0.031 | 2.232 | 0.997 | 87.8 |
| FISHER | weekly | 91 | 0.266 | 0.348 | 0.239 | -0.034 | 1.205 | 0.999 | 97.8 |
| FISHER | monthly | 21 | 0.142 | 0.172 | 0.127 | -0.039 | 0.355 | 1.000 | 95.0 |

### Route-level (elementary Jevons) accuracy

| Route | Frequency | MAE | RMSE | MAPE % | Corr |
|---|---|---|---|---|---|
| DEL-BOM | weekly | 0.661 | 0.858 | 0.609 | 0.997 |
| DEL-BOM | monthly | 0.454 | 0.605 | 0.418 | 0.998 |
| DEL-BLR | weekly | 0.627 | 0.798 | 0.549 | 0.997 |
| DEL-BLR | monthly | 0.306 | 0.372 | 0.274 | 0.999 |
| BOM-BLR | weekly | 0.620 | 0.783 | 0.554 | 0.996 |
| BOM-BLR | monthly | 0.365 | 0.421 | 0.330 | 0.999 |
| DEL-CCU | weekly | 0.670 | 0.888 | 0.580 | 0.996 |
| DEL-CCU | monthly | 0.400 | 0.449 | 0.351 | 0.999 |
| BLR-HYD | weekly | 0.633 | 0.861 | 0.583 | 0.996 |
| BLR-HYD | monthly | 0.457 | 0.545 | 0.427 | 0.998 |
| MAA-DEL | weekly | 0.712 | 0.868 | 0.671 | 0.997 |
| MAA-DEL | monthly | 0.354 | 0.426 | 0.338 | 0.999 |

### Booking-window indices (monthly, headline methodology)

| Window | MAE | RMSE | MAPE % | Corr |
|---|---|---|---|---|
| T+1 | 0.420 | 0.506 | 0.378 | 0.998 |
| T+7 | 0.313 | 0.366 | 0.282 | 0.999 |
| T+15 | 0.424 | 0.501 | 0.383 | 0.999 |
| T+30 | 0.344 | 0.404 | 0.312 | 0.998 |
| T+45 | 0.354 | 0.442 | 0.317 | 0.999 |

### How far apart the formulas are

| Frequency | Mean spread (pts) | Max spread (pts) | Latest period | Latest values |
|---|---|---|---|---|
| daily | 1.153 | 4.582 | 2026-09-29 | LASPEYRES 121.657, JEVONS 120.057, PAASCHE 121.745, FISHER 121.701 |
| weekly | 0.971 | 3.483 | 2026-W40 | LASPEYRES 121.171, JEVONS 119.898, PAASCHE 121.298, FISHER 121.235 |
| monthly | 0.782 | 2.316 | 2026-09 | LASPEYRES 117.322, JEVONS 115.105, PAASCHE 117.421, FISHER 117.371 |

## Interpretation limits

- The simulator's noise model is simple (log-normal noise, AR(1) shocks, fixed seasonal bumps). Real
  fare dynamics (fare buckets, flash sales, capacity shocks) are harsher, so real-data errors will be larger.
- No official CPI airfare series has been loaded, so no statement about agreement with official
  statistics can be made. Load one into the `reference_series` collection to backtest against it.
- Route weights are DEMO values, not DGCA traffic.
