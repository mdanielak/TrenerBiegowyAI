# -*- coding: utf-8 -*-
"""Strategia z kreatora: fazy z celu i ostatnich biegów w formacie, który czyta services.strategy."""
import re
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from services.strategy import parse_strategy
from services.strategy_builder import build_strategy, build_strategy_markdown, save_strategy
from tests.test_api_plan import _app

TODAY = date(2026, 11, 11)  # środa
PROFILE = {"target_distance": "hm", "target_date": "2027-04-10", "target_time": "1:55:00",
           "training_frequency": "4 treningi w tygodniu"}


def _runs(km_per_run=7.5, longest=13.8):
    days = [TODAY - timedelta(days=offset) for offset in range(1, 28, 2)]
    runs = [{"date": f"{day.isoformat()}T07:00:00", "type": "running", "distance_km": km_per_run} for day in days]
    runs[0]["distance_km"] = longest
    return runs


def test_generated_strategy_is_readable_by_the_parser_and_ends_on_race_day():
    strategy = parse_strategy(build_strategy_markdown(profile=PROFILE, activities=_runs(), today=TODAY))
    assert [phase.name for phase in strategy.phases] == [
        "Baza", "Budowanie", "Przygotowanie startowe", "Szczyt formy i odpoczynek przed startem"]
    assert strategy.phases[0].start == date(2026, 11, 9) and strategy.phases[-1].end == date(2027, 4, 10)
    for earlier, later in zip(strategy.phases, strategy.phases[1:]):
        assert later.start == earlier.end + timedelta(days=1)
    assert strategy.runs_per_week == (3, 4)
    assert strategy.long_run_target == strategy.phases[-2].long_km
    assert strategy.test_10k_seconds is not None
    assert strategy.phase_for(TODAY).name == "Baza"


def test_volume_starts_from_what_the_runner_actually_runs():
    low = parse_strategy(build_strategy_markdown(profile=PROFILE, activities=_runs(3, 5), today=TODAY))
    high = parse_strategy(build_strategy_markdown(profile=PROFILE, activities=_runs(12, 20), today=TODAY))
    assert low.phases[0].km[1] < high.phases[0].km[1]
    assert low.phases[0].km[1] <= 20  # ok. 11 km tygodniowo teraz: pierwsza faza nie skacze do 30
    tops = [phase.km[1] for phase in high.phases[:-1]]
    assert tops == sorted(tops)


@pytest.mark.parametrize(("change", "message"), [
    ({"target_distance": "fitness"}, "5 km"),
    ({"target_date": ""}, "datę zawodów"),
    ({"target_date": "2026-11-25"}, "za późno"),
])
def test_goals_without_a_sensible_plan_are_refused_in_plain_words(change, message):
    with pytest.raises(ValueError, match=message):
        build_strategy_markdown(profile={**PROFILE, **change}, activities=_runs(), today=TODAY)


def test_saving_keeps_the_previous_strategy_as_a_copy(tmp_path):
    path = tmp_path / "strategia.md"
    path.write_text("moja ręczna strategia", encoding="utf-8")
    save_strategy("nowa", path=path, now=datetime(2026, 11, 11, 9, 30))
    assert path.read_text(encoding="utf-8") == "nowa"
    assert (tmp_path / "strategia-poprzednia-20261111-093000.md").read_text(encoding="utf-8") == "moja ręczna strategia"


@pytest.mark.usefixtures("testclient_sockets")
def test_goal_page_builds_the_strategy_only_with_a_valid_form(tmp_path, monkeypatch):
    path = tmp_path / "strategia.md"
    monkeypatch.setattr("services.strategy.STRATEGY_PATH", path)
    race = (date.today() + timedelta(days=150)).isoformat()
    app = _app(tmp_path, profile_provider=lambda: {})
    with TestClient(app) as client:
        assert client.post("/goal/strategy").status_code == 403 and not path.exists()
    app = _app_with_goal(tmp_path, race)
    with TestClient(app) as client:
        token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/plan").text).group(1)
        response = client.post("/goal/strategy", data={"csrf_token": token}, follow_redirects=False,
                               headers={"Origin": "http://testserver"})
    assert response.status_code == 303 and response.headers["location"] == "/goal?strategy=created"
    assert parse_strategy(path.read_text(encoding="utf-8")).phases[-1].end.isoformat() == race


def _app_with_goal(tmp_path, race):
    from api.main import create_app
    from services.jobs import JobStore

    return create_app(profile_provider=lambda: {**PROFILE, "target_date": race},
                      job_store=JobStore(tmp_path / "jobs2"), lock_directory=tmp_path / "locks2",
                      ai_settings_provider=lambda: {})


def test_each_phase_shows_where_it_starts_and_steps_lead_to_the_peak():
    text = build_strategy_markdown(profile=PROFILE, activities=_runs(3, 5), today=TODAY)
    strategy = parse_strategy(text)
    base = strategy.phases[0]
    assert base.km[0] < base.km[1]  # baza zaczyna się od obecnego biegania, nie od szczytu
    assert "Kroki po drodze (zwykły tydzień):" in text


def test_the_parser_reads_a_flat_phase_written_as_about():
    from services.strategy import _KM, _LONG, _range
    assert _range(_KM.search("ok. 42 km")) == (42, 42)
    assert _range(_LONG.search("long ok. 20 km")) == (20, 20)
    assert _range(_KM.search("zwykle 17-42 km")) == (17, 42)


@pytest.mark.parametrize("profile", [
    PROFILE,
    {**PROFILE, "target_distance": "5k", "target_time": ""},
    {**PROFILE, "target_distance": "marathon", "target_time": "3:30:00", "target_date": "2027-10-10"},
])
def test_the_structure_equals_what_the_text_says(profile):
    text, structured = build_strategy(profile=profile, activities=_runs(), today=TODAY)
    assert structured == parse_strategy(text)  # jedna strategia, dwie postaci: tekst dla człowieka, JSON dla aplikacji


def test_the_app_reads_the_structure_and_falls_back_to_text_after_a_manual_edit(tmp_path):
    import os
    from services.strategy import load_strategy, structured_path
    text, structured = build_strategy(profile=PROFILE, activities=_runs(), today=TODAY)
    path = save_strategy(text, path=tmp_path / "strategia.md", structured=structured)
    assert structured_path(path).is_file() and load_strategy(path) == structured
    # Ręczna edycja tabeli: tekst nowszy niż struktura — wygrywa tekst.
    edited = text.replace("| Baza |", "| Baza wydłużona |")
    path.write_text(edited, encoding="utf-8")
    later = structured_path(path).stat().st_mtime + 5
    os.utime(path, (later, later))
    assert load_strategy(path).phases[0].name == "Baza wydłużona"
    # Zapis bez struktury (np. tekst z innego źródła) usuwa nieaktualny JSON.
    save_strategy(edited, path=path)
    assert not structured_path(path).exists()


def test_a_goal_too_far_for_the_time_left_is_named_plainly():
    beginner = {"running_since": "under6", "target_distance": "hm", "target_date": "2027-05-30",
                "training_frequency": "3 treningi"}
    runs = [{"date": f"{TODAY - timedelta(days=7 * week + day)} 07:00", "type": "running", "duration_min": 27,
             "distance_km": 3.8} for week in range(1, 9) for day in (1, 3, 6)]  # 3 × 27 min, jak osoba zaczynająca
    text = build_strategy_markdown(profile=beginner, activities=runs, today=TODAY)
    assert "Uwaga na termin" in text and "16 km" in text


def test_the_taper_long_run_is_a_share_of_the_peak_not_a_fixed_cut():
    text, structured = build_strategy(profile=PROFILE, activities=_runs(), today=TODAY)
    peak = structured.phases[-2].long_km[1]
    taper = structured.phases[-1].long_km
    assert taper == (max(round(peak * 0.6), 4), max(round(peak * 0.8), 5))
