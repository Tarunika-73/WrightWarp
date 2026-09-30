"""Route master-data endpoints."""
from fastapi import APIRouter, Depends
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.routes import get_airport, get_route, list_routes
from app.db.bson_utils import datetime_to_date
from app.index_engine.weights import active_weight_set

router = APIRouter(prefix="/routes", tags=["routes"])


def _route_payload(route, shares: dict[str, float], weight_meta: dict) -> dict:
    origin, destination = get_airport(route.origin), get_airport(route.destination)
    return {
        "route_code": route.route_code,
        "origin": {"iata_code": route.origin, "city": origin.city, "name": origin.name, "state": origin.state},
        "destination": {"iata_code": route.destination, "city": destination.city, "name": destination.name, "state": destination.state},
        "weight_share": round(shares.get(route.route_code, 0.0), 6),
        "weighting_version": weight_meta["version"],
        "weighting_label": weight_meta["label"],
    }


@router.get("", summary="Monitored routes with airport details and (labelled) index weights")
async def list_monitored_routes(db: AsyncDatabase = Depends(get_db)):
    settings = get_settings()
    weights = active_weight_set(settings.index_base_year)
    shares = weights.shares(settings.index_base_year)
    stats = {
        d["_id"]: d
        for d in await (
            await db["daily_cells"].aggregate(
                [{"$group": {"_id": "$route", "n_obs": {"$sum": "$n_obs"}, "first": {"$min": "$date"}, "last": {"$max": "$date"}}}]
            )
        ).to_list()
    }
    out = []
    for route in list_routes():
        payload = _route_payload(route, shares, weights.metadata())
        s = stats.get(route.route_code)
        payload["valid_observations"] = s["n_obs"] if s else 0
        payload["first_observation_date"] = datetime_to_date(s["first"]) if s else None
        payload["last_observation_date"] = datetime_to_date(s["last"]) if s else None
        out.append(payload)
    return out


@router.get("/{route_code}", summary="One monitored route")
async def get_monitored_route(route_code: str):
    route = get_route(route_code)
    if route is None:
        raise NotFoundError(f"Route {route_code!r} is not a monitored route")
    settings = get_settings()
    weights = active_weight_set(settings.index_base_year)
    return _route_payload(route, weights.shares(settings.index_base_year), weights.metadata())
