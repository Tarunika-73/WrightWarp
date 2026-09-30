import math

import pytest

from app.index_engine.calculators import (
    CALCULATORS,
    DEFAULT_METHODOLOGY,
    ElementaryAggregate,
    FisherIndexCalculator,
    IndexCalculationError,
    JevonsIndexCalculator,
    LaspeyresIndexCalculator,
    PaascheIndexCalculator,
    WeightContext,
    get_calculator,
)

AGGS = [ElementaryAggregate("A", 1.10, 100.0), ElementaryAggregate("B", 0.95, 200.0)]
W = WeightContext(base_quantities={"A": 3.0, "B": 1.0}, current_quantities={"A": 1.0, "B": 3.0})


def test_jevons_is_unweighted_geometric_mean():
    assert JevonsIndexCalculator().calculate(AGGS) == pytest.approx(math.sqrt(1.10 * 0.95))


def test_laspeyres_uses_base_expenditure_shares():
    # expenditures q0*P0: A=300, B=200 -> shares 0.6/0.4
    assert LaspeyresIndexCalculator().calculate(AGGS, W) == pytest.approx(0.6 * 1.10 + 0.4 * 0.95)


def test_paasche_equals_sum_qt_pt_over_sum_qt_p0():
    pt = {"A": 110.0, "B": 190.0}
    expected = (1 * pt["A"] + 3 * pt["B"]) / (1 * 100 + 3 * 200)
    assert PaascheIndexCalculator().calculate(AGGS, W) == pytest.approx(expected)


def test_fisher_is_geometric_mean_of_laspeyres_and_paasche():
    l = LaspeyresIndexCalculator().calculate(AGGS, W)
    p = PaascheIndexCalculator().calculate(AGGS, W)
    assert FisherIndexCalculator().calculate(AGGS, W) == pytest.approx(math.sqrt(l * p))


def test_all_formulas_agree_when_prices_move_together():
    aggs = [ElementaryAggregate("A", 1.2, 100.0), ElementaryAggregate("B", 1.2, 300.0)]
    for calc in CALCULATORS.values():
        assert calc.calculate(aggs, W) == pytest.approx(1.2)


def test_base_period_value_is_one():
    aggs = [ElementaryAggregate("A", 1.0, 100.0), ElementaryAggregate("B", 1.0, 300.0)]
    for calc in CALCULATORS.values():
        assert calc.calculate(aggs, W) == pytest.approx(1.0)


def test_weighted_formulas_need_weights_for_every_route():
    with pytest.raises(IndexCalculationError):
        LaspeyresIndexCalculator().calculate([ElementaryAggregate("Z", 1.0, 100.0)], W)
    with pytest.raises(IndexCalculationError):
        LaspeyresIndexCalculator().calculate(AGGS, None)


def test_empty_and_invalid_inputs_rejected():
    with pytest.raises(IndexCalculationError):
        JevonsIndexCalculator().calculate([])
    with pytest.raises(IndexCalculationError):
        JevonsIndexCalculator().calculate([ElementaryAggregate("A", 0.0, 100.0)])


def test_registry_and_default():
    assert DEFAULT_METHODOLOGY == "LASPEYRES"
    assert set(CALCULATORS) == {"JEVONS", "LASPEYRES", "PAASCHE", "FISHER"}
    assert get_calculator("fisher").name == "FISHER"
    with pytest.raises(IndexCalculationError):
        get_calculator("carli")
