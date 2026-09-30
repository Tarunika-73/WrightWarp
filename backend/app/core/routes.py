"""Route and airport master data.

Static configuration, like the source registry: the monitored route set
is a methodological decision (it defines the index basket), so it
changes by code review, not by an API call. ``RouteRepository.sync``
mirrors it into the ``routes``/``airports`` collections at startup so
it is queryable through the same repository pattern as everything else.

Add a route by appending to ``MONITORED_ROUTES`` (and its airports to
``AIRPORTS``). Route weights do NOT live here - they are versioned,
provenance-carrying data (see ``app.index_engine.weights``).
"""
from dataclasses import dataclass

from app.core.validators import validate_iata_code


@dataclass(frozen=True)
class AirportDefinition:
    iata_code: str
    name: str
    city: str
    state: str


@dataclass(frozen=True)
class RouteDefinition:
    origin: str
    destination: str
    # Carriers the demo market simulator offers on this route. Has no
    # effect on real collection; a real adapter reports whichever
    # carriers the source actually lists.
    demo_carriers: tuple[str, ...]

    @property
    def route_code(self) -> str:
        return f"{self.origin}-{self.destination}"


AIRPORTS: tuple[AirportDefinition, ...] = (
    AirportDefinition("DEL", "Indira Gandhi International Airport", "Delhi", "Delhi"),
    AirportDefinition("BOM", "Chhatrapati Shivaji Maharaj International Airport", "Mumbai", "Maharashtra"),
    AirportDefinition("BLR", "Kempegowda International Airport", "Bengaluru", "Karnataka"),
    AirportDefinition("CCU", "Netaji Subhas Chandra Bose International Airport", "Kolkata", "West Bengal"),
    AirportDefinition("HYD", "Rajiv Gandhi International Airport", "Hyderabad", "Telangana"),
    AirportDefinition("MAA", "Chennai International Airport", "Chennai", "Tamil Nadu"),
)

MONITORED_ROUTES: tuple[RouteDefinition, ...] = (
    RouteDefinition("DEL", "BOM", ("6E", "AI", "QP")),
    RouteDefinition("DEL", "BLR", ("6E", "AI", "IX")),
    RouteDefinition("BOM", "BLR", ("6E", "AI", "QP")),
    RouteDefinition("DEL", "CCU", ("6E", "AI", "SG")),
    RouteDefinition("BLR", "HYD", ("6E", "IX", "QP")),
    RouteDefinition("MAA", "DEL", ("6E", "AI", "SG")),
)

_AIRPORTS_BY_CODE = {a.iata_code: a for a in AIRPORTS}
_ROUTES_BY_CODE = {r.route_code: r for r in MONITORED_ROUTES}


def _validate_master_data() -> None:
    for route in MONITORED_ROUTES:
        validate_iata_code(route.origin)
        validate_iata_code(route.destination)
        if route.origin == route.destination:
            raise ValueError(f"route {route.route_code}: origin and destination must differ")
        for code in (route.origin, route.destination):
            if code not in _AIRPORTS_BY_CODE:
                raise ValueError(f"route {route.route_code}: airport {code} missing from AIRPORTS")
    if len(_ROUTES_BY_CODE) != len(MONITORED_ROUTES):
        raise ValueError("duplicate route in MONITORED_ROUTES")


_validate_master_data()


def parse_route_code(route_code: str) -> tuple[str, str]:
    """``"del-bom"`` -> ``("DEL", "BOM")``. Raises ``ValueError`` on bad shape."""
    parts = route_code.strip().upper().split("-")
    if len(parts) != 2:
        raise ValueError(f"route must look like XXX-YYY, got {route_code!r}")
    origin, destination = (validate_iata_code(p) for p in parts)
    if origin == destination:
        raise ValueError("origin and destination must differ")
    return origin, destination


def get_route(route_code: str) -> RouteDefinition | None:
    try:
        origin, destination = parse_route_code(route_code)
    except ValueError:
        return None
    return _ROUTES_BY_CODE.get(f"{origin}-{destination}")


def is_monitored_route(origin: str, destination: str) -> bool:
    return f"{origin}-{destination}" in _ROUTES_BY_CODE


def get_airport(iata_code: str) -> AirportDefinition | None:
    return _AIRPORTS_BY_CODE.get(iata_code.upper())


def list_routes() -> tuple[RouteDefinition, ...]:
    return MONITORED_ROUTES


def list_route_codes() -> tuple[str, ...]:
    return tuple(r.route_code for r in MONITORED_ROUTES)
