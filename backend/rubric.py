"""
rubric.py — deterministic occasion-aware scoring (DESIGN §3).

Scoring is transparent on purpose: a venue's fit is a weighted sum over a small
feature vector, and the SAME per-feature contributions drive both the score and
the plain-language "why". No LLM here (that's M3) — just weights × features.

Key idea ("aligned goodness"): each occasion gives every feature a SIGNED weight.
For a feature value v in [0,1]:
    aligned   = v        if weight >= 0   (we want it high)
              = 1 - v     if weight  < 0   (we want it low)
    contribution = |weight| * aligned
fit_score = sum(contribution) / sum(|weight|)   -> 0..1, absolute & comparable.

Because "aligned" already encodes direction, the top contributions are exactly
the reasons a venue is a GOOD fit (e.g. low noise on a first-date surfaces as
"quiet enough to talk").
"""

from __future__ import annotations

# --- Feature extraction -----------------------------------------------------
# Most features are tag axes (0..1). A few are derived:
#   seating_counter / fixed_menu : bool -> 0/1
#   short_seating : 1 at ~60 min, 0 at ~180 min (prefer-short signal)
#   price_high    : 0 at $, 1 at $$$$ (expense signal)

_DUR_MIN, _DUR_MAX = 60.0, 180.0


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def features(venue: dict) -> dict:
    t = venue["tags"]
    dur = float(t.get("duration_min", 90))
    return {
        "noise": t["noise"],
        "conversation": t["conversation"],
        "intimacy": t["intimacy"],
        "ambiance": t["ambiance"],
        "formality": t["formality"],
        "special_factor": t["special_factor"],
        "privacy": t["privacy"],
        "staff_coordination": t["staff_coordination"],
        "central_transit": t["central_transit"],
        "view": t["view"],
        "seating_counter": 1.0 if t["seating_counter"] else 0.0,
        "fixed_menu": 1.0 if t["fixed_menu"] else 0.0,
        "short_seating": _clamp01((_DUR_MAX - dur) / (_DUR_MAX - _DUR_MIN)),
        "price_high": (float(venue["price_tier"]) - 1.0) / 3.0,
    }


# --- Occasion weight vectors (signed) ---------------------------------------
# +3..-3 mirrors the +++/--- notation in DESIGN §3. Missing key => weight 0.
WEIGHTS: dict[str, dict[str, float]] = {
    "first_date": {
        "conversation": 3.0, "noise": -2.0, "fixed_menu": -2.0,
        "seating_counter": 1.0, "central_transit": 2.0, "formality": -1.0,
        "short_seating": 2.0, "price_high": -1.5, "special_factor": 0.5,
        "intimacy": 0.5,
    },
    "second_date": {
        "ambiance": 2.0, "special_factor": 1.0, "intimacy": 1.5,
        "conversation": 1.0, "noise": -1.0, "view": 0.5,
    },
    "anniversary": {
        "special_factor": 3.0, "ambiance": 3.0, "intimacy": 2.0, "view": 1.5,
        "staff_coordination": 1.0, "noise": -1.0, "formality": 0.5,
        "price_high": 0.5,
    },
    "proposal": {
        "privacy": 3.0, "staff_coordination": 3.0, "special_factor": 2.0,
        "intimacy": 2.0, "noise": -2.0, "view": 1.5, "ambiance": 1.0,
    },
    "business": {
        "noise": -3.0, "conversation": 3.0, "central_transit": 2.0,
        "formality": 1.0, "staff_coordination": 1.0, "fixed_menu": -1.0,
        "special_factor": 0.5, "intimacy": -0.5,
    },
    "group": {
        "noise": 0.5, "special_factor": 1.0, "ambiance": 1.0,
        "conversation": 1.0, "short_seating": -0.5,
    },
}

OCCASIONS = tuple(WEIGHTS.keys())

# Human phrasing per feature: (phrase when we want it HIGH, phrase when LOW).
_PHRASE: dict[str, tuple[str, str]] = {
    "noise": ("lively energy", "quiet enough to talk"),
    "conversation": ("easy to hold a conversation", "conversation takes effort"),
    "intimacy": ("an intimate, close room", "an open, social room"),
    "ambiance": ("a striking, memorable room", "a plain room"),
    "formality": ("polished and formal", "relaxed and unstuffy"),
    "special_factor": ("feels like a real occasion", "low-key, no pressure"),
    "privacy": ("private and discreet", "out in the open"),
    "staff_coordination": ("staff used to special requests", ""),
    "central_transit": ("central and easy to reach", "a bit out of the way"),
    "view": ("a notable view", ""),
    "seating_counter": ("counter seating keeps it low-pressure", ""),
    "fixed_menu": ("a full tasting-menu experience", "no tasting-menu lock-in"),
    "short_seating": ("a shorter, easy-to-wrap-up meal", "a long, lingering meal"),
    "price_high": ("a splurge", "easy on the wallet"),
}


def _apply_vibe(weights: dict[str, float], vibe: float) -> dict[str, float]:
    """vibe in [-1,1]: +1 push toward special/ambiance, -1 toward casual/short."""
    if not vibe:
        return weights
    w = dict(weights)
    w["special_factor"] = w.get("special_factor", 0.0) + 1.5 * vibe
    w["ambiance"] = w.get("ambiance", 0.0) + 1.0 * vibe
    if vibe < 0:  # chill: nudge toward shorter, less formal
        w["short_seating"] = w.get("short_seating", 0.0) + 0.5 * (-vibe)
        w["formality"] = w.get("formality", 0.0) - 0.5 * (-vibe)
    return w


def score_venue(venue: dict, occasion: str, vibe: float = 0.0,
                cuisine_likes: list[str] | None = None,
                adjust: dict[str, float] | None = None) -> dict:
    """Return fit_score (0..1), top contributing factors, and a reason string.

    `adjust` adds signed deltas to specific feature weights (powers the
    results-side one-click corrections, e.g. {"formality": -1.5}).
    """
    weights = _apply_vibe(WEIGHTS[occasion], vibe)
    if adjust:
        weights = dict(weights)
        for k, dv in adjust.items():
            if isinstance(dv, (int, float)):
                weights[k] = weights.get(k, 0.0) + float(dv)
    f = features(venue)
    denom = sum(abs(w) for w in weights.values()) or 1.0

    contribs = []  # (feature, contribution, want_high)
    total = 0.0
    for feat, w in weights.items():
        if w == 0:
            continue
        v = f.get(feat, 0.0)
        aligned = v if w >= 0 else (1.0 - v)
        c = abs(w) * aligned
        total += c
        contribs.append((feat, c, w >= 0))

    fit = total / denom

    # soft cuisine-like nudge (tiebreak only, capped) — kept out of denom
    if cuisine_likes:
        overlap = len(set(c.lower() for c in cuisine_likes)
                      & set(c.lower() for c in venue["cuisine"]))
        if overlap:
            fit = min(1.0, fit + 0.03 * overlap)

    contribs.sort(key=lambda x: x[1], reverse=True)
    top = []
    for feat, c, want_high in contribs[:3]:
        phrase = _PHRASE.get(feat, ("", ""))[0 if want_high else 1]
        if phrase:
            top.append({"feature": feat, "contribution": round(c, 3),
                        "note": phrase})

    reason = _compose_reason(top, occasion, venue)
    return {"fit_score": round(fit, 3), "top_factors": top, "reason": reason}


_OCCASION_TAIL = {
    "first_date": "easy for a first date",
    "second_date": "a nice step up for a second date",
    "anniversary": "fitting for an anniversary",
    "proposal": "right for a proposal",
    "business": "solid for a business dinner",
    "group": "good for a group celebration",
}


def _compose_reason(top: list[dict], occasion: str, venue: dict) -> str:
    if not top:
        return f"A reasonable option — {_OCCASION_TAIL.get(occasion, '')}."
    notes = [t["note"] for t in top]
    if len(notes) == 1:
        body = notes[0]
    elif len(notes) == 2:
        body = f"{notes[0]} and {notes[1]}"
    else:
        body = f"{notes[0]}, {notes[1]}, and {notes[2]}"
    body = body[0].upper() + body[1:]
    return f"{body} — {_OCCASION_TAIL.get(occasion, '')}."
