# -*- coding: utf-8 -*-
"""Testy dziennika samopoczucia."""
import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from services.journal import add_entry, entries_by_day, recent_entries, summary_for_ai, validate_entry

pytestmark = pytest.mark.usefixtures("testclient_sockets")

TODAY = date(2026, 10, 29)


def _entry(**overrides):
    values = dict(day=TODAY.isoformat(), feeling="good", rpe="4", pain_areas=[], pain_note="", note="", today=TODAY)
    values.update(overrides)
    return validate_entry(**values)


def test_validation_messages_are_for_people():
    with pytest.raises(ValueError, match="przyszłego"):
        _entry(day=(TODAY + timedelta(days=1)).isoformat())
    with pytest.raises(ValueError, match="RPE"):
        _entry(rpe="11")
    with pytest.raises(ValueError, match="samopoczucie|czujesz"):
        _entry(feeling="")
    with pytest.raises(ValueError, match="bólu"):
        _entry(pain_areas=["ucho"])
    assert _entry(rpe="")["rpe"] is None


def test_pain_note_is_kept_only_with_pain_and_notes_are_trimmed():
    assert _entry(pain_note="coś")["pain_note"] == ""
    entry = _entry(pain_areas=["calf"], pain_note="  lekko \n przy zbieganiu ", note="x" * 400)
    assert entry["pain_note"] == "lekko przy zbieganiu"
    assert len(entry["note"]) == 300


def test_file_is_append_only_and_the_last_entry_of_a_day_wins(tmp_path):
    path = tmp_path / "journal.jsonl"
    add_entry(_entry(feeling="poor"), path=path)
    add_entry(_entry(feeling="great"), path=path)

    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    assert entries_by_day(path=path)[TODAY.isoformat()]["feeling"] == "great"


def test_ai_summary_has_structured_fields_and_short_notes(tmp_path):
    path = tmp_path / "journal.jsonl"
    add_entry(_entry(day=(TODAY - timedelta(days=1)).isoformat(), rpe="6", pain_areas=["knee"], pain_note="po biegu"), path=path)
    add_entry(_entry(rpe="2", note="n" * 300), path=path)
    add_entry(_entry(day=(TODAY - timedelta(days=7)).isoformat()), path=path)

    summary = summary_for_ai(today=TODAY, path=path)

    assert summary["days_with_entries"] == 2
    assert summary["average_rpe"] == 4
    assert summary["pain_days"] == [{"date": "2026-10-28", "areas": ["kolano"], "note": "po biegu"}]
    assert len(summary["notes"][0]["note"]) == 120
    assert summary_for_ai(today=TODAY, path=tmp_path / "brak.jsonl") is None
    assert [e["date"] for e in recent_entries(today=TODAY, days=14, path=path)] == ["2026-10-29", "2026-10-28", "2026-10-22"]


def _csrf(client):
    page = client.get("/journal")
    return re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)


def test_journal_form_saves_an_entry(tmp_path):
    path = tmp_path / "journal.jsonl"
    client = TestClient(create_app(journal_path=path))
    token = _csrf(client)

    response = client.post("/journal", data={"csrf_token": token, "date": date.today().isoformat(), "feeling": "poor",
                                             "rpe": "7", "pain": ["calf", "foot"], "note": "ciężko"},
                           headers={"Origin": "http://testserver"}, follow_redirects=False)

    assert response.status_code == 303
    page = client.get("/journal?saved=1")
    assert "Zapisano wpis." in page.text
    assert "ból: łydka, stopa" in page.text
    assert entries_by_day(path=path)[date.today().isoformat()]["rpe"] == 7


def test_journal_rejects_missing_csrf_and_bad_input(tmp_path):
    path = tmp_path / "journal.jsonl"
    client = TestClient(create_app(journal_path=path))

    forged = client.post("/journal", data={"csrf_token": "x", "feeling": "good"}, headers={"Origin": "http://testserver"})
    assert forged.status_code == 403
    invalid = client.post("/journal", data={"csrf_token": _csrf(client), "date": date.today().isoformat(), "feeling": "good", "rpe": "99"},
                          headers={"Origin": "http://testserver"})
    assert invalid.status_code == 400 and "RPE to liczba od 1 do 10." in invalid.text
    assert not path.exists()


def test_replacing_entry_requires_confirmation_for_the_same_date(tmp_path):
    path = tmp_path / "journal.jsonl"
    client = TestClient(create_app(journal_path=path))
    day = date.today().isoformat()
    data = {"csrf_token": _csrf(client), "date": day, "feeling": "good", "note": "pierwszy"}
    assert client.post('/journal', data=data, headers={"Origin": "http://testserver"}, follow_redirects=False).status_code == 303
    data["note"] = "nowy"
    pending = client.post('/journal', data=data, headers={"Origin": "http://testserver"})
    assert "Potwierdź zastąpienie" in pending.text
    assert entries_by_day(path=path)[day]["note"] == "pierwszy"
    data.update(confirm="yes", confirm_date=day)
    assert client.post('/journal', data=data, headers={"Origin": "http://testserver"}, follow_redirects=False).status_code == 303
    assert entries_by_day(path=path)[day]["note"] == "nowy"
