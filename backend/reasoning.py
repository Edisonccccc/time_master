"""
reasoning.py — plan-level "why" generation (DESIGN §3 transparency).

Default: deterministic, template-based prose built ONLY from the assembled
structured facts (so it can never invent a venue). If an ANTHROPIC_API_KEY is
present and the `anthropic` package is installed, we upgrade to a short LLM
sentence — still constrained to the same facts, with deterministic fallback on
any error. The chosen source is reported back so the output stays transparent.
"""

from __future__ import annotations

import os
from typing import Optional

_MODEL = os.environ.get("CONCIERGE_LLM_MODEL", "claude-haiku-4-5-20251001")

_OCCASION_TAIL = {
    "first_date": "easy for a first date",
    "second_date": "a nice step up for a second date",
    "anniversary": "fitting for an anniversary",
    "proposal": "right for a proposal",
    "business": "solid for a business dinner",
    "group": "good for a group celebration",
}


def _deterministic(struct: dict) -> str:
    occ = struct["occasion"]
    segs = []
    pre = struct.get("pre")
    if pre:
        segs.append(f"start with {pre['vibe']} drinks at {pre['name']}")
    dn = struct["dinner"]
    core = dn.get("reason_core") or "a great room"
    segs.append(f"dinner at {dn['name']} ({core})")
    post = struct.get("post")
    if post:
        if post["kind"] == "walk":
            segs.append(f"then a stroll at {post['name']} to wind down")
        elif post["kind"] == "dessert":
            segs.append(f"then dessert at {post['name']}")
        else:
            segs.append(f"then a nightcap at {post['name']}")
    body = ", ".join(segs)
    body = body[0].upper() + body[1:]
    walk = struct.get("total_walk_min")
    walk_clause = f" About {walk} min of walking in total." if walk else ""
    return f"{body}.{walk_clause} {_OCCASION_TAIL.get(occ, '').capitalize()}."


def _llm(struct: dict) -> Optional[str]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic  # noqa: local optional dependency
    except Exception:
        return None
    try:
        facts = {
            "occasion": struct["occasion"],
            "pre_drinks": struct.get("pre"),
            "dinner": struct["dinner"],
            "post": struct.get("post"),
            "total_walk_min": struct.get("total_walk_min"),
            "vibe_arc": struct.get("vibe_arc"),
        }
        prompt = (
            "Write ONE warm, concrete sentence (max 40 words) telling the user why "
            "this evening plan suits the occasion. Use ONLY the facts in the JSON; "
            "do NOT invent venues, dishes, or details. No emojis.\n\n"
            f"FACTS:\n{facts}"
        )
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=_MODEL, max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return text.strip() or None
    except Exception:
        return None


def explain(struct: dict, use_llm: Optional[bool] = None) -> dict:
    """Return {'text', 'source'}. use_llm None = auto-detect by env."""
    if use_llm is not False:
        text = _llm(struct)
        if text:
            return {"text": text, "source": "llm"}
    return {"text": _deterministic(struct), "source": "template"}
