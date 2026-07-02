"""
main.py — FastAPI app for the dining concierge (M2).

POST /plan : given a brief, filter dinner venues by HARD constraints, then rank
the survivors with the deterministic occasion rubric. No LLM and no live
availability yet (M3 / M4). Evening assembly (pre/post) also comes in M3 — for
now we return ranked dinner anchors with transparent reasoning.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, assemble, data, rubric

_FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
_PHOTOS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "photos"))
os.makedirs(_PHOTOS, exist_ok=True)

app = FastAPI(title="Dining Concierge", version="0.2.0")

# Local dev: allow the single-file frontend to call us from file:// or localhost.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
# Serve downloaded venue photos (populated by scripts/fetch_photos.py).
app.mount("/photos", StaticFiles(directory=_PHOTOS), name="photos")


# --- Request / response models ---------------------------------------------
class Brief(BaseModel):
    occasion: str = Field(..., description="one of rubric.OCCASIONS")
    party_size: int = Field(2, ge=1, le=20)
    budget_max_tier: Optional[int] = Field(None, ge=1, le=4,
                                           description="max price tier 1..4")
    neighborhoods: List[str] = Field(default_factory=list,
                                     description="empty = anywhere in NYC")
    cuisine_likes: List[str] = Field(default_factory=list)
    cuisine_avoids: List[str] = Field(default_factory=list)
    dietary: List[str] = Field(default_factory=list,
                               description="vegetarian | vegan | gluten_free")
    vibe: float = Field(0.0, ge=-1.0, le=1.0,
                        description="-1 chill .. +1 special")
    adjust: Dict[str, float] = Field(
        default_factory=dict,
        description="signed weight deltas per feature (one-click corrections), "
                    "e.g. {'formality': -1.5, 'noise': 1.5}")
    limit: int = Field(10, ge=1, le=50)
    use_llm: Optional[bool] = Field(
        None, description="None=auto (LLM if ANTHROPIC_API_KEY set), false=template only")
    # date/time accepted; time seeds the timeline. Availability filtering = M4.
    date: Optional[str] = None
    time: Optional[str] = None


# --- Hard-constraint filter -------------------------------------------------
def _passes_hard_filters(v: dict, b: Brief) -> bool:
    if b.budget_max_tier is not None and v["price_tier"] > b.budget_max_tier:
        return False
    if b.neighborhoods and v["neighborhood"] not in b.neighborhoods:
        return False
    if b.cuisine_avoids:
        avoid = {c.lower() for c in b.cuisine_avoids}
        if avoid & {c.lower() for c in v["cuisine"]}:
            return False
    for req in b.dietary:
        if not v.get("dietary", {}).get(req, False):
            return False
    return True


def _public_venue(v: dict) -> dict:
    """Trim to what a client card needs."""
    return {
        "id": v["id"], "name": v["name"], "neighborhood": v["neighborhood"],
        "cuisine": v["cuisine"], "price_tier": v["price_tier"],
        "michelin": v["michelin"], "booking_platform": v["booking"]["platform"],
        "requires_deposit": v["booking"]["requires_deposit"],
        "notes": v.get("notes", ""), "verified": v.get("verified", False),
    }


@app.get("/")
def root() -> dict:
    return {
        "service": "Dining Concierge",
        "version": app.version,
        "try": {
            "app": "/app",
            "docs": "/docs",
            "health": "/health",
            "plan": "POST /plan  (body: see /docs)",
        },
    }


@app.get("/app", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(os.path.abspath(_FRONTEND))


@app.get("/health")
def health() -> dict:
    return {"ok": True, "venues": len(data.all_venues()),
            "occasions": list(rubric.OCCASIONS),
            "agent": agent.available()}


class LiveReq(BaseModel):
    name: str
    neighborhood: str = ""
    date: Optional[str] = None
    time: Optional[str] = None
    party_size: int = 2


@app.post("/availability/live")
def availability_live(req: LiveReq) -> dict:
    """Runtime agent: web-search a venue's current hours/policy/status.
    Returns {enabled: false} when no ANTHROPIC_API_KEY is configured."""
    if not agent.available():
        return {"enabled": False,
                "note": "Live check needs ANTHROPIC_API_KEY on the server."}
    res = agent.live_availability(req.name, req.neighborhood, req.date,
                                  req.time, req.party_size)
    return {"enabled": True, **res} if res else {
        "enabled": True, "summary": None,
        "note": "Couldn't complete a live check just now."}


@app.post("/plan")
def plan(brief: Brief) -> dict:
    """M3: full evening plans (dinner + walkable pre/post) + a backup."""
    if brief.occasion not in rubric.WEIGHTS:
        return {"error": f"unknown occasion '{brief.occasion}'",
                "valid_occasions": list(rubric.OCCASIONS)}

    result = assemble.assemble(brief)
    return {
        "brief": brief.model_dump(),
        "occasion_profile": rubric.WEIGHTS[brief.occasion],
        **result,
        "_note": "M3: assembled evening plans. Live availability = M4; "
                 "deep-link booking = M5; data verified:false (see DATA_NOTES).",
    }


@app.post("/rank-dinners")
def rank_dinners(brief: Brief) -> dict:
    """Debug view: just the ranked dinner anchors (the M2 behavior)."""
    if brief.occasion not in rubric.WEIGHTS:
        return {"error": f"unknown occasion '{brief.occasion}'",
                "valid_occasions": list(rubric.OCCASIONS)}
    dinners = data.venues_by_role("dinner")
    eligible = [v for v in dinners if _passes_hard_filters(v, brief)]
    scored = []
    for v in eligible:
        s = rubric.score_venue(v, brief.occasion, vibe=brief.vibe,
                               cuisine_likes=brief.cuisine_likes)
        scored.append({**_public_venue(v), **s})
    scored.sort(key=lambda x: x["fit_score"], reverse=True)
    return {"considered": len(dinners), "eligible_after_filters": len(eligible),
            "results": scored[: brief.limit]}
