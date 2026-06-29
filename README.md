# Evening — special-occasion dining concierge

Plan a whole special-occasion night in NYC — pre-dinner drinks, the dinner anchor,
and a dessert or walk after — matched to the occasion (first date, anniversary,
proposal, business…), with transparent reasoning, a walkable route map, an
assisted booking handoff, and a downloadable invitation card.

> Design & architecture live in [`docs/DESIGN.md`](docs/DESIGN.md);
> project memory in [`CLAUDE.md`](CLAUDE.md).

## Stack
- **Backend:** Python + FastAPI. Deterministic occasion rubric scoring, walkable
  evening assembly, stubbed availability, assisted booking links. Optional
  LLM-written reasoning when `ANTHROPIC_API_KEY` is set.
- **Frontend:** one self-contained `frontend/index.html` (no build step). Dark/
  light themes, guided tour, illustrated route map, Leaflet+Carto map in detail,
  one-click vibe corrections, invitation generator. Served at `/app`.
- **Data:** `data/nyc_venues.json` — 104 curated NYC venues (seed; `verified:false`
  until geocoded — see `data/DATA_NOTES.md`).

## Run locally
```bash
pip install -r requirements.txt
python3 -m uvicorn backend.main:app --reload
# open http://127.0.0.1:8000/app   ·   API docs at /docs   ·   health at /health
python3 -m pytest tests/ -q        # 17 tests
```

## Endpoints
- `GET /app` — the web app
- `POST /plan` — brief → evening plans (+ availability, booking, unavailable gems)
- `POST /rank-dinners` — debug: ranked dinner anchors only
- `GET /health` — liveness + venue count

## Deploy to Render
This repo includes a [`render.yaml`](render.yaml) blueprint.

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, point it at this repo. It reads `render.yaml`
   and creates a free Python web service:
   - build: `pip install -r requirements.txt`
   - start: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - health check: `/health`
3. (Optional) In the service's **Environment**, add `ANTHROPIC_API_KEY` to enable
   LLM-written plan reasoning. Without it, the app uses deterministic wording.
4. Once live, the app is at `https://<your-service>.onrender.com/app`.

The detail-view map loads tiles from Carto over the network; everything else
(including the illustrated route map on cards) works offline.

## Data verification (optional, later)
`scripts/geocode.py` resolves accurate coordinates (default provider: Photon,
keyless) and flips `verified:true`:
```bash
python3 scripts/geocode.py --dry-run   # preview
python3 scripts/geocode.py             # write
```

## Notes
- Booking is **assisted, human-confirms** — links open the platform pre-filled;
  you review and confirm. Nothing is booked and no money moves automatically.
- Venue facts (Michelin status, booking platform, coordinates) are a seed and
  should be verified before real use.
