"""Route weighting: versioned, provenance-carrying weight sets.

Upper-level index formulas (Laspeyres, Paasche, Fisher) need route
quantities - ideally DGCA domestic origin-destination passenger traffic.
Weights are *data*, loaded from JSON files in ``app/reference_data/weights``,
never constants in code, so official figures can be dropped in later
without touching the index engine:

    {
      "version": "DGCA-2024.1",
      "label": "OFFICIAL",            # or "DEMO"
      "is_official": true,
      "source": "DGCA domestic traffic data, <table/URL>",
      "unit": "passengers",
      "quantities": {"2024": {"DEL-BOM": 1234567, ...}, "2025": {...}}
    }

Selection: an ``OFFICIAL`` set always wins over a ``DEMO`` one; the
``WEIGHTS_VERSION`` environment variable pins a specific version.

The weight set shipped with this repository is labeled DEMO. Its numbers
are illustrative, hand-picked magnitudes, NOT DGCA figures. Every index
built on it carries ``weighting.label = "DEMO"``.
"""
import hashlib
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.routes import list_route_codes

WEIGHTS_DIR = Path(__file__).resolve().parents[1] / "reference_data" / "weights"


class WeightValidationError(ValueError):
    pass


@dataclass(frozen=True)
class WeightSet:
    version: str
    label: str
    is_official: bool
    source: str
    description: str
    unit: str
    quantities: dict[int, dict[str, float]]  # year -> route -> quantity
    file_name: str
    checksum: str

    def quantities_for(self, year: int, *, fallback_year: int) -> tuple[dict[str, float], int]:
        """Quantities for ``year``; if absent, the latest year <= ``year``, else ``fallback_year``."""
        if year in self.quantities:
            return self.quantities[year], year
        earlier = [y for y in self.quantities if y <= year]
        chosen = max(earlier) if earlier else fallback_year
        return self.quantities[chosen], chosen

    def shares(self, year: int) -> dict[str, float]:
        q, _ = self.quantities_for(year, fallback_year=min(self.quantities))
        total = sum(q.values())
        return {route: value / total for route, value in q.items()}

    def metadata(self) -> dict:
        return {
            "version": self.version,
            "label": self.label,
            "is_official": self.is_official,
            "source": self.source,
            "unit": self.unit,
            "file": self.file_name,
            "checksum_sha256": self.checksum,
            "years": sorted(self.quantities),
        }


def validate_weight_payload(payload: dict, *, base_year: int, file_name: str = "<memory>") -> None:
    for key in ("version", "label", "source", "quantities"):
        if key not in payload:
            raise WeightValidationError(f"{file_name}: missing '{key}'")
    label = payload["label"]
    if label not in ("DEMO", "OFFICIAL"):
        raise WeightValidationError(f"{file_name}: label must be DEMO or OFFICIAL")
    if label == "OFFICIAL" and not payload.get("is_official"):
        raise WeightValidationError(f"{file_name}: OFFICIAL label requires is_official=true")
    if label == "DEMO" and payload.get("is_official"):
        raise WeightValidationError(f"{file_name}: a DEMO weight set can never be is_official")
    known = set(list_route_codes())
    quantities = payload["quantities"]
    if str(base_year) not in quantities:
        raise WeightValidationError(f"{file_name}: no quantities for base year {base_year}")
    for year, routes in quantities.items():
        if not str(year).isdigit():
            raise WeightValidationError(f"{file_name}: bad year {year!r}")
        unknown = set(routes) - known
        if unknown:
            raise WeightValidationError(f"{file_name}: {year}: routes not in master data: {sorted(unknown)}")
        for route, value in routes.items():
            if not isinstance(value, (int, float)) or value <= 0:
                raise WeightValidationError(f"{file_name}: {year}/{route}: quantity must be positive")
    missing = known - set(quantities[str(base_year)])
    if missing:
        raise WeightValidationError(f"{file_name}: base year {base_year} lacks routes {sorted(missing)}")


def parse_weight_set(payload: dict, *, base_year: int, file_name: str, raw_bytes: bytes) -> WeightSet:
    validate_weight_payload(payload, base_year=base_year, file_name=file_name)
    return WeightSet(
        version=payload["version"],
        label=payload["label"],
        is_official=bool(payload.get("is_official", False)),
        source=payload["source"],
        description=payload.get("description", ""),
        unit=payload.get("unit", ""),
        quantities={int(y): {r: float(v) for r, v in routes.items()} for y, routes in payload["quantities"].items()},
        file_name=file_name,
        checksum=hashlib.sha256(raw_bytes).hexdigest(),
    )


@lru_cache(maxsize=4)
def load_weight_sets(base_year: int, directory: str = str(WEIGHTS_DIR)) -> tuple[WeightSet, ...]:
    sets = []
    for path in sorted(Path(directory).glob("*.json")):
        raw = path.read_bytes()
        sets.append(parse_weight_set(json.loads(raw), base_year=base_year, file_name=path.name, raw_bytes=raw))
    if not sets:
        raise WeightValidationError(f"no weight sets found in {directory}")
    return tuple(sets)


def active_weight_set(base_year: int) -> WeightSet:
    sets = load_weight_sets(base_year)
    pinned = os.environ.get("WEIGHTS_VERSION")
    if pinned:
        for s in sets:
            if s.version == pinned:
                return s
        raise WeightValidationError(f"WEIGHTS_VERSION={pinned} not found")
    official = [s for s in sets if s.is_official]
    return sorted(official or sets, key=lambda s: s.version)[-1]
