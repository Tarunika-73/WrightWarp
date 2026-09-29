import pytest
from pydantic import ValidationError

from app.schemas.route import RouteCreate


def _route(**overrides):
    payload = dict(origin="DEL", destination="BOM", route_code="DEL-BOM")
    payload.update(overrides)
    return payload


def test_valid_route_is_accepted():
    route = RouteCreate(**_route())
    assert route.route_code == "DEL-BOM"
    assert route.origin == "DEL"
    assert route.destination == "BOM"


def test_lowercase_iata_codes_are_uppercased():
    route = RouteCreate(origin="del", destination="bom", route_code="DEL-BOM")
    assert route.origin == "DEL"
    assert route.destination == "BOM"


@pytest.mark.parametrize("code", ["delbom", "DEL_BOM", "DEL-BOMX", "DELBOM", "DEL-bom", "123-456"])
def test_malformed_route_code_rejected(code):
    with pytest.raises(ValidationError):
        RouteCreate(**_route(route_code=code))


def test_route_code_same_origin_destination_rejected():
    with pytest.raises(ValidationError):
        RouteCreate(origin="DEL", destination="DEL", route_code="DEL-DEL")


def test_route_code_not_matching_origin_destination_rejected():
    with pytest.raises(ValidationError):
        RouteCreate(origin="DEL", destination="BOM", route_code="DEL-BLR")
