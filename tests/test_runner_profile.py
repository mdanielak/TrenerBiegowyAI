# -*- coding: utf-8 -*-
"""Profil biegacza: poziom, decyzja tygodnia, dobór modułów promptu i bezpieczniki planu."""
from datetime import date, timedelta
from pathlib import Path

from ai.prompts import coach_prompt, modules_for
from services import plan as plan_service
from services.runner_profile import build_runner_profile, profile_lines

TODAY = date(2026, 11, 4)  # środa; poprzednie 4 tygodnie: 5.10–1.11
FLOORS = {"z1": 98, "z2": 120, "z3": 138, "z4": 156, "z5": 172}


def _runs(days_back, minutes, km=5.0, hr=130):
    return [{"date": f"{TODAY - timedelta(days=d)} 18:00", "type": "running/generic",
             "duration_min": minutes, "distance_km": km, "avg_hr": hr} for d in days_back]


def _profile(**extra):
    return {"age": 32, "weight_kg": 60, "height_cm": 165, "sex": "female", "hr_zone_floors": FLOORS,
            "target_distance": "5k", "target_date": "2027-03-01", **extra}


def _tester():
    """Osoba testująca: zegarek od dwóch miesięcy, 2-3 biegi tygodniowo po 30-40 min, cel 5 km."""
    return _runs([4, 6, 9, 11, 13, 16, 18, 20, 23, 25, 27, 30, 50, 55], 35)


def test_the_tester_is_a_beginner_with_5k_modules_and_no_author_data():
    runner = build_runner_profile(activities=_tester(), profile=_profile(running_since="under6"), today=TODAY)
    assert runner["level"] == "poczatkujacy" and runner["longest_min"] == 35
    assert modules_for(runner) == ["poziom/poczatkujacy", "cel/5km"]
    prompt = coach_prompt(runner, private_path=Path("brak.md"))
    assert "## Poziom: początkujący" in prompt and "## Cel: 5 km" in prompt and "półmaraton" not in prompt


def test_a_new_watch_trusts_the_years_of_running_from_the_wizard():
    runner = build_runner_profile(activities=_runs([3, 5, 8], 50), profile=_profile(running_since="over24"), today=TODAY)
    assert runner["short_history"] and runner["level"] == "regularny"


def test_a_long_standing_frequent_runner_is_advanced():
    runs = _runs(range(3, 31), 55, km=10.0) + _runs([7, 14, 21, 28], 100, km=18.0)
    runner = build_runner_profile(activities=runs, profile=_profile(running_since="over24", target_distance="hm"),
                                  today=TODAY)
    assert runner["level"] == "zaawansowany" and "cel/polmaraton" in modules_for(runner)


def test_weekly_decision_follows_resting_heart_rate_pain_and_last_week():
    base = dict(activities=_tester(), profile=_profile(running_since="6to24"), today=TODAY)
    last_week = {"workouts": [{"date": "2026-10-29", "type": "easy", "duration_min": 35},
                              {"date": "2026-10-31", "type": "long", "duration_min": 40}]}
    done = build_runner_profile(**base, previous_plan=last_week)
    assert done["adherence"] == 1.0 and done["decision"] == "doloz"
    assert build_runner_profile(**base, previous_plan=last_week,
                                rhr_trend={"recent": 56, "average": 50})["decision"] == "odpusc"
    assert build_runner_profile(**base, previous_plan=last_week, pain=True)["decision"] == "odpusc"
    hard = dict(base, activities=_runs([4, 6, 9, 11, 13, 16, 18, 20, 23, 25, 27, 30], 35, hr=150))
    assert build_runner_profile(**hard, previous_plan=last_week)["decision"] == "utrzymaj"


def test_coming_back_after_a_break_counts_as_a_beginner():
    runs = _runs([5, 8], 30) + _runs(range(40, 70, 2), 60)
    runner = build_runner_profile(activities=runs, profile=_profile(running_since="over24"), today=TODAY)
    assert runner["returning"] and runner["level"] == "poczatkujacy"
    assert "zdrowie/powrot-po-przerwie" in modules_for(runner)


def test_age_weight_and_health_notes_add_their_modules_and_lines():
    runner = build_runner_profile(activities=_tester(), today=TODAY, profile=_profile(
        running_since="under6", age=56, weight_kg=95, health_notes="kontuzja kolana w 2024"))
    assert {"zdrowie/wiek-50", "zdrowie/wysoka-waga", "zdrowie/kontuzje"} <= set(modules_for(runner))
    lines = "\n".join(profile_lines(runner))
    assert "BMI 34,9" in lines and "kobieta" in lines and "kontuzja kolana w 2024" in lines
    assert "DECYZJA TYGODNIA" in lines


def _context(runner):
    days = [{"date": str(date(2026, 11, 2) + timedelta(days=i)), "day": key, "available": True,
             "min_minutes": 20, "max_minutes": 120}
            for i, key in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"))]
    return {"week_start": "2026-11-02", "week_end": "2026-11-08", "week_days": days, "hr_zone_floors": FLOORS,
            "recent_activities": [], "runner": runner}


def test_beginners_get_no_hard_sessions_and_the_week_respects_the_volume_limit():
    runner = build_runner_profile(activities=_tester(), profile=_profile(running_since="under6"), today=TODAY)
    response = {"workouts": [
        {"date": "2026-11-03", "kind": "intervals", "name": "Interwały", "duration_min": 40, "hr_zone": 4,
         "pace_target": "5:00-5:10", "repetitions": 5, "work_seconds": 120, "rest_seconds": 90},
        {"date": "2026-11-05", "kind": "easy", "name": "Łatwy", "duration_min": 40, "hr_zone": 2},
        {"date": "2026-11-08", "kind": "long", "name": "Długi", "duration_min": 60, "distance_km": 8.0, "hr_zone": 2},
    ]}
    workouts = plan_service.normalize_plan(response, context=_context(runner))["workouts"]
    tuesday, thursday, sunday = workouts[1], workouts[3], workouts[6]
    assert tuesday["type"] == "easy" and "bez mocnych akcentów" in tuesday["notes"]
    limit = round(runner["max_week_minutes"] * 1.0)  # decyzja „utrzymaj” bez poprzedniego planu
    assert sum(w["duration_min"] or 0 for w in workouts if w["type"] != "rest") <= limit
    assert "limit czasu tygodnia" in sunday["notes"] and thursday["duration_min"] >= 20


def test_the_week_keeps_the_chosen_number_of_runs_and_trims_proportionally():
    runner = build_runner_profile(activities=_tester(), today=TODAY,
                                  profile=_profile(running_since="under6", training_frequency="3 treningi w tygodniu"))
    response = {"workouts": [
        {"date": str(date(2026, 11, 2) + timedelta(days=i)), "kind": "long" if i == 6 else "easy",
         "name": "Bieg", "duration_min": 60 if i == 6 else 40, "hr_zone": 2} for i in (0, 1, 3, 4, 6)]}
    workouts = plan_service.normalize_plan(response, context=_context(runner))["workouts"]
    runs = [w for w in workouts if w["type"] != "rest"]
    assert len(runs) == 3 and "wybrano 3 treningi w tygodniu" in workouts[0]["notes"]
    long_run = next(w for w in runs if w["type"] == "long")
    assert long_run["duration_min"] == max(w["duration_min"] for w in runs)  # długi zostaje najdłuższy
    assert sum(w["duration_min"] for w in runs) <= runner["max_week_minutes"]
