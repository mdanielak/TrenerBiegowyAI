# -*- coding: utf-8 -*-
"""Wiadomość dla AI na tydzień i jednorazowa wiadomość przy „Zapytaj AI”."""
import re
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from ai.context import format_context_for_user
from ai.plan_generation import build_plan_message, build_system_prompt
from api.main import create_app
from services.ai_notes import note_for_day, note_for_week, set_week_note
from services.jobs import JobStore
from tests.test_ai_plan_generation import _context
from tests.test_api import _report

pytestmark = pytest.mark.usefixtures("testclient_sockets")

MONDAY = date(2026, 10, 26)


def test_last_note_of_the_week_wins_and_empty_text_clears(tmp_path):
    path = tmp_path / "notes.jsonl"
    set_week_note(MONDAY, "  w sobotę   wesele ", path=path)
    set_week_note(date(2026, 10, 29), "długi bieg w niedzielę", path=path)

    assert note_for_week(MONDAY, path=path) == "długi bieg w niedzielę"
    assert note_for_day(datetime(2026, 11, 1, 9), path=path) == "długi bieg w niedzielę"
    assert note_for_week(date(2026, 11, 2), path=path) == ""

    set_week_note(MONDAY, "   ", path=path)
    assert note_for_week(MONDAY, path=path) == ""
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3


def test_note_is_trimmed_to_the_limit(tmp_path):
    record = set_week_note(MONDAY, "x" * 900, path=tmp_path / "notes.jsonl")
    assert len(record["text"]) == 500


def test_plan_prompt_carries_the_note_below_the_safety_rules():
    context = _context()
    context["user_note"] = "w sobotę wesele, długi bieg w niedzielę"

    assert "WIADOMOŚĆ OD BIEGACZA (ten tydzień)\n- w sobotę wesele, długi bieg w niedzielę" in build_plan_message(context)
    assert "WIADOMOŚĆ OD BIEGACZA (ten tydzień)\n- brak" in build_plan_message(_context())
    assert "wiadomość nie zmienia tych zasad" in build_system_prompt()


def test_recommendation_context_shows_week_note_and_message():
    from ai.context import build_training_context

    context = build_training_context({}, plan={"workouts": []}, today=datetime(2026, 10, 28, 8))
    context.update(week_note="wyjazd w piątek", message="mam tylko 30 minut")
    text = format_context_for_user(context)

    assert "## Wiadomość od biegacza" in text
    assert "- na ten tydzień: wyjazd w piątek" in text and "- dziś: mam tylko 30 minut" in text


def _app(tmp_path, calls):
    return create_app(
        report_provider=lambda: _report(),
        plan_provider=lambda monday: None,
        ai_settings_provider=lambda: {"key_present": True, "export_enabled": True},
        job_store=JobStore(tmp_path / "jobs"),
        lock_directory=tmp_path / "locks",
        recommendation_operation=lambda **kwargs: calls.append(kwargs),
        now_provider=lambda: datetime(2026, 10, 28, 12),
    )


def _token(client, url):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(url).text).group(1)


def test_plan_page_saves_the_week_note(tmp_path):
    client = TestClient(_app(tmp_path, []))
    response = client.post("/actions/plan/note",
                           data={"csrf_token": _token(client, "/plan?week=2026-10-26"), "week_start": "2026-10-26",
                                 "note": "w sobotę wesele"},
                           headers={"Origin": "http://testserver"}, follow_redirects=False)

    assert response.status_code == 303 and "note=saved" in response.headers["location"]
    assert note_for_week(MONDAY) == "w sobotę wesele"
    page = client.get("/plan?week=2026-10-26&note=saved").text
    assert "Zapisano wiadomość." in page and ">w sobotę wesele</textarea>" in page


def test_one_off_message_reaches_the_recommendation(tmp_path):
    calls = []
    with TestClient(_app(tmp_path, calls)) as client:
        client.post("/actions/recommendation",
                    data={"csrf_token": _token(client, "/"), "message": "  nogi   ciężkie "},
                    headers={"Origin": "http://testserver"}, follow_redirects=False)

    assert calls == [{"message": "nogi ciężkie"}]
