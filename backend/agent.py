"""
agent.py — runtime availability agent (Anthropic + web search).

The deterministic stub in `availability.py` is fast and offline; it's used to
filter/rank. THIS module is the dynamic layer: when a user opens a specific plan
we run an LLM agent that actually **searches the web** for that venue's current
hours, reservation policy ("books ~30 days out"), and any recent closure /
private-event notices, then returns a short, cited availability read.

Honest limits: exact live table inventory lives behind OpenTable/Resy/Tock (no
public API), so this is an informed, current assessment — not a guaranteed seat.

Requires ANTHROPIC_API_KEY. If the key or the `anthropic` package is missing,
`available()` returns False and callers fall back to the stub. Kept off the hot
path (only runs on demand per opened plan) to bound cost/latency.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from typing import Optional

_MODEL = os.environ.get("CONCIERGE_AGENT_MODEL", "claude-sonnet-4-6")


def available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


def live_availability(name: str, neighborhood: str, date: Optional[str],
                      time: Optional[str], party: int) -> Optional[dict]:
    try:
        import anthropic
    except Exception:
        return None
    when = date or "an upcoming evening"
    at = f" around {time}" if time else ""
    prompt = (
        f"Check how easy it is to get a table. Search the web for the restaurant "
        f"\"{name}\" in {neighborhood or 'New York City'}. For a party of {party} on "
        f"{when}{at}, determine whether it's open that day + its hours, how reservations "
        f"work (platform + how far ahead it books), any recent closure/private-event "
        f"notice, and overall how easy a table will be.\n\n"
        "Then reply with ONLY a JSON object (no markdown, no text before/after), "
        "each value a SHORT phrase (<=14 words) or null:\n"
        '{"status": "likely_available" | "call_ahead" | "hard_to_get" | '
        '"closed_that_day" | "unknown", '
        '"headline": "one short sentence on how easy a table is", '
        '"hours": "e.g. Wed-Sun 5-9:30pm" | null, '
        '"booking": "e.g. Resy, books 30 days out" | null, '
        '"notice": "recent closure/private event" | null}'
    )
    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=_MODEL, max_tokens=700,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        return None

    text_parts, sources = [], []
    for block in msg.content:
        btype = getattr(block, "type", "")
        if btype == "text":
            text_parts.append(block.text)
            for c in (getattr(block, "citations", None) or []):
                url = getattr(c, "url", None)
                if url:
                    sources.append({"title": getattr(c, "title", "") or url, "url": url})
        elif btype == "web_search_tool_result":
            for r in (getattr(block, "content", None) or []):
                url = getattr(r, "url", None)
                if url:
                    sources.append({"title": getattr(r, "title", "") or url, "url": url})

    text = " ".join(t.strip() for t in text_parts if t.strip()).strip()
    if not text:
        return None

    # de-dupe sources by url, cap a few
    seen, uniq = set(), []
    for s in sources:
        if s["url"] in seen:
            continue
        seen.add(s["url"]); uniq.append(s)

    fields = _parse_json(text)
    if not fields:
        # fallback: model returned prose — clean it into a short headline
        clean = re.sub(r"[*_`#]+", "", text)
        clean = re.sub(r"\s+", " ", clean).strip()
        fields = {"status": "unknown", "headline": clean[:220],
                  "hours": None, "booking": None, "notice": None}

    def short(v):
        if not isinstance(v, str):
            return None
        v = v.strip()
        return v[:120] if v and v.lower() not in ("null", "none", "n/a", "") else None

    status = fields.get("status") if fields.get("status") in _STATUSES else "unknown"
    return {
        "status": status,
        "headline": short(fields.get("headline")) or "Availability information found.",
        "hours": short(fields.get("hours")),
        "booking": short(fields.get("booking")),
        "notice": short(fields.get("notice")),
        "sources": uniq[:4], "source": "agent",
        "checked_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


_STATUSES = {"likely_available", "call_ahead", "hard_to_get",
             "closed_that_day", "unknown"}


def _parse_json(text: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", text, re.S)      # last-resort: grab the JSON object
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None
