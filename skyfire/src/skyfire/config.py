from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Spot:
    name: str
    lat: float
    lon: float
    elevation_m: float


@dataclass
class City:
    key: str
    name: str
    lat: float
    lon: float
    timezone: str
    spots: list[Spot] = field(default_factory=list)


def load_cities(path: Path) -> dict[str, City]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    cities: dict[str, City] = {}
    for key, c in data["cities"].items():
        spots = [Spot(**s) for s in c.get("spots", [])]
        cities[key] = City(
            key=key, name=c["name"], lat=c["lat"], lon=c["lon"],
            timezone=c["timezone"], spots=spots,
        )
    return cities
