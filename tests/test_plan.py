"""Smoke + sanity tests for the API using FastAPI TestClient."""

from fastapi.testclient import TestClient

from backend.assemble import WALK_RADIUS_MIN
from backend.main import app

client = TestClient(app)


# --- /health & /rank-dinners (M2 deterministic ranking) ---------------------
def test_health():
    r = client.get("/health").json()
    assert r["ok"] and r["venues"] == 104


def test_first_date_prefers_talkable_not_tasting():
    r = client.post("/rank-dinners",
                    json={"occasion": "first_date", "budget_max_tier": 3}).json()
    assert r["results"]
    assert all(v["price_tier"] <= 3 for v in r["results"])
    assert all("first date" in v["reason"] for v in r["results"][:8])


def test_anniversary_surfaces_special_places():
    r = client.post("/rank-dinners", json={"occasion": "anniversary"}).json()
    assert any(v["michelin"] for v in r["results"][:10])


def test_dietary_hard_filter():
    r = client.post("/rank-dinners",
                    json={"occasion": "second_date", "dietary": ["vegan"]}).json()
    assert 1 <= r["eligible_after_filters"] < r["considered"]


def test_neighborhood_filter():
    r = client.post("/rank-dinners",
                    json={"occasion": "first_date",
                          "neighborhoods": ["West Village"]}).json()
    assert r["results"]
    assert all(v["neighborhood"] == "West Village" for v in r["results"])


def test_unknown_occasion():
    assert "error" in client.post("/plan", json={"occasion": "brunch"}).json()


# --- /plan (M3 evening assembly) --------------------------------------------
def test_plan_assembles_evenings():
    r = client.post("/plan", json={"occasion": "first_date", "use_llm": False}).json()
    assert 1 <= len(r["plans"]) <= 3
    for p in r["plans"]:
        assert p["dinner"]["name"]
        assert p["reasoning"]["plan_level"]
        assert p["reasoning"]["source"] == "template"
        assert p["logistics"]["timeline"]
        assert p["logistics"]["est_total_cost_usd"] > 0


def test_plan_companions_are_walkable():
    r = client.post("/plan", json={"occasion": "anniversary", "use_llm": False}).json()
    for p in r["plans"] + ([r["backup"]] if r["backup"] else []):
        if p["pre"]:
            assert p["pre"]["walk_min_to_dinner"] <= WALK_RADIUS_MIN
        if p["post"]:
            assert p["post"]["walk_min_from_dinner"] <= WALK_RADIUS_MIN


def test_plan_dinners_are_distinct():
    r = client.post("/plan", json={"occasion": "second_date", "use_llm": False}).json()
    ids = [p["dinner"]["id"] for p in r["plans"]]
    assert len(ids) == len(set(ids))


def test_backup_differs_from_plans():
    r = client.post("/plan", json={"occasion": "proposal", "use_llm": False}).json()
    if r["backup"]:
        chosen = {p["dinner"]["id"] for p in r["plans"]}
        assert r["backup"]["dinner"]["id"] not in chosen
        assert r["backup"]["is_backup"] is True


# --- M4 availability --------------------------------------------------------
def _body(**kw):
    return {"occasion": "anniversary", "date": "2026-07-11", "time": "19:30",
            "use_llm": False, **kw}


def test_planned_dinners_are_bookable_with_slots():
    r = client.post("/plan", json=_body()).json()
    assert r["bookable_dinners"] <= r["eligible_after_filters"]
    for p in r["plans"]:
        a = p["dinner"]["availability"]
        assert a["bookable"] is True
        assert a["status"] in ("available", "limited", "walk_in")


def test_availability_is_deterministic():
    a = client.post("/plan", json=_body()).json()
    b = client.post("/plan", json=_body()).json()
    assert [p["dinner"]["name"] for p in a["plans"]] == \
           [p["dinner"]["name"] for p in b["plans"]]


def test_trophy_tables_flagged_not_booked():
    r = client.post("/plan", json=_body()).json()
    gems = {g["name"]: g["availability"]["status"] for g in r["unavailable_gems"]}
    # at least one flagged gem, and none of them appear as bookable plans
    assert gems
    booked = {p["dinner"]["name"] for p in r["plans"]}
    assert not (set(gems) & booked)


def test_no_date_means_not_checked():
    r = client.post("/plan", json={"occasion": "anniversary", "use_llm": False}).json()
    # without a date we don't pretend to know availability
    statuses = {p["dinner"]["availability"]["status"] for p in r["plans"]}
    assert statuses <= {"not_checked", "walk_in"}


# --- M5 booking handoff -----------------------------------------------------
def test_booking_link_prefilled_with_date_and_party():
    r = client.post("/plan", json=_body(party_size=3)).json()
    for p in r["plans"]:
        bk = p["dinner"]["booking"]
        assert bk["kind"] in ("reserve", "search", "call", "walk_in")
        if bk["kind"] in ("reserve", "search"):
            assert bk["url"].startswith("http")
            # party + date should be threaded into reservable platforms
            if bk["platform"] in ("opentable", "resy"):
                assert "3" in bk["url"] and "2026-07-11" in bk["url"]


def test_booking_module_units():
    from backend import booking
    walk = booking.for_venue({"name": "X", "booking_platform": "walk_in"},
                             "2026-07-11", "19:30", 2)
    assert walk["kind"] == "walk_in" and walk["url"] is None
    tmpl = booking.for_venue(
        {"name": "Y", "booking_platform": "resy",
         "url_template": "https://resy.com/v/y?date={date}&seats={party}"},
        "2026-07-11", "19:30", 4)
    assert tmpl["kind"] == "reserve" and "seats=4" in tmpl["url"]
    srch = booking.for_venue({"name": "Le Spot", "booking_platform": "opentable"},
                             "2026-07-11", "19:30", 2)
    assert srch["kind"] == "search" and "Le%20Spot" in srch["url"]


# --- one-click corrections (weight adjust) ----------------------------------
def test_adjust_is_accepted_and_changes_ranking():
    from backend import data, rubric
    dinners = data.venues_by_role("dinner")

    def top(adj):
        s = [(v["name"], rubric.score_venue(v, "anniversary", adjust=adj)["fit_score"])
             for v in dinners]
        s.sort(key=lambda x: x[1], reverse=True)
        return [n for n, _ in s[:5]]

    base = top(None)
    casual = top({"formality": -3, "special_factor": -3, "ambiance": -2, "noise": 2})
    assert base != casual  # corrections actually re-rank
    # endpoint accepts the field without error
    r = client.post("/plan", json={"occasion": "anniversary", "use_llm": False,
                                   "adjust": {"price_high": -3}}).json()
    assert "plans" in r
