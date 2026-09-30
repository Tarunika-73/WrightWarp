"""Upper-level index formulas behind one interface.

Two-stage structure, as in CPI compilation:

1. **Elementary level** (``app.index_engine.engine``): for each route (or
   route x booking window), the price relative against the base period is
   a Jevons index - the geometric mean of matched item relatives, where an
   item is one carrier x booking window on that route. No weights exist
   below route level, and the geometric mean is the standard choice there.

2. **Upper level** (this module): route relatives are combined into one
   index. Every formula implements ``IndexCalculator`` so they can be
   computed side by side and compared; none is hard-wired.

Notation per route r in period t: ``R_r`` price relative (base = 1),
``P0_r`` base-period price level (INR, geometric mean), ``q0_r`` / ``qt_r``
base / current-period quantities from the active weight set.

* Jevons:     prod(R_r) ** (1/n)                        (unweighted)
* Laspeyres:  sum(q0 * P0 * R) / sum(q0 * P0)           (base-period expenditure shares)
* Paasche:    sum(qt * P0 * R) / sum(qt * P0)           (= sum(qt*pt) / sum(qt*p0))
* Fisher:     sqrt(Laspeyres * Paasche)

Only routes present in the period take part; their shares are
re-normalised over what is present (documented in INDEX_METHODOLOGY.md).
"""
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass


class IndexCalculationError(ValueError):
    pass


@dataclass(frozen=True)
class ElementaryAggregate:
    key: str  # route code (weights are route-level)
    relative: float  # price relative vs base, base = 1.0
    base_price: float  # geometric-mean base-period price, INR
    n_items: int = 0
    n_obs: int = 0


@dataclass(frozen=True)
class WeightContext:
    base_quantities: dict[str, float]
    current_quantities: dict[str, float]


class IndexCalculator(ABC):
    name: str
    label: str
    description: str
    requires_weights: bool

    @abstractmethod
    def calculate(self, aggregates: list[ElementaryAggregate], weights: WeightContext | None) -> float:
        """Return the aggregate price relative (base = 1.0)."""

    def _check(self, aggregates: list[ElementaryAggregate], weights: WeightContext | None) -> None:
        if not aggregates:
            raise IndexCalculationError(f"{self.name}: no elementary aggregates")
        for agg in aggregates:
            if not (agg.relative > 0 and math.isfinite(agg.relative)):
                raise IndexCalculationError(f"{self.name}: non-positive relative for {agg.key}")
        if self.requires_weights and weights is None:
            raise IndexCalculationError(f"{self.name}: requires route weights")


def _weighted_arithmetic(aggregates: list[ElementaryAggregate], quantities: dict[str, float], name: str) -> float:
    numerator = 0.0
    denominator = 0.0
    for agg in aggregates:
        q = quantities.get(agg.key)
        if q is None:
            raise IndexCalculationError(f"{name}: no weight for {agg.key}")
        expenditure = q * agg.base_price
        numerator += expenditure * agg.relative
        denominator += expenditure
    if denominator <= 0:
        raise IndexCalculationError(f"{name}: zero total weight")
    return numerator / denominator


class JevonsIndexCalculator(IndexCalculator):
    name = "JEVONS"
    label = "Jevons (unweighted geometric)"
    description = "Unweighted geometric mean of route price relatives."
    requires_weights = False

    def calculate(self, aggregates, weights=None):
        self._check(aggregates, weights)
        return math.exp(sum(math.log(a.relative) for a in aggregates) / len(aggregates))


class LaspeyresIndexCalculator(IndexCalculator):
    name = "LASPEYRES"
    label = "Laspeyres (base-period weights)"
    description = "Route relatives weighted by base-period expenditure shares (q0 x P0). CPI-standard fixed basket."
    requires_weights = True

    def calculate(self, aggregates, weights):
        self._check(aggregates, weights)
        return _weighted_arithmetic(aggregates, weights.base_quantities, self.name)


class PaascheIndexCalculator(IndexCalculator):
    name = "PAASCHE"
    label = "Paasche (current-period weights)"
    description = "Route relatives weighted by current-period quantities valued at base prices (qt x P0)."
    requires_weights = True

    def calculate(self, aggregates, weights):
        self._check(aggregates, weights)
        return _weighted_arithmetic(aggregates, weights.current_quantities, self.name)


class FisherIndexCalculator(IndexCalculator):
    name = "FISHER"
    label = "Fisher (ideal)"
    description = "Geometric mean of Laspeyres and Paasche."
    requires_weights = True

    def calculate(self, aggregates, weights):
        self._check(aggregates, weights)
        laspeyres = LaspeyresIndexCalculator().calculate(aggregates, weights)
        paasche = PaascheIndexCalculator().calculate(aggregates, weights)
        return math.sqrt(laspeyres * paasche)


CALCULATORS: dict[str, IndexCalculator] = {
    c.name: c
    for c in (LaspeyresIndexCalculator(), JevonsIndexCalculator(), PaascheIndexCalculator(), FisherIndexCalculator())
}

# Headline methodology: Laspeyres at the upper level over Jevons elementary
# aggregates - the structure most national CPIs (including India's) use.
DEFAULT_METHODOLOGY = "LASPEYRES"


def get_calculator(name: str) -> IndexCalculator:
    try:
        return CALCULATORS[name.upper()]
    except KeyError as exc:
        raise IndexCalculationError(f"unknown methodology {name!r}; choose from {sorted(CALCULATORS)}") from exc
