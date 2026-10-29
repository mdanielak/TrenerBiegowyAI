# -*- coding: utf-8 -*-
"""Przerwy z poziomu Dziennika."""
import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from services.pauses import pause_views, planned_workouts_in, validate_pause
from services.plan import save_plan
from trainer import preferences

pytestmark = pytest.mark.usefixtures("testclient_sockets")

TODAY = date(2026, 10, 28)


def _pause(**overrides):
    values = dict(pause_type="illness", start="2026-10-29", end="2026-10-31", note="  przeziębienie ", today=TODAY)
    values.update(overrides)
    return validate_pause(**values)


def test_validation_and_reason_with_the_type_first():
    assert _pause()["reason"] == "Choroba: przeziębienie"
    assert _pause(note="", pause_type="vacation")["reason"] == "Wyjazd"
    with pytest.raises(ValueError, match="przed jej początkiem"):
        _pause(start="2026-11-02", end="2026-11-01")
    with pytest.raises(ValueError, match="30 dni wstecz"):
        _pause(start="2026-09-01")
    with pytest.raises(ValueError, match="rodzaj"):
        _pause(pause_type="urlop")


def test_views_skip_finished_pauses_and_mark_the_current_one():
    views = pause_views([
        {"start_date": "2026-10-01", "end_date": "2026-10-05", "reason": "stara", "type": "medical"},
        {"start_date": "2026-10-27", "end_date": "2026-10-29", "reason": "Choroba", "type": "illness"},
        {"start_date": "2026-11-10", "end_date": "2026-11-12", "reason": "Wyjazd", "type": "vacation"},
    ], today=TODAY)

    assert [v["reason"] for v in views] == ["Choroba", "Wyjazd"]
    assert views[0]["is_active"] and not views[1]["is_active"]


def _week_plan():
    monday = date(2026, 10, 26)
    workouts = [{"date": (monday + timedelta(days=i)).isoformat(), "day": key,
                 "type": "easy" if i in (3, 6) else "rest", "name": "Bieg", "duration_min": 40}
                for i, key in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"))]
    return {"start_date": "2026-10-26", "end_date": "2026-11-01", "workouts": workouts}


def test_overlap_lists_only_days_with_training_from_today():
    save_plan(_week_plan())

    assert planned_workouts_in("2026-10-20", "2026-11-05", today=TODAY) == ["2026-10-29", "2026-11-01"]


def _csrf(client):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get("/journal").text).group(1)


def test_journal_adds_and_removes_a_pause(tmp_path):
    client = TestClient(create_app(journal_path=tmp_path / "journal.jsonl"))
    today = date.today()
    data = {"csrf_token": _csrf(client), "pause_type": "vacation", "start": today.isoformat(),
            "end": (today + timedelta(days=3)).isoformat(), "note": "Zakopane"}

    added = client.post("/journal/pause", data=data, headers={"Origin": "http://testserver"}, follow_redirects=False)

    assert added.status_code == 303 and "pause=added" in added.headers["location"]
    [stored] = preferences.list_planned_pauses()
    assert stored["reason"] == "Wyjazd: Zakopane" and stored["type"] == "vacation"
    page = client.get(added.headers["location"]).text
    assert "Zapisano przerwę." in page and "Wyjazd: Zakopane" in page and "trwa teraz" in page

    pending = client.post("/journal/pause/remove", data={"csrf_token": _csrf(client), "start": data["start"],
                                                        "end": data["end"]},
                          headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert pending.status_code == 200 and "Usunąć tę przerwę?" in pending.text
    assert len(preferences.list_planned_pauses()) == 1
    removed = client.post("/journal/pause/remove", data={"csrf_token": _csrf(client), "start": data["start"],
                                                        "end": data["end"], "confirm": "yes"},
                          headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert removed.status_code == 303 and preferences.list_planned_pauses() == []


def test_journal_pause_rejects_forged_requests_and_bad_dates(tmp_path):
    client = TestClient(create_app(journal_path=tmp_path / "journal.jsonl"))

    forged = client.post("/journal/pause", data={"csrf_token": "x", "pause_type": "break", "start": "2026-10-28",
                                                 "end": "2026-10-28"}, headers={"Origin": "http://testserver"})
    bad = client.post("/journal/pause", data={"csrf_token": _csrf(client), "pause_type": "break",
                                              "start": "2026-10-30", "end": "2026-10-29"},
                      headers={"Origin": "http://testserver"})

    assert forged.status_code == 403
    assert bad.status_code == 400 and "przed jej początkiem" in bad.text
    assert preferences.list_planned_pauses() == []


def test_clash_banner_links_to_the_plan(tmp_path):
    client = TestClient(create_app(journal_path=tmp_path / "journal.jsonl"))

    page = client.get("/journal?pause=added&clash=2026-10-29,2026-11-01").text

    assert "Obecny plan ma treningi w dniach" in page
    assert 'href="/plan?week=2026-10-26"' in page
