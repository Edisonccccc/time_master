"""data.py — load and cache the seed venue dataset."""

from __future__ import annotations

import json
import os
from functools import lru_cache

_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "nyc_venues.json")


@lru_cache(maxsize=1)
def all_venues() -> list[dict]:
    with open(os.path.abspath(_DATA_PATH), encoding="utf-8") as f:
        return json.load(f)


def venues_by_role(role: str) -> list[dict]:
    return [v for v in all_venues() if role in v["role"]]
