"""
availability.py — does a venue have a table for this date/time/party?

REALITY (DESIGN §5): OpenTable/Resy/Tock have no public booking API, and
scraping them is fragile + ToS-risky. So M4 ships a deterministic STUB behind a
small provider interface. Swap in a real provider later without touching the
rest of the pipeline.

The stub is deterministic per (venue, date, time, party) so results are stable
within a request and across reloads, but vary believably:
  - trophy tables ($$$$ + 2/3-star) usually "release on schedule" (book ~N days
    out) -> flagged, NOT bookable now (matches the out-of-v1 drop-watch note).
  - weekends, prime time, and big parties reduce availability.
  - phone_only / walk_in are handled honestly (call / no reservation).
If no date is given we don't pretend — status "not_checked", still bookable, with
a nudge to pick a date.

Status values: available | limited | released_on_schedule | unavailable |
               phone_only | walk_in | not_checked
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from typing import List, Optional

RELEASE_DAYS = 30  # trophy tables open this many days out

_BOOKABLE = {"available", "limited", "walk_in", "not_checked"}
_PRIME = {"18:30", "19:00", "19:30", "20:00", "20:30"}
_DINNER_SLOTS = ["17:00", "17:30", "18:00", "18:30", "19:00",
                 "19:30", "20:00", "20:30", "21:00", "21:30"]


def _r(*parts) -> float:
    h = hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _is_weekend(date: Optional[str]) -> Optional[bool]:
    if not date:
        return None
    try:
        d = _dt.date.fromisoformat(date)
        return d.weekday() >= 4  # Fri/Sat/Sun count as high-demand
    except ValueError:
        return None


def _nearby_slots(time: Optional[str], r: float, n: int) -> List[str]:
    t = time if time in _DINNER_SLOTS else "19:30"
    i = _DINNER_SLOTS.index(t)
    order = sorted(range(len(_DINNER_SLOTS)), key=lambda j: abs(j - i))
    picks = sorted(order[: max(n + 1, 3)], key=lambda j: j)
    # drop one pseudo-randomly so it's not always symmetric
    if len(picks) > n:
        picks.pop(int(r * len(picks)) % len(picks))
    return [_DINNER_SLOTS[j] for j in picks[:n]]


def _trophy(v: dict) -> bool:
    return v["price_tier"] == 4 and v.get("michelin") in ("2_star", "3_star")


def check(v: dict, date: Optional[str], time: Optional[str], party: int) -> dict:
    plat = v["booking"]["platform"]
    if plat == "walk_in":
        return {"status": "walk_in", "bookable": True, "slots": [],
                "note": "No reservations — walk in."}
    if plat == "phone_only":
        return {"status": "phone_only", "bookable": False, "slots": [],
                "note": "Reservations by phone — call to book."}
    if not date:
        return {"status": "not_checked", "bookable": True, "slots": [],
                "note": "Pick a date to check live availability."}

    r = _r(v["id"], date, time or "", party)

    if _trophy(v) and r > 0.25:
        return {"status": "released_on_schedule", "bookable": False, "slots": [],
                "note": f"Books ~{RELEASE_DAYS} days out on "
                        f"{plat.title()}; reserve right when it opens."}

    p = 0.85
    p -= {4: 0.35, 3: 0.15}.get(v["price_tier"], 0.0)
    p -= {"1_star": 0.12, "2_star": 0.25, "3_star": 0.45}.get(v.get("michelin"), 0.0)
    if _is_weekend(date):
        p -= 0.15
    if (time or "19:30") in _PRIME:
        p -= 0.10
    if party > 4:
        p -= 0.10
    if party > 6:
        p -= 0.15
    p = max(0.05, min(0.95, p))

    if r < p:
        return {"status": "available", "bookable": True,
                "slots": _nearby_slots(time, r, 3),
                "note": ""}
    if r < p + 0.12:
        return {"status": "limited", "bookable": True,
                "slots": _nearby_slots(time, r, 1),
                "note": "Limited — only an off-peak slot left."}
    return {"status": "unavailable", "bookable": False, "slots": [],
            "note": "Fully booked for that date/time."}


def is_bookable(status: str) -> bool:
    return status in _BOOKABLE
