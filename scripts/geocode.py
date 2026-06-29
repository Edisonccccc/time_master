#!/usr/bin/env python3
"""
geocode.py — resolve accurate coordinates for the seed venues (run later).

Part of the data-verification pass (DESIGN §4 / DATA_NOTES). Looks up each venue
by name + neighborhood and replaces the approximate seed lat/lng with the
geocoded one, marking the record `verified: true` and recording `geocode_source`.

Providers (both free, keyless, OSM-based):
  - **photon** (default) — photon.komoot.io. Permissive; good for a quick batch.
  - **nominatim** — nominatim.openstreetmap.org. Strict policy: it 403s generic
    clients, so set a REAL contact in USER_AGENT and keep to <=1 req/sec.

This is a one-off batch, not a runtime dependency — the app never calls it.
Network required (won't run in a sandbox without egress).

Usage:
  python3 scripts/geocode.py --dry-run            # preview (default provider: photon)
  python3 scripts/geocode.py                       # write data/nyc_venues.json in place
  python3 scripts/geocode.py --provider nominatim  # opt into Nominatim
  python3 scripts/geocode.py --only venue_001,venue_002
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(__file__)
DATA = os.path.abspath(os.path.join(HERE, "..", "data", "nyc_venues.json"))
# Set a real contact here if you use Nominatim (its policy requires it).
USER_AGENT = "EveningConcierge/0.1 (special-occasion dining concierge; dataset geocoding)"
NYC = (40.74, -73.99)       # bias results toward NYC
RATE = {"photon": 0.4, "nominatim": 1.1}   # nominatim demands <=1 req/sec
MAX_DRIFT_DEG = 0.03        # geocode this far from the seed -> flag, don't auto-write


def _query(venue: dict) -> str:
    return f'{venue["name"]}, {venue["neighborhood"]}, New York, NY, USA'


def _get(url: str) -> dict | list:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def geocode(q: str, provider: str) -> tuple[float, float] | None:
    if provider == "photon":
        qs = urllib.parse.urlencode({"q": q, "limit": 1,
                                     "lat": NYC[0], "lon": NYC[1]})
        feats = _get(f"https://photon.komoot.io/api/?{qs}").get("features", [])
        if not feats:
            return None
        lon, lat = feats[0]["geometry"]["coordinates"]     # GeoJSON is [lon, lat]
        return float(lat), float(lon)
    # nominatim
    qs = urllib.parse.urlencode({"q": q, "format": "json", "limit": 1,
                                 "countrycodes": "us"})
    data = _get(f"https://nominatim.openstreetmap.org/search?{qs}")
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--provider", choices=["photon", "nominatim"], default="photon")
    ap.add_argument("--only", default="", help="comma-separated venue ids")
    ap.add_argument("--force", action="store_true", help="re-geocode even if verified")
    args = ap.parse_args()
    only = {x for x in args.only.split(",") if x}
    rate = RATE[args.provider]

    venues = json.load(open(DATA, encoding="utf-8"))
    changed = matched = skipped = failed = 0
    print(f"provider={args.provider}  (dry-run={args.dry_run})\n")

    for v in venues:
        if only and v["id"] not in only:
            continue
        if v.get("verified") and not args.force:
            skipped += 1
            continue
        try:
            res = geocode(_query(v), args.provider)
        except Exception as e:                       # network/HTTP error -> skip, keep seed
            print(f"  ! {v['name']}: {e}", file=sys.stderr)
            failed += 1
            time.sleep(rate)
            continue
        time.sleep(rate)
        if not res:
            print(f"  ? {v['name']}: no match (kept seed coords)")
            failed += 1
            continue
        lat, lng = res
        drift = abs(lat - v["lat"]) + abs(lng - v["lng"])
        flag = "  ~ suspicious drift" if drift > MAX_DRIFT_DEG else ""
        matched += 1
        print(f"  ✓ {v['name']}: ({v['lat']:.4f},{v['lng']:.4f}) -> ({lat:.4f},{lng:.4f}){flag}")
        if not args.dry_run and not flag:            # don't auto-accept far jumps
            v["lat"], v["lng"] = round(lat, 5), round(lng, 5)
            v["verified"] = True
            v["geocode_source"] = args.provider
            changed += 1

    if not args.dry_run:
        json.dump(venues, open(DATA, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\nmatched={matched} written={changed} skipped(verified)={skipped} "
          f"failed/none={failed}  {'(dry-run, nothing written)' if args.dry_run else ''}")
    print("Note: records with large drift are flagged and NOT auto-written — "
          "review those by hand (the seed name may be ambiguous).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
