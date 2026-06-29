"""
booking.py — assisted, human-confirms booking handoff (DESIGN §5).

We never book server-side or move money. For a chosen venue we produce a URL the
user opens in their own browser, landing as close to "confirm" as the platform
allows. They review and confirm themselves.

Precedence:
  1. venue.booking.url_template — exact pre-filled reservation URL (set once a
     venue is verified). Placeholders: {date} {time} {party} {datetime}.
  2. otherwise a pre-filled platform SEARCH URL (date/time/party where supported)
     — honest interim handoff until templates are filled in.
  3. phone_only / walk_in are surfaced honestly (no fake reservation link).

`kind`: reserve | search | call | walk_in   (drives the button label + caveat).
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

RESY_CITY = "new-york-ny"


def _datetime(date: Optional[str], time: Optional[str]) -> Optional[str]:
    if not date:
        return None
    return f"{date}T{time or '19:30'}"


def _search_url(platform: str, name: str, date: Optional[str],
                time: Optional[str], party: int) -> str:
    q = quote(name)
    dt = _datetime(date, time)
    if platform == "opentable":
        u = f"https://www.opentable.com/s?term={q}&covers={party}"
        return u + (f"&dateTime={dt}" if dt else "")
    if platform == "resy":
        u = f"https://resy.com/cities/{RESY_CITY}?query={q}&seats={party}"
        return u + (f"&date={date}" if date else "")
    if platform == "tock":
        return f"https://www.exploretock.com/search?query={q}"
    # fallback: a plain web search
    return f"https://www.google.com/search?q={q}+reservation"


def for_venue(venue: dict, date: Optional[str], time: Optional[str],
              party: int) -> dict:
    """venue: a dict with name, booking_platform, optional url_template."""
    platform = venue.get("booking_platform")
    name = venue["name"]

    if platform == "walk_in":
        return {"kind": "walk_in", "platform": platform, "url": None,
                "label": "Walk-in — no reservation"}
    if platform == "phone_only":
        return {"kind": "call", "platform": platform,
                "url": f"https://www.google.com/search?q={quote(name)}+reservations+phone",
                "label": "Find the number to call"}

    tmpl = venue.get("url_template")
    if tmpl:
        url = tmpl.format(date=date or "", time=time or "",
                          party=party, datetime=_datetime(date, time) or "")
        return {"kind": "reserve", "platform": platform, "url": url,
                "label": f"Reserve on {platform.title()}"}

    return {"kind": "search", "platform": platform,
            "url": _search_url(platform, name, date, time, party),
            "label": f"Find on {platform.title()}"}
