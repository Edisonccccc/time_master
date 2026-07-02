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
import os
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
        f"Search the web for the restaurant \"{name}\" in {neighborhood or 'New York City'}. "
        f"Using what you find, report for a party of {party} on {when}{at}:\n"
        "1) current opening hours (and whether it's open that day),\n"
        "2) how reservations work (platform, and how far ahead it typically books),\n"
        "3) any recent notices (temporary closure, private events, relocation).\n"
        "Then give ONE plain-language sentence assessing how easy a table is likely "
        "to be. Be concise (max ~70 words total), factual, and do not invent specifics "
        "you didn't find. If little is found, say so."
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

    summary = " ".join(t.strip() for t in text_parts if t.strip()).strip()
    if not summary:
        return None
    # de-dupe sources by url, cap a few
    seen, uniq = set(), []
    for s in sources:
        if s["url"] in seen:
            continue
        seen.add(s["url"]); uniq.append(s)
    return {"summary": summary, "sources": uniq[:4], "source": "agent",
            "checked_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"}
