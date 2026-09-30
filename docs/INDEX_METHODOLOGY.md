# Index Methodology

This document describes how the WrightWarp Airfare Price Index is calculated, as implemented in
`backend/app/index_engine/` (calculation version `index-engine/1.0`).

> **Data status.** No real airline or OTA source is currently cleared for collection, so every
> published value is computed from **SIMULATED** observations and labeled **DEMO**. The route
> weights are **DEMO** values, not DGCA traffic data. The methodology itself does not depend on
> where the data comes from, and it applies unchanged once real sources and official weights exist.

## 1. What is priced

| Dimension | Definition |
|---|---|
| Product | One-way domestic economy airfare, total payable price in INR (base fare + taxes + airport charges/UDF + mandatory fees). Optional ancillaries (baggage, seat, meal) are excluded. |
| Basket | 6 monitored routes: DEL-BOM, DEL-BLR, BOM-BLR, DEL-CCU, BLR-HYD, MAA-DEL (`app/core/routes.py`) |
| Booking windows | T+1, T+7, T+15, T+30, T+45 days before travel. Configurable with `BOOKING_WINDOWS`. |
| Price observation date | The IST calendar day the fare was seen. Index periods are built on this date, which is CPI practice: prices are attributed to the period in which they are observed. |
| Base period | Calendar year 2024 = 100 (`INDEX_BASE_YEAR`) |

## 2. From observations to cells

1. Each observation passes through the quality engine (see `DATA_PIPELINE.md`). Only observations
   with status `VALIDATED` or `PROVISIONAL`, and provenance `REAL` or `SIMULATED`, are eligible.
   `SYNTHETIC` test fixtures never enter the index.
2. A **cell** is one (observation day d, route r, booking window w, carrier a). Its price is the
   geometric mean of the eligible total fares in that cell:
   `ln p(d,r,w,a) = mean(ln fare)`.
3. An **item** is (route, window, carrier). The item's **base price** is the geometric mean of its
   daily cell prices over the base year:
   `ln p0(i) = mean over base-year days of ln p(d,i)`.

## 3. Elementary level: route relatives (Jevons)

For a period t (day, ISO week, or month), an item's period price is the geometric mean of its daily
cell prices in t. The route's price relative is the **Jevons** index over the route's *matched*
items, meaning items that have both a period price and a base price:

```
R(r,t) = exp( mean over matched items i of r [ ln p(t,i) - ln p0(i) ] )
```

- Items with no base-year price (for example, a carrier that entered the route later) are excluded
  and counted in `unmatched_items`. They cannot be compared with base, and chain-linking them in is
  listed as a future enhancement.
- The same construction gives **route × window** relatives, where the items are the carriers on one
  route in one window.
- The route's **base price level** is `P0(r) = exp(mean of ln p0(i) over the route's items)`.

Why Jevons at this level: no quantity information exists below route level. The geometric mean is
the standard elementary-aggregate formula in CPI practice (ILO/IMF CPI Manual). It also satisfies
the time-reversal and transitivity tests, and it is robust to one carrier's extreme price move.

## 4. Upper level: combining routes

Four formulas implement the same `IndexCalculator` interface (`calculators.py`) and are computed
side by side for every period:

| Formula | Expression over routes present in period t | Weights |
|---|---|---|
| **Laspeyres** (headline) | `Σ q0·P0·R / Σ q0·P0` | base-year quantities `q0` |
| Paasche | `Σ qt·P0·R / Σ qt·P0` (= `Σ qt·pt / Σ qt·p0`) | quantities for the period's year `qt` |
| Fisher | `sqrt(Laspeyres × Paasche)` | both |
| Jevons | `exp(mean ln R)` | none |

Index value = 100 × the aggregate relative.

- **Headline methodology: Laspeyres** over Jevons elementary aggregates. This is the fixed-basket
  structure used by most national CPIs, including India's, so the index can be read alongside CPI.
- Laspeyres, Paasche, and Fisher differ only through the weights. With the DEMO weights their spread
  is under one index point on average (see `BACKTEST_REPORT.md`).
- If a route has no data in a period, it drops out of that period and the remaining shares are
  re-normalised. `n_routes` on every point records how many routes contributed.
- The **booking-window index** for window w applies the same formula to the route × w relatives
  across routes.
- The **route index** is the elementary Jevons route relative itself (methodology
  `ELEMENTARY_JEVONS`).

## 5. Weights

`app/index_engine/weights.py` loads versioned JSON weight sets from `backend/app/reference_data/weights/`:

- Each set carries `version`, `label` (`DEMO` or `OFFICIAL`), `is_official`, `source`, `unit`, and
  quantities by year and route.
- Validation: every monitored route has a positive base-year quantity, no unknown routes, and a
  `DEMO` set can never claim `is_official`.
- Selection: an `OFFICIAL` set always wins over `DEMO`. `WEIGHTS_VERSION` pins a specific version.
- Every index run records the weight set's version, label, file, and SHA-256 checksum.

The shipped set `DEMO-2024.1` holds **illustrative** passenger magnitudes. To use official data, add
a file such as `route_weights.dgca-2024.json` with `"label": "OFFICIAL", "is_official": true`, a
`source` citing the DGCA table, and the base-year quantities. The engine needs no code changes.

## 6. Frequencies

| Frequency | Period key | Period price of an item |
|---|---|---|
| Daily | `YYYY-MM-DD` | the day's cell |
| Weekly | ISO week `YYYY-Www` | geometric mean of the week's daily cells |
| Monthly | `YYYY-MM` | geometric mean of the month's daily cells |

All frequencies are direct comparisons with the base year (fixed base, not chained), so a weekly or
monthly value is consistent with the daily values it summarises.

## 7. Reproducibility

Each computation writes an `index_runs` document with: run id, timestamp, calculation version,
base year, methodologies, booking windows, weighting metadata and checksum, cell and observation
counts (total, eligible, excluded, by quality status, by source), first and last observation date,
and the data label. Every series document references its run id. Readers only see a run after all
of its series are written (`index_meta.current`).

## 8. What is not claimed

- The index is **not validated** against official statistics. The backtest compares it with the
  simulator's ground truth, which is a recovery test, not a validation (see `BACKTEST_REPORT.md`).
- No **real-time** data is collected: the scheduled job collects from the simulated source once a day.
- The weights are **not DGCA** figures.
