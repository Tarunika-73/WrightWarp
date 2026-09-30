# Demo Guide (SIH judging walkthrough, about 8 minutes)

Everything shown is **DEMO DATA**: simulated fares, DEMO weights. The dashboard says so on every
page. Say so out loud too.

## 1. Overview (1 min)
- Point to the yellow **DEMO DATA · SIMULATED** banner and explain why: every real airline/OTA source
  is `PENDING_REVIEW`, and we do not bypass robots.txt or ToS.
- KPIs: current index (base 2024 = 100), day/7-day/month/year changes, observations and the share
  that passed quality checks, active sources, last collection time.
- Index trend: switch Daily / Weekly / Monthly.
- Booking-window effect: T+1 is far dearer than T+45, which is the core consumer insight.
- Largest increases and decreases by route; the quality breakdown.

## 2. Pick a route, a travel date, and a booking window (2 min): the end-to-end flow
1. **Route Analysis**: choose `DEL-BOM`.
2. In *Fare for a travel date, by booking window*, pick a travel date. The table answers "what did
   this trip cost when bought T+1 / T+7 / T+15 / T+30 / T+45 days ahead?" with cheapest, median, and
   highest valid fares, and valid-vs-seen counts.
3. The daily chart shows the same route per booking window over 90 days.
4. *All routes compared* places the six route indices on one base-100 axis.

## 3. Show the pipeline behind a number (2 min)
- **Data Quality**: every observation gets one status, and none is deleted. The rules table covers
  duplicates, outliers (robust z-score), sold-out, missing, component mismatch, and more.
- **API & Methodology → Tracing a value**: open
  `/api/v1/index/trace?route=DEL-BOM&observation_date=<recent date>` to show index point → cells →
  individual observations, each with quality status and `included_in_index`. Then open
  `/api/v1/quotes/<id>/provenance` to show the raw payload, its SHA-256 hash, and the collection run.
- **Source Monitoring**: the compliance registry (robots.txt findings) and recent collection runs.

## 4. Index methodology (1.5 min)
- **Airfare Index**: switch methodology (Laspeyres headline / Paasche / Fisher / Jevons) and frequency.
- The methodology comparison chart shows the formulas moving together. The spread is driven by the
  (DEMO) weights.

## 5. Backtesting (1 min)
- Explain the **NOT A VALIDATION** banner: the computed index is compared with the simulator's own
  ground truth, which tests how well the pipeline recovers a known index from noisy, gappy,
  corrupted data.
- Monthly MAPE is about 0.13% on simulated data. Daily error is larger (thin samples per day).
- Name the next step: load an official CPI airfare series into `reference_series` to backtest
  against it.

## 6. Operations (0.5 min)
- **System Health**: API, DB, the last scheduled job (Vercel Cron, daily 06:00 IST), and the current
  run's reproducibility record (weights checksum, calculation version).
- `/docs` for the full OpenAPI.

## Resetting the demo data
```bash
cd backend
.venv/Scripts/python.exe -m app.cli seed-demo      # replaces DEMO_SIM data only; ~3-4 minutes
```
