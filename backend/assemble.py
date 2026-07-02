"""
assemble.py — turn ranked dinners into walkable EVENING PLANS (DESIGN §4).

Pipeline (all deterministic; reasoning prose may upgrade to LLM):
  1. Rank eligible dinners with the occasion rubric.
  2. For each top dinner, attach the best walkable pre-drinks and post
     (dessert / walk / bar) within a walk radius.
  3. Score the whole evening (dinner-dominant) and diversify into 2-3 plans
     across neighborhoods, plus 1 backup.
  4. Build timeline, est. cost, and vibe arc.
"""

from __future__ import annotations

from typing import Optional

from . import availability, booking, data, geo, reasoning, rubric

WALK_RADIUS_MIN = 12
N_PLANS = 3
TOP_ANCHORS = 12

_DINNER_PP = {1: 25, 2: 55, 3: 120, 4: 265}
_DRINKS_PP = {1: 18, 2: 30, 3: 45, 4: 70}
_DESSERT_PP = {1: 12, 2: 18, 3: 28, 4: 40}


def _vibe(noise: float) -> str:
    return "cozy" if noise < 0.4 else "relaxed" if noise < 0.6 else "lively"


def _arc_word(noise: float) -> str:
    return "quiet" if noise < 0.35 else "relaxed" if noise < 0.6 else "lively"


def _add_minutes(hhmm: str, mins: int) -> str:
    h, m = map(int, hhmm.split(":"))
    total = (h * 60 + m + mins) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _pub(v: dict) -> dict:
    return {
        "id": v["id"], "name": v["name"], "neighborhood": v["neighborhood"],
        "lat": v["lat"], "lng": v["lng"],
        "cuisine": v["cuisine"], "price_tier": v["price_tier"],
        "michelin": v["michelin"], "role": v["role"],
        "booking_platform": v["booking"]["platform"],
        "requires_deposit": v["booking"]["requires_deposit"],
        "url_template": v["booking"].get("url_template"),
        "notes": v.get("notes", ""),
        "photo_url": v.get("photo_url"), "photo_credit": v.get("photo_credit"),
    }


def _with_booking(pub: dict, b) -> dict:
    return {**pub, "booking": booking.for_venue(pub, b.date, b.time, b.party_size)}


def _reason_core(reason: str) -> str:
    # rubric reason format: "Body — tail." -> keep Body, lowercased lead.
    core = reason.split(" — ")[0].rstrip(".")
    return core[0].lower() + core[1:] if core else core


def _best_companion(anchor: dict, pool: list[dict], occasion: str,
                    vibe: float, adjust: Optional[dict] = None) -> Optional[dict]:
    best, best_score = None, -1.0
    for c in pool:
        w = geo.walk_minutes(anchor, c)
        if w > WALK_RADIUS_MIN:
            continue
        fit = rubric.score_venue(c, occasion, vibe=vibe, adjust=adjust)["fit_score"]
        prox = 1.0 - (w / WALK_RADIUS_MIN)
        combo = 0.6 * fit + 0.4 * prox
        if combo > best_score:
            best, best_score = {"venue": c, "walk": w, "fit": fit}, combo
    return best


def _hard_ok(v: dict, b) -> bool:
    if b.budget_max_tier is not None and v["price_tier"] > b.budget_max_tier:
        return False
    if b.neighborhoods and v["neighborhood"] not in b.neighborhoods:
        return False
    if b.cuisine_avoids and ({c.lower() for c in b.cuisine_avoids}
                             & {c.lower() for c in v["cuisine"]}):
        return False
    for req in b.dietary:
        if not v.get("dietary", {}).get(req, False):
            return False
    return True


def _build_plan(anchor: dict, d_fit: dict, drinks: list[dict],
                postpool: list[dict], b, idx: int, is_backup: bool,
                avail: dict) -> dict:
    occ, vibe, adj = b.occasion, b.vibe, getattr(b, "adjust", None)
    pre = _best_companion(anchor, drinks, occ, vibe, adj)
    post = _best_companion(anchor, postpool, occ, vibe, adj)

    # plan score: dinner-dominant, small credit for good walkable companions
    pre_q = pre["fit"] if pre else 0.5
    post_q = post["fit"] if post else 0.5
    plan_fit = round(0.78 * d_fit["fit_score"] + 0.11 * pre_q + 0.11 * post_q, 3)

    # timeline — prefer the requested time, else the nearest real slot
    dinner_time = b.time or "19:30"
    slots = avail.get("slots") or []
    if slots and dinner_time not in slots:
        dinner_time = min(slots, key=lambda s: abs(
            int(s[:2]) * 60 + int(s[3:]) - (int(dinner_time[:2]) * 60 + int(dinner_time[3:]))))
    dur = int(anchor["tags"].get("duration_min", 90))
    timeline, total_walk = [], 0
    if pre:
        timeline.append({"t": _add_minutes(dinner_time, -60),
                         "what": f"Drinks at {pre['venue']['name']}"})
        total_walk += pre["walk"]
    timeline.append({"t": dinner_time,
                     "what": f"Dinner at {anchor['name']} (reservation)"})
    if post:
        timeline.append({"t": _add_minutes(dinner_time, dur + 10),
                         "what": f"{post['venue']['role'][0].title()} at {post['venue']['name']}"})
        total_walk += post["walk"]

    # cost
    cost = _DINNER_PP[anchor["price_tier"]]
    if pre:
        cost += _DRINKS_PP[pre["venue"]["price_tier"]]
    if post:
        pv = post["venue"]
        cost += 0 if "walk" in pv["role"] else _DESSERT_PP[pv["price_tier"]]
    est_total = int(round(cost * b.party_size / 5.0) * 5)

    # vibe arc
    arc = []
    if pre:
        arc.append(_arc_word(pre["venue"]["tags"]["noise"]))
    arc.append(_arc_word(anchor["tags"]["noise"]))
    if post:
        arc.append(_arc_word(post["venue"]["tags"]["noise"]))

    post_kind = ("walk" if (post and "walk" in post["venue"]["role"])
                 else "dessert" if (post and "dessert" in post["venue"]["role"])
                 else "drinks" if post else None)

    struct = {
        "occasion": occ, "total_walk_min": total_walk,
        "vibe_arc": arc,
        "pre": ({"name": pre["venue"]["name"],
                 "vibe": _vibe(pre["venue"]["tags"]["noise"])} if pre else None),
        "dinner": {"name": anchor["name"],
                   "reason_core": _reason_core(d_fit["reason"]),
                   "neighborhood": anchor["neighborhood"]},
        "post": ({"name": post["venue"]["name"], "kind": post_kind} if post else None),
    }
    why = reasoning.explain(struct, use_llm=b.use_llm)

    return {
        "id": f"plan_{'b' if is_backup else idx}",
        "occasion": occ,
        "fit_score": plan_fit,
        "pre": ({**_with_booking(_pub(pre["venue"]), b),
                 "walk_min_to_dinner": pre["walk"]} if pre else None),
        "dinner": {**_with_booking(_pub(anchor), b), "fit_score": d_fit["fit_score"],
                   "top_factors": d_fit["top_factors"], "availability": avail},
        "post": ({**_with_booking(_pub(post["venue"]), b),
                  "walk_min_from_dinner": post["walk"]} if post else None),
        "reasoning": {"plan_level": why["text"], "source": why["source"],
                      "occasion_profile_used": occ, "vibe_arc": arc},
        "logistics": {"total_walk_min": total_walk, "timeline": timeline,
                      "est_total_cost_usd": est_total},
        "is_backup": is_backup,
    }


def assemble(b) -> dict:
    dinners = data.venues_by_role("dinner")
    eligible = [v for v in dinners if _hard_ok(v, b)]
    scored = []
    for v in eligible:
        s = rubric.score_venue(v, b.occasion, vibe=b.vibe,
                               cuisine_likes=b.cuisine_likes,
                               adjust=getattr(b, "adjust", None))
        avail = availability.check(v, b.date, b.time, b.party_size)
        scored.append((v, s, avail))
    scored.sort(key=lambda x: x[1]["fit_score"], reverse=True)

    bookable = [(v, s, a) for v, s, a in scored if a["bookable"]]
    # high-fit places we can't book now (trophy drops / fully booked) — flagged,
    # not silently dropped (DESIGN §5).
    flagged = [{**_with_booking(_pub(v), b), "fit_score": s["fit_score"],
                "availability": a}
               for v, s, a in scored if not a["bookable"]][:6]

    anchors = bookable[:TOP_ANCHORS]

    drinks = data.venues_by_role("drinks")
    postpool = data.venues_by_role("dessert") + data.venues_by_role("walk")

    # build candidate plans (not yet diversified)
    cands = [_build_plan(v, s, drinks, postpool, b, i, False, a)
             for i, (v, s, a) in enumerate(anchors)]
    cands.sort(key=lambda p: p["fit_score"], reverse=True)

    # diversify: prefer distinct neighborhoods, unique dinners
    chosen, used_hoods, used_ids = [], set(), set()
    for p in cands:
        hood = p["dinner"]["neighborhood"]
        if p["dinner"]["id"] in used_ids or hood in used_hoods:
            continue
        chosen.append(p); used_hoods.add(hood); used_ids.add(p["dinner"]["id"])
        if len(chosen) >= N_PLANS:
            break
    if len(chosen) < N_PLANS:  # backfill ignoring neighborhood variety
        for p in cands:
            if p["dinner"]["id"] in used_ids:
                continue
            chosen.append(p); used_ids.add(p["dinner"]["id"])
            if len(chosen) >= N_PLANS:
                break

    # relabel chosen ids 0..n
    for i, p in enumerate(chosen):
        p["id"] = f"plan_{i}"

    # backup: best remaining, prefer a new neighborhood
    backup = None
    for p in cands:
        if p["dinner"]["id"] in used_ids:
            continue
        if p["dinner"]["neighborhood"] not in used_hoods:
            backup = p; break
    if backup is None:
        for p in cands:
            if p["dinner"]["id"] not in used_ids:
                backup = p; break
    if backup:
        bid = backup["dinner"]["id"]
        bv, bs, ba = next((v, s, a) for v, s, a in anchors if v["id"] == bid)
        backup = _build_plan(bv, bs, drinks, postpool, b, 0, True, ba)

    return {
        "considered_dinners": len(dinners),
        "eligible_after_filters": len(eligible),
        "bookable_dinners": len(bookable),
        "checked_for": {"date": b.date, "time": b.time, "party": b.party_size},
        "plans": chosen,
        "backup": backup,
        "unavailable_gems": flagged,
    }
