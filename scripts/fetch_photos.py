#!/usr/bin/env python3
"""
fetch_photos.py — download official venue photos via the Google Places API.

Fills each venue's `photo_url` (+ `photo_credit`) so the cards show a real photo
of the room/food. Uses Google Places **Text Search** to find the place, then the
**Place Photo** endpoint to download one provider photo into frontend/photos/.

Requires an API key with the Places API enabled + billing:
    export GOOGLE_MAPS_API_KEY=...

⚠️ LICENSING — read before running:
- Google Places photos are provided by Google/third parties. Google's terms
  generally DISALLOW caching Place photos for more than ~30 days and require
  showing the returned attribution. This script downloads copies for display
  convenience; that's fine for a personal/demo project, but for anything public
  or long-lived prefer a server-side proxy that fetches on demand and shows the
  attribution, and refresh periodically. We store the attribution in
  `photo_credit` and render it on the card.
- The app never calls this at runtime; it's a one-off batch you run yourself.

Usage:
    python3 scripts/fetch_photos.py --dry-run          # preview matches
    python3 scripts/fetch_photos.py                     # download + write
    python3 scripts/fetch_photos.py --only venue_050 --force
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(__file__)
DATA = os.path.abspath(os.path.join(HERE, "..", "data", "nyc_venues.json"))
PHOTOS = os.path.abspath(os.path.join(HERE, "..", "frontend", "photos"))
KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
MAXW = 800
RATE = 0.3


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def _strip(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


def find_photo(venue: dict):
    """Return (photo_reference, credit) or (None, None)."""
    q = urllib.parse.urlencode({
        "query": f'{venue["name"]} {venue["neighborhood"]} New York NY',
        "key": KEY})
    data = _get_json(f"https://maps.googleapis.com/maps/api/place/textsearch/json?{q}")
    results = data.get("results") or []
    if not results:
        return None, None
    photos = results[0].get("photos") or []
    if not photos:
        return None, None
    ref = photos[0]["photo_reference"]
    attrs = photos[0].get("html_attributions") or []
    credit = _strip(attrs[0]) if attrs else "via Google"
    return ref, credit


def download_photo(ref: str, dest: str) -> bool:
    q = urllib.parse.urlencode({"maxwidth": MAXW, "photo_reference": ref, "key": KEY})
    url = f"https://maps.googleapis.com/maps/api/place/photo?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "EveningConcierge/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:      # follows redirect to the image
        blob = r.read()
    if len(blob) < 1000:
        return False
    with open(dest, "wb") as f:
        f.write(blob)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="stop after N downloads")
    args = ap.parse_args()
    if not KEY:
        print("Set GOOGLE_MAPS_API_KEY first.", file=sys.stderr)
        return 2
    os.makedirs(PHOTOS, exist_ok=True)
    only = {x for x in args.only.split(",") if x}
    venues = json.load(open(DATA, encoding="utf-8"))
    got = skipped = failed = 0

    for v in venues:
        if only and v["id"] not in only:
            continue
        if v.get("photo_url") and not args.force:
            skipped += 1
            continue
        if args.limit and got >= args.limit:
            break
        try:
            ref, credit = find_photo(v)
            time.sleep(RATE)
        except Exception as e:
            print(f"  ! {v['name']}: {e}", file=sys.stderr); failed += 1; continue
        if not ref:
            print(f"  ? {v['name']}: no photo found"); failed += 1; continue
        print(f"  ✓ {v['name']}  (credit: {credit})")
        if args.dry_run:
            got += 1
            continue
        dest = os.path.join(PHOTOS, f"{v['id']}.jpg")
        try:
            ok = download_photo(ref, dest)
            time.sleep(RATE)
        except Exception as e:
            print(f"  ! {v['name']} download: {e}", file=sys.stderr); failed += 1; continue
        if ok:
            v["photo_url"] = f"/photos/{v['id']}.jpg"
            v["photo_credit"] = credit
            got += 1
        else:
            failed += 1

    if not args.dry_run:
        json.dump(venues, open(DATA, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\ngot={got} skipped(existing)={skipped} failed/none={failed} "
          f"{'(dry-run)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
