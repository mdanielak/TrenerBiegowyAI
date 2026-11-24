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


@pytest.mark.parametrize(("frequency", "share"), [("3 treningi", 0.45), ("4 treningi", 0.35), ("6 treningów", 0.3)])
def test_the_strategy_long_run_share_follows_the_prompt(frequency, share):
    _, structured = build_strategy(profile={**PROFILE, "training_frequency": frequency}, activities=_runs(), today=TODAY)
    longest_now = 13.8  # _runs(): najdłuższy bieg — strategia nie skraca poniżej tego
    for phase in structured.phases[:-1]:
        allowed = max(round(phase.km[1] * share), min(16, round(phase.km[1] * 0.5)), 6, round(longest_now))
        assert phase.long_km[1] <= allowed and phase.long_km[1] <= max(round(phase.km[1] * 0.5), round(longest_now))


def _weekly(pattern, pace, weeks=12):
    return [{"date": f"{TODAY - timedelta(days=7 * week + day)} 07:00", "type": "running", "duration_min": minutes,
             "distance_km": round(minutes / pace, 2)} for week in range(1, weeks + 1) for day, minutes in pattern]


def test_a_prepared_runner_never_gets_a_shorter_long_run_or_a_false_date_warning():
    marathoner = _weekly([(0, 50), (1, 70), (2, 60), (3, 75), (4, 50), (6, 150)], 5.0)  # długi 150 min = 30 km
    text, structured = build_strategy(activities=marathoner, today=TODAY, profile={
        "running_since": "over24", "target_distance": "marathon", "target_date": "2027-06-20",
        "target_time": "3:20:00", "training_frequency": "6 treningów"})
    assert "Uwaga na termin" not in text
    assert all(phase.long_km[0] >= 30 for phase in structured.phases[:-1])  # nie krócej niż dziś
    half = _weekly([(1, 45), (2, 50), (4, 45), (6, 80)], 5.8)  # długi 80 min ≈ 13,8 km
    text, structured = build_strategy(activities=half, today=TODAY, profile={
        "running_since": "6to24", "target_distance": "hm", "target_date": "2027-06-20",
        "target_time": "1:55:00", "training_frequency": "4 treningi"})
    assert "Uwaga na termin" not in text and structured.phases[-2].long_km[1] >= 14


def test_the_long_run_never_exceeds_half_the_week_and_a_marathoner_can_grow_to_the_goal():
    beginner = _weekly([(1, 25), (3, 25), (6, 30)], 7.2, weeks=8)
    _, structured = build_strategy(activities=beginner, today=TODAY, profile={
        "running_since": "under6", "target_distance": "hm", "target_date": "2027-05-30", "training_frequency": "3 treningi"})
    for phase in structured.phases[:-1]:
        assert phase.long_km[1] <= max(int(phase.km[1] * 0.5), 6)
    marathoner = _weekly([(0, 50), (1, 70), (2, 60), (3, 75), (4, 50), (6, 150)], 5.0)
    _, structured = build_strategy(activities=marathoner, today=TODAY, profile={
        "running_since": "over24", "target_distance": "marathon", "target_date": "2027-06-20",
        "training_frequency": "6 treningów"})
    assert structured.phases[-2].long_km[1] >= 32  # dochodzi do celu dla poziomu, nie stoi na obecnych 30 km


def test_beginner_5k_starts_from_real_long_run_without_5km_floor():
    beginner_5k = _weekly([(1, 20), (3, 20), (6, 20)], 8.0, weeks=6)  # ~2,5 km na bieg
    _, structured = build_strategy(activities=beginner_5k, today=TODAY, profile={
        "running_since": "under6", "target_distance": "5k", "target_date": "2027-02-28", "training_frequency": "3 treningi"})
    assert structured.phases[0].long_km[0] < 5


def test_slow_marathoner_strategy_respects_three_hour_long_run_ceiling():
    slow_marathoner = _weekly([(1, 45), (2, 45), (4, 45), (6, 120)], 7.5, weeks=10)  # 7:30/km -> 3 h = 24 km
    text, structured = build_strategy(activities=slow_marathoner, today=TODAY, profile={
        "running_since": "over24", "target_distance": "marathon", "target_date": "2027-08-15",
        "training_frequency": "4 treningi"})
    assert structured.phases[-2].long_km[1] <= 24
    assert "3 godziny" in text


def test_marathon_4h_riegel_gives_realistic_10k_test():
    marathoner = _weekly([(0, 50), (1, 70), (2, 60), (3, 75), (4, 50), (6, 150)], 5.2)
    _, structured = build_strategy(activities=marathoner, today=TODAY, profile={
        "running_since": "over24", "target_distance": "marathon", "target_date": "2027-06-20",
        "target_time": "4:00:00", "training_frequency": "6 treningów"})
    assert structured.test_10k_seconds[1] < 50 * 60 + 30


def test_ambitious_5k_and_10k_generate_5k_check_criterion_and_28w_beginner_hm_works():
    regular_5k = _weekly([(1, 40), (3, 45), (5, 35), (6, 60)], 5.0, weeks=8)
    text_5k, s_5k = build_strategy(activities=regular_5k, today=TODAY, profile={
        "running_since": "6to24", "target_distance": "5k", "target_date": "2027-03-15",
        "target_time": "21:00", "training_frequency": "4 treningi"})
    assert s_5k.test_5k_seconds is not None and s_5k == parse_strategy(text_5k)
    text_10k, s_10k = build_strategy(activities=regular_5k, today=TODAY, profile={
        "running_since": "6to24", "target_distance": "10k", "target_date": "2027-04-15",
        "target_time": "44:00", "training_frequency": "4 treningi"})
    assert s_10k.test_5k_seconds is not None and s_10k == parse_strategy(text_10k)

    beginner_hm = _weekly([(1, 35), (3, 35), (6, 45)], 7.0, weeks=6)  # ~16 km/tydz., long 6,4 km
    text_hm, s_hm = build_strategy(activities=beginner_hm, today=TODAY, profile={
        "running_since": "under6", "target_distance": "hm", "target_date": "2027-06-20",
        "training_frequency": "3 treningi"})
    assert s_hm.phases[-2].long_km[1] >= 16 and "Uwaga na termin" not in text_hm
