# CLAUDE.md — Special-Occasion Dining Concierge

> Project memory for AI tools and humans. Read this first, then `docs/`.

## What this is

An agentic web app that helps a user **find, plan, and book** restaurants for
special occasions (first date, anniversary, proposal, business dinner, etc.),
with a focus on the higher end — Michelin, omakase, notable NYC spots.

The core unit is not a single restaurant but a **full evening plan**:
optional pre-dinner drinks → dinner (the anchor) → optional post-dinner
dessert/walk, all walkable from each other, with transparent reasoning for
*why* each piece fits the occasion.

## Why it should win

The differentiator is **transparent, occasion-aware reasoning**. The app shows
the user the rubric it used and explains in plain language why each recommendation
fits their occasion — so the user trusts and "buys" the plan rather than being
handed an opaque list.

## Scope (v1)

- **City:** New York City only. Architecture stays city-agnostic so other
  cities can be added later.
- **Booking:** Assisted, human-confirms. The app never moves money or
  auto-confirms. It hands the user off to the booking platform one click from
  confirm (see `docs/DESIGN.md §5`).
- **Hosting:** Build and test **locally first**, deploy to Render later.

## Stack

- **Backend:** Python + FastAPI. Holds the LLM reasoning/orchestration, the
  curated dataset, and availability lookups. Keeps API keys off the client.
- **Frontend:** Single HTML/JS app (start as one file). Screens: intake →
  reasoning/loading → ranked evening plans → plan detail with deep-links.
- **Data:** Curated seed dataset of **104 NYC venues** across price/vibe tiers,
  pre-tagged on the rubric axes (see `docs/DESIGN.md §4`).

## Current status

- **Phase:** M1–M5 complete. Full flow (plan → availability → booking) at `/app`.
- **Done:**
  - `data/nyc_venues.json` — 104 NYC venues (68 dinner / 19 drinks / 8 dessert /
    9 walk) via `scripts/build_dataset.py`. All `verified:false` — check before M4
    (see `data/DATA_NOTES.md`).
  - `backend/` FastAPI app. `POST /plan` → 2–3 assembled **evening plans**
    (dinner + walkable pre-drinks + post dessert/walk) + a backup, each with
    timeline, est. cost, vibe arc, and plain-language reasoning. `POST /rank-dinners`
    (debug ranking), `GET /health`. 10 passing tests.
  - `backend/rubric.py` deterministic scoring; `assemble.py` walkable assembly
    (`geo.py` haversine); `reasoning.py` template prose, auto-upgrades to LLM if
    `ANTHROPIC_API_KEY` is set (`use_llm` overrides; `source` reported in output).
  - `frontend/index.html` — single-file app, served at `/app`. Dark/light theme
    toggle (Fraunces+Inter), occasion-first progressive intake, itinerary cards
    with a generated SVG **route mini-map** (pre→dinner→post pins + dashed walk
    path, projected from venue lat/lng) + vibe arc, detail modal
    (map/timeline/booking/.ics), one-click vibe corrections (→ `brief.adjust`).
    Needs `lat`/`lng` on plan legs (added to `_pub`).
  - Detail view also shows an interactive **Leaflet + Carto** map (keyless; Dark
    Matter/Positron by theme) with numbered markers + route; falls back to the SVG
    map if the CDN is unreachable. Cards stay offline; detail map needs network.
  - `scripts/geocode.py` — geocoding batch (default Photon, keyless; Nominatim
    opt-in) to fix coords + set `verified:true` (run later, network required).
  - **Invitation generator**: "Invite" button on each card + a big CTA in the
    expanded detail view open an overlay that builds an elegant framed invitation
    (cheers header, occasion title, date, per-stop bullets with neighborhood ·
    cuisine · price and little stop cartoons, optional to/from) as client-side
    SVG; download as SVG or PNG (`inviteSVG`/`inviteArt`/`downloadInvite`). No deps.
  - **First-run guided tour** (`startTour`/`TOUR`): animated spotlight coach-marks
    over occasion → when → budget → where → plan; auto-runs once (localStorage
    `evening-onboarded`), replayable via the "? Tour" button. Plus one-time pulse
    hints to open a plan (`maybeCardHint`) and create the invitation (`maybeInviteHint`).
  - `backend/availability.py` — provider interface + deterministic stub
    (status/slots/bookable; trophy flagged "released on schedule"). Wired into
    assembly: plans use bookable dinners; unbookable high-fit spots → `unavailable_gems`.
  - `backend/booking.py` — assisted handoff URL per venue (`url_template` or
    date/time/party pre-filled platform search); attached to every plan leg.
    Client-side `.ics` calendar export in the frontend. 16 tests.
  - **Photos**: `photo_url`/`photo_credit` on venues (null until fetched); cards +
    detail show the photo, else fall back to the illustrated map. `scripts/fetch_photos.py`
    downloads official Google Places photos → `frontend/photos/` (served at `/photos`);
    needs `GOOGLE_MAPS_API_KEY`. Licensing caveat in `data/DATA_NOTES.md`.
  - **Runtime availability agent**: `backend/agent.py` uses the Anthropic API's
    web_search tool to look up a venue's current hours/policy/status on demand.
    `POST /availability/live` (per opened plan, off the hot path); `/health.agent`
    reports if enabled. Needs `ANTHROPIC_API_KEY`; falls back silently to the stub.
    Can't read exact live table inventory (no public API) — an informed, cited read.
- **Next (M6):** deploy to Render (push done via user's machine). Plus the data
  pass: run `geocode.py` + `fetch_photos.py`, verify facts, fill `url_template`s.

## Run
```
pip install -r requirements.txt
python3 -m uvicorn backend.main:app --reload
# open http://127.0.0.1:8000/app   (UI)   ·   /docs (API)   ·   /health
python3 -m pytest tests/ -q
```

## Conventions

- Reasoning lives server-side, never in the browser.
- Prove the experience on the **static seed dataset** before touching live
  availability or any scraping.
- Two booking modes considered but only one in v1: *instant-bookable* (in).
  *Drop-watch* for trophy reservations is **out of v1** (can't be assisted-confirm).

## Docs

Full design lives in **`docs/DESIGN.md`** (single file, six sections):
Overview · Architecture · Occasion Rubric · Data & Dataset · Booking · Build Plan.

Dataset provenance + verification status: **`data/DATA_NOTES.md`**.

## Layout
```
CLAUDE.md
docs/DESIGN.md
data/nyc_venues.json   data/DATA_NOTES.md
scripts/build_dataset.py
```
