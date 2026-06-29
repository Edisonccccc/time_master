"""geo.py — distance + walking-time between venues (for walkable evenings)."""

from __future__ import annotations

import math

_EARTH_M = 6_371_000.0
_WALK_M_PER_MIN = 80.0  # ~4.8 km/h, allowing for streets/lights


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return _EARTH_M * 2 * math.asin(math.sqrt(a))


def walk_minutes(a: dict, b: dict) -> int:
    d = haversine_m(a["lat"], a["lng"], b["lat"], b["lng"])
    return round(d / _WALK_M_PER_MIN)
