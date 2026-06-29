# Design — Special-Occasion Dining Concierge

> The full design. `CLAUDE.md` is the lean "read this first" orientation;
> this is the detail. Sections: Overview · Architecture · Occasion Rubric ·
> Data & Dataset · Booking · Build Plan.

## Table of contents
- [1. Overview](#1-overview)
- [2. Architecture](#2-architecture)
- [3. Occasion → Vibe Rubric](#3-occasion--vibe-rubric)
- [4. Data Model & Seed Dataset](#4-data-model--seed-dataset)
- [5. Booking: Assisted, Human-Confirms](#5-booking-assisted-human-confirms)
- [6. Build Plan](#6-build-plan)

---

## 1. Overview

### Problem

Booking a great restaurant for a *special occasion* is hard in a specific way.
The platforms (OpenTable, Resy, Tock) are good at "find a table for 2 tonight"
but bad at "find the right place for a **first date** vs. a **10th
anniversary**." They don't reason about vibe, conversation-friendliness, timing,
or how the whole evening flows. The user is left cross-referencing Michelin
lists, Infatuation reviews, and three booking apps by hand.

### What we're building

An agentic web app that takes a short brief about the occasion and returns a
small set of **complete evening plans** — optionally drinks beforehand, a dinner
anchor, optionally dessert or a walk after — each with a transparent explanation
of why it fits. The user picks one and is handed off to the booking platform,
one click from confirming.

### Who it's for

A person planning a meaningful evening who wants it to feel considered, not
generic. Initially the builder (us) in NYC; later, anyone.

### Goals

1. **Occasion-aware matching.** Map the occasion to concrete venue attributes
   and rank against them (see [§3](#3-occasion--vibe-rubric)).
2. **Transparency.** Always show the rubric and a plain-language reason per pick.
   This is the trust mechanism and the main differentiator.
3. **Whole-evening planning.** Pre/dinner/post, walkable and time-sequenced.
4. **Safe booking.** Assisted, human-confirms, no stored credentials, no
   server-side money movement.

### Non-goals (v1)

- Cities other than NYC (architecture stays portable; data does not).
- Fully autonomous booking / auto-confirm.
- "Drop-watch" sniping of trophy reservations that release on a schedule —
  incompatible with human-confirm; surfaced but routed to manual.
- Group logistics beyond party size (no split-pay, no group polling).
- Native mobile app. (Responsive web only.)

### Success criteria for v1

- For a given NYC brief, returns 2–3 coherent evening plans with available
  dinner slots and believable, occasion-specific reasoning.
- Every recommendation is explainable: user can see *why* and correct the vibe
  with minimal friction.
- Booking handoff lands the user on the correct pre-filled reservation page.

---

## 2. Architecture

### High-level

```
┌─────────────┐     brief      ┌──────────────────────────────┐
│  Frontend   │ ─────────────▶ │  FastAPI backend             │
│  (HTML/JS)  │                │                              │
│             │                │  1. Intake → structured brief│
│  intake     │ ◀───────────── │  2. Candidate retrieval      │
│  plans      │  evening plans │  3. Availability check       │
│  detail     │                │  4. LLM scoring + reasoning  │
└─────────────┘                │  5. Evening assembly         │
       │                       └──────────────────────────────┘
       │ deep-link                      │            │
       ▼                                ▼            ▼
  Booking platform              Curated dataset   Availability
  (user's browser,              (104 venues:      (live, per
   already logged in)            dinner+bars+       request)
                                 dessert+walk)
```

### Components

#### Frontend (single HTML/JS app)
Four screens:
1. **Intake** — one screen of questions (occasion, date/time, party size,
   neighborhood, budget, cuisine likes/avoids, dietary, one vibe slider).
2. **Reasoning/loading** — shows what it's doing (sets expectation, builds trust).
3. **Plans** — 2–3 evening-plan cards, each with fit score, rubric chips, and a
   one-line reason; one designated backup for high-demand nights.
4. **Plan detail** — the three venues, plan-level reasoning, timeline, walk map,
   est. cost, and the deep-link "book" buttons.

No secrets in the browser. All reasoning calls go through the backend.

#### Backend (Python / FastAPI)
Primary endpoint: `POST /plan` — takes the brief, returns ranked evening plans.
Internally:

1. **Intake normalization.** Raw form → structured brief. Occasion expands into
   a rubric weight vector ([§3](#3-occasion--vibe-rubric)). Hard constraints
   (date/time/party/budget/dietary/geo) separated from soft preferences.
2. **Candidate retrieval.** Filter the curated dataset by hard constraints →
   candidate dinner venues. Separately pull nearby bar + dessert/walk options.
3. **Availability check.** For candidate dinners, check live availability for
   the requested slot (v1 can stub this; see build plan). Unavailable curated
   gems are flagged, not silently dropped.
4. **LLM scoring + reasoning.** Score each candidate against the occasion rubric,
   produce a fit score and a plain-language *why*. Reasoning is a first-class
   output, not a side effect.
5. **Evening assembly.** Combine dinner + walkable pre/post into 2–3 coherent
   plans with plan-level reasoning (vibe arc, timing, walk distance) + 1 backup.

#### Data layer (cached)
- **Curated venue set** — 104 NYC venues, pre-tagged on rubric axes. Refreshed
  slowly (curated sources change over weeks, not minutes). See [§4](#4-data-model--seed-dataset).
- **Bars + dessert/walk venues** — same treatment, geo-tagged for proximity.
- **Availability** — live per request, short TTL cache.

#### Reasoning layer
Lives in the backend. Two responsibilities: (a) deterministic rubric scoring
(weights × tags) gives a transparent base score; (b) the LLM writes the
explanation and assembles the evening, constrained by the structured data so it
can't invent venues or slots.

> Design choice: keep scoring **mostly deterministic** (weights × tags) so the
> "why" the user sees matches the math, and use the LLM for language + assembly,
> not for inventing the ranking. This is what makes transparency honest.

### Data flow for one request
brief → normalize (+rubric weights) → filter by hard constraints → candidates →
availability → score+explain → assemble 2–3 plans (+backup) → return → render
→ user picks → deep-link handoff.

### Portability note
Everything except the dataset is city-agnostic. Adding a city = adding a
curated dataset for it. Keep city as a field on every venue and on the brief.

---

## 3. Occasion → Vibe Rubric

This is the core asset. It maps an occasion to a **weighted set of venue
attributes**. Scoring is `sum(weight_i × venue_tag_i)`, which keeps the ranking
transparent: the "why" shown to the user is literally the math.

### Rubric axes (venue attributes)

Each venue in the dataset is tagged on these axes, normalized 0–1 unless noted.

| Axis | Meaning |
|---|---|
| `noise` | 0 = silent, 1 = loud/club-like |
| `conversation` | how easy it is to talk (often inverse of noise + layout) |
| `intimacy` | tables-close, low light, private feel |
| `ambiance` | design/decor/memorability of the room |
| `formality` | 0 = super casual, 1 = jacket-required formal |
| `special_factor` | "is this a treat / occasion-worthy" feeling |
| `duration_min` | typical seating length in minutes (raw number) |
| `seating_counter` | bool — has bar/counter seating (good for low-pressure dates) |
| `fixed_menu` | bool — locks you into a long tasting menu |
| `price_tier` | 1–4 ($ to $$$$) |
| `privacy` | suitability for a private/quiet moment (proposals) |
| `staff_coordination` | known to accommodate special requests |
| `central_transit` | ease of getting to / meeting at |
| `view` | notable view or scenic setting |

> Some axes (noise, conversation, intimacy, ambiance) are **not** in any booking
> API. They come from an enrichment pass over curated reviews and are cached on
> the venue. See [§4](#4-data-model--seed-dataset).

### Occasion profiles (weight vectors)

Weights are illustrative starting points — tune with real results. `+` favors
high values, `−` penalizes them; magnitude = importance.

**First date** — low pressure, easy conversation, easy exit, not a huge
financial commitment.
- conversation **+++**, noise **− −**, duration_min: prefer ≤ 90 (penalize long),
  fixed_menu **− −**, seating_counter **+**, price_tier target $$–$$$ (penalize $$$$),
  central_transit **++**, formality: mild penalty if very high.
- Vibe words: *lively but talkable, not stuffy, easy.*

**Second / third date** — a step up, a bit more special, still relaxed.
- ambiance **++**, special_factor **+**, intimacy **+**, conversation **+**,
  price_tier target $$$, duration moderate.

**Anniversary / milestone** — memorable, intimate, worth the splurge.
- special_factor **+++**, ambiance **+++**, intimacy **++**, view **+**,
  duration flexible (no penalty for long / tasting menus), price_tier up to $$$$,
  formality neutral-to-high ok.

**Proposal** — privacy, a staff that can help, a moment.
- privacy **+++**, staff_coordination **+++**, special_factor **++**,
  intimacy **++**, noise **− −**, view **+**. Flag venues known to accommodate
  proposals.

**Business dinner** — quiet, reliable, central, expense-friendly, no spectacle.
- noise **− − −**, conversation **+++**, central_transit **++**, formality **+**,
  price_tier $$$ (expense-able), special_factor neutral, fixed_menu mild penalty.

**Celebration with friends / group** — fun, lively, shareable, fits a group.
- noise neutral-to-high ok, special_factor **+**, shareable/lively **+**,
  party-size fit **+++**, conversation moderate.

### Hard vs. soft

- **Hard constraints** (filter, not weight): date/time availability, party size,
  budget ceiling, dietary/allergy, neighborhood radius. A perfect-vibe place that
  can't seat the party is dropped before scoring.
- **Soft preferences** (the rubric above): rank what survives the filter.

### Transparency contract

Every recommendation returns:
1. The **occasion profile** used (which axes mattered and how much).
2. A **fit score** (the weighted sum, normalized).
3. A **plain-language reason** generated from the top contributing axes
   (e.g., "Quiet room, ~75-min seating, no tasting-menu lock-in — easy for a
   first date").
4. One-click **vibe corrections** ("too formal", "louder is fine", "go more
   special") that nudge weights and re-rank.

### Open tuning questions
- Exact duration thresholds per occasion.
- Whether `price_tier` should be a hard ceiling, a soft penalty, or both (lean:
  ceiling = hard from budget; *under*-spending = mild soft penalty for milestone
  occasions where too-cheap reads as not-special).
- How aggressively to penalize `fixed_menu` for first dates (lean: strong).

---

## 4. Data Model & Seed Dataset

### The Evening Plan object (core unit)

```jsonc
{
  "id": "plan_xxx",
  "occasion": "first_date",
  "fit_score": 0.87,
  "pre": { /* Venue, optional — drinks before */ },
  "dinner": { /* Venue, the anchor */ },
  "post": { /* Venue, optional — dessert / bar / scenic walk */ },
  "reasoning": {
    "plan_level": "Lively drinks at X to warm up, then an intimate dinner at Y a 4-min walk away, ending with a quiet walk along Z — the energy winds down as the night goes on.",
    "occasion_profile_used": "first_date",
    "vibe_arc": ["lively", "intimate", "quiet"]
  },
  "logistics": {
    "total_walk_min": 11,
    "timeline": [
      { "t": "18:30", "what": "Drinks at X" },
      { "t": "19:30", "what": "Dinner at Y (reservation)" },
      { "t": "21:15", "what": "Dessert / walk" }
    ],
    "est_total_cost_usd": 240
  },
  "is_backup": false
}
```

### The Venue object

```jsonc
{
  "id": "venue_xxx",
  "name": "…",
  "city": "NYC",
  "neighborhood": "West Village",
  "lat": 40.73, "lng": -73.99,
  "cuisine": ["japanese", "omakase"],
  "price_tier": 4,              // 1–4
  "michelin": "1_star",        // null | bib_gourmand | 1_star | 2_star | 3_star
  "role": ["dinner"],          // dinner | drinks | dessert | walk (can be multi)
  "archetype": "omakase_counter", // drives base tag profile (see scripts/build_dataset.py)
  "booking": {
    "platform": "resy",        // resy | opentable | tock | phone_only | walk_in
    "url_template": null,       // for deep-link handoff (see §5); filled at M5
    "requires_deposit": false
  },
  "tags": {                      // the rubric axes, see §3
    "noise": 0.3, "conversation": 0.8, "intimacy": 0.7, "ambiance": 0.8,
    "formality": 0.6, "special_factor": 0.9, "duration_min": 110,
    "seating_counter": true, "fixed_menu": true, "privacy": 0.6,
    "staff_coordination": 0.7, "central_transit": 0.5, "view": 0.2
  },
  "good_for": ["anniversary", "proposal"],   // quick occasion hints
  "dietary": { "vegetarian": true, "vegan": false, "gluten_free": true },
  "notes": "Counter omakase; books 30 days out on Resy at 9am.",
  "sources": ["knowledge_seed"],  // provenance; → ["michelin","infatuation",...] after enrichment
  "verified": false               // facts unverified until M4 (see data/DATA_NOTES.md)
}
```

### Seed dataset — 104 NYC venues (built ✓)

A curated static dataset, built before any live integration, so the whole
experience can be proven on real-but-static data. **As built** (`data/nyc_venues.json`):

| Role | Count | Notes |
|---|---|---|
| dinner | 68 | tiers: 13× $ / 11× $$ / 40× $$$ / 40× $$$$ (across all roles) |
| drinks | 19 | cocktail bars, wine bars, hotel-bar-with-view |
| dessert | 8 | bakeries, gelato, dessert bars |
| walk | 9 | scenic-walk pseudo-venues (`role: walk`) |

Michelin among dinners: 4× 3-star, 9× 2-star, 15× 1-star.

**Neighborhood clustering.** Venues are concentrated in **6 walkable clusters**
(West Village/Greenwich, East Village/LES, Flatiron/Gramercy/NoMad, Midtown,
Brooklyn [Williamsburg/Dumbo/etc.], Tribeca/Soho/Nolita) so pre/dinner/post can
be stitched within a short walk. Each cluster has both dinners and pre/post
options. A gorgeous dinner with no nearby drinks makes a weak plan.

**How it's built.** Generated by `scripts/build_dataset.py`: each venue inherits
a base tag profile from an **archetype** (e.g. `omakase_counter`, `lively_bistro`,
`hotel_bar_view`) plus per-venue overrides, keeping all axes on a consistent
0–1 scale. Edit the script's `V` list / archetype profiles, not the JSON.

**Tagging / provenance.** Seed tags + facts are from general knowledge
(`sources: ["knowledge_seed"]`, `verified: false`). The intended enrichment pass
(Michelin, Infatuation, Eater, omakase roundups) + spot-check happens at M4; see
`data/DATA_NOTES.md` for what must be verified (Michelin status, booking platform,
lat/lng, subjective tags).

**Format.** `data/nyc_venues.json` (array of Venue objects). Walk pseudo-venues
live in this same file as `role: walk` entries — no separate `walks.json`.

### Validation (passing)
- Every venue: valid NYC lat/lng, price_tier 1–4, all rubric axes present and
  in range, unique id + name.
- Every cluster has ≥1 dinner and ≥1 pre/post venue so plans can be assembled.
- `good_for` consistent with tags (e.g., a `proposal` venue has decent `privacy`).

---

## 5. Booking: Assisted, Human-Confirms

### Principle

The app **never** moves money, stores platform credentials, or auto-confirms a
reservation. It does all the thinking, then hands the user off to the booking
platform **one click from confirm**, in the user's own browser where they're
already logged in.

### Why not server-side automation

A Render-hosted web app can't safely drive OpenTable/Resy/Tock:

- Those platforms have **no public booking API** for third parties.
- Automating their sites needs a real browser **and the user's logged-in
  session** — neither exists on a server. Doing it server-side means storing
  credentials, fighting bot detection / CAPTCHAs / 2FA, and likely violating ToS.
- Deposits and card-holds (common at Tock and many omakase counters) mean a
  wrong action costs real money.

So v1 uses **deep-link handoff** instead. This is genuinely "assisted-confirm,"
done honestly.

### Deep-link handoff

For a chosen dinner venue, the app opens the platform's reservation page with
date / time / party-size pre-filled, in a new tab in the user's browser.

- **OpenTable** and **Resy** support parameterized reservation URLs (date, time,
  party size, venue). Store a `url_template` per venue (see [§4](#4-data-model--seed-dataset)).
- **Tock** / deposit venues: open the venue page but **stop before any payment**;
  make the deposit explicit in the UI so there are no surprises.
- **phone_only / walk_in** venues: don't pretend to book. Show the phone number,
  hours, and a one-line script; mark clearly as "call to book."

The user lands on the real page, reviews, and clicks confirm themselves.

### Trophy-tier reservations (out of v1)

Many Michelin / top omakase tables release on a schedule (e.g., Resy drops
exactly 30 days out at 9am) and vanish in seconds. "Drop-watch" sniping can't be
human-confirm (no time for a human in the loop), so it's **out of v1**. v1 still
*surfaces* these venues but routes them to manual: "This one books 30 days out
at 9am on Resy — here's the link and the timing." A future "power mode" (chat
agent + browser automation under the user's own session) could attempt these,
but the hosted app must not depend on it.

### Future "power mode" (not v1)

For users who want the agent to actually fill the form: a local/extension-based
flow (browser automation in the user's own authenticated session) can navigate
and fill, still stopping at the final confirm. Kept separate from the hosted app
so the hosted app stays credential-free and ToS-clean.

### What the app should still do around booking
- Add-to-calendar (.ics) for the chosen plan.
- A reminder (optional).
- The designated **backup** plan, surfaced for high-demand nights in case the
  first choice is gone by the time the user clicks through.

---

## 6. Build Plan

Prove the experience on static data before touching the messy parts (live
availability, scraping). Deploy to Render only after the core loop feels right.

### Milestones

**M1 — single-file frontend** *(complete ✓, redesigned)*
- ✓ `frontend/index.html` (vanilla, self-contained), served at `/app`.
- ✓ UX redesign: **dark "Evening" / light "Daylight" theme toggle** (localStorage,
  Fraunces + Inter); **occasion-first progressive intake** (tap an occasion →
  optional details reveal; chips for date/time/where/budget/diet, stepper, vibe
  slider); itinerary cards with a visual **vibe arc**; detail modal with timeline,
  rubric factors, booking, `.ics` export.
- ✓ **One-click vibe corrections** on results (more casual / more special / louder /
  quieter / cheaper) — fulfils the transparency contract (§3 item 4). Each toggles
  signed weight deltas sent as `brief.adjust` and re-ranks instantly.
- ✓ **Maps.** Result cards: a self-contained illustrated SVG route map (offline,
  themed — river/park/roads/street-names + numbered pins on the real lat/lng
  walking route). Detail view: an interactive **Leaflet + Carto** map (keyless;
  Dark Matter / Positron by theme) with numbered markers + route, degrading to the
  SVG map if the CDN is unreachable. Detail map needs network; cards stay offline.

**M2 — FastAPI backend + seed dataset** *(complete ✓)*
- ✓ `data/nyc_venues.json` — 104-venue seed built (see [§4](#4-data-model--seed-dataset)).
- ✓ `POST /plan` endpoint (+ `GET /health`) in `backend/main.py`.
- ✓ Deterministic pipeline: hard-constraint filter → "aligned goodness" rubric
  scoring (`backend/rubric.py`) → ranked dinners with fit scores + reasons.
  No LLM; weights × features. 7 passing tests (`tests/test_plan.py`).

**M3 — LLM reasoning + evening assembly** *(complete ✓)*
- ✓ Assemble dinner + walkable pre/post into 2–3 plans + 1 backup
  (`backend/assemble.py`, `geo.py`): walk-radius companions, dinner-dominant plan
  score, neighborhood diversification, timeline, est. cost, vibe arc.
- ✓ Plan-level reasoning (`backend/reasoning.py`): deterministic template by
  default; auto-upgrades to a constrained LLM sentence if `ANTHROPIC_API_KEY` is
  set (facts-only prompt, fallback to template, `source` reported). Can't invent
  venues — it only describes the assembled structured data.
- ✓ `POST /plan` now returns evening plans; `POST /rank-dinners` keeps the M2
  ranking for debugging. 10 passing tests.

**M4 — Availability** *(stub complete ✓)*
- ✓ Provider abstraction + deterministic **stub** (`backend/availability.py`):
  status (available / limited / released_on_schedule / unavailable / phone_only /
  walk_in / not_checked), slots near the requested time, demand-aware (weekend,
  prime time, party size, tier, Michelin). Trophy tables flagged "released on
  schedule," not booked. No date → `not_checked` (we don't pretend).
- ✓ Wired into assembly: plans built only from bookable dinners; high-fit
  unbookable spots surfaced as `unavailable_gems` (flagged, not dropped). Slots
  drive the timeline. Frontend shows status/slots + a "worth knowing" section.
- ☐ *Real* provider (replace stub) — deferred: no public APIs, scraping is
  fragile/ToS-risky. Revisit with verified `verified:true` data + a sanctioned
  source. The interface is ready for the swap.

**M5 — Booking handoff** *(complete ✓)*
- ✓ `backend/booking.py`: per-venue handoff URL — uses `url_template` when set,
  else a date/time/party pre-filled platform SEARCH url (OpenTable/Resy/Tock);
  phone_only / walk_in handled honestly. `kind` drives the button + caveat.
  Attached to every plan leg (and flagged gems).
- ✓ Add-to-calendar (`.ics`) generated client-side for the chosen plan (enabled
  once a date is set). Deposit note shown in the UI.
- Note: exact one-click deep-links arrive automatically once venues are verified
  and `url_template` is populated — the search fallback is the interim.

**M6 — Deploy to Render**
- Containerize, env-managed API keys, basic rate limiting.

### Suggested repo layout

Built so far is marked ✓; the rest is planned.

```
.
├── CLAUDE.md             ✓
├── docs/
│   └── DESIGN.md         ✓ (this file)
├── data/
│   ├── nyc_venues.json   ✓ (104 venues, walks included as role:walk)
│   └── DATA_NOTES.md     ✓ (provenance + verification status)
├── scripts/
│   ├── build_dataset.py  ✓ (generator; source of truth for the dataset)
│   └── geocode.py        ✓ (Nominatim batch — fix coords + verify; run later)
├── requirements.txt      ✓
├── tests/
│   └── test_plan.py      ✓ (7 tests)
├── backend/
│   ├── main.py           ✓ (FastAPI: /plan, /rank-dinners, /health, /)
│   ├── rubric.py         ✓ (occasion weight vectors + scoring + reasons)
│   ├── data.py           ✓ (dataset loader/cache)
│   ├── geo.py            ✓ (haversine + walk-minutes)
│   ├── assemble.py       ✓ (evening-plan assembly)
│   ├── reasoning.py      ✓ (plan prose; template + optional LLM)
│   ├── availability.py   ✓ (provider interface + deterministic stub)
│   └── booking.py        ✓ (handoff URLs: url_template or pre-filled search)
└── frontend/
    └── index.html        ✓ (single-file app; served at /app)
```

### Risks & mitigations
- **Tag quality** (subjective axes): LLM-assist from review text, then human
  spot-check. The whole product's credibility rests on these tags.
- **Live availability fragility / ToS:** keep it read-only and resilient; the app
  must degrade gracefully to "check the link" if a lookup fails.
- **Trophy reservations:** explicitly out of v1; surfaced and routed to manual.
- **Walkability gaps:** enforce neighborhood clustering in the dataset so plans
  can always be assembled.

### Open questions (carried from chat)
1. Live availability source for M4 — which platforms first, and stub vs. real
   for the first deployable cut?
2. Duration thresholds and price penalties — finalize the rubric tuning numbers.
3. Calendar / reminders — in v1 or later?
4. Single user (us) or multi-user with accounts from the start? (Leaning single
   user for v1; accounts later.)

### Immediate next step
M1–M5 done; the full flow works at `/app` (brief → plans → availability →
booking handoff + calendar + maps). Next: **M6 deploy to Render** — containerize,
env config (`ANTHROPIC_API_KEY` optional), basic rate limiting, health check.
Then the data-verification pass: run `scripts/geocode.py` to fix coords + flip
`verified:true`, fill `url_template`s for exact deep-links, and revisit a real
availability provider.
