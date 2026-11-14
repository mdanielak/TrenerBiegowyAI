# -*- coding: utf-8 -*-
"""Bezpieczniki trenera: limit tygodnia, poziom, tętno spoczynkowych biegów, mocne dni z rzędu, gotowość."""
from datetime import date, timedelta

from services import plan as plan_service
from services.readiness import compute_readiness_breakdown, yesterday_load
from services.runner_profile import build_runner_profile, profile_lines, week_cap, week_reference

TODAY = date(2026, 11, 16)  # poniedziałek; ostatni pełny tydzień: 9–15.11
FLOORS = {"z1": 98, "z2": 120, "z3": 150, "z4": 160, "z5": 172}


def _run(days_back, minutes, hr=135, ate=None):
    return {"date": f"{TODAY - timedelta(days=days_back)} 18:00", "type": "running/generic",
            "duration_min": minutes, "distance_km": minutes / 6, "avg_hr": hr, "ate": ate}


def _weeks(totals):
    """Trzy biegi w każdym z czterech tygodni; ``totals`` od najstarszego do ostatniego tygodnia."""
    runs = []
    for weeks_back, total in zip((3, 2, 1, 0), totals):
        runs += [_run(7 * weeks_back + day, total / 3) for day in (1, 3, 5)]
    return runs


def _done_last_week():
    return {"workouts": [{"date": str(TODAY - timedelta(days=d)), "type": "easy", "duration_min": 50}
                         for d in (1, 3, 5)]}


def _profile(**extra):
    return {"running_since": "over24", "hr_zone_floors": FLOORS, **extra}


# --- Limit tygodnia ---------------------------------------------------------------------------

def test_one_big_week_a_month_ago_does_not_inflate_the_limit():
    runner = build_runner_profile(activities=_weeks([240, 150, 150, 150]), profile=_profile(), today=TODAY,
                                  previous_plan=_done_last_week())
    assert runner["decision"] == "doloz" and runner["week_reference_min"] == 150
    assert runner["week_cap_min"] == 165  # +10% wobec zwykłego tygodnia, a nie wobec 240


def test_an_easier_week_is_really_easier_than_the_last_one():
    runner = build_runner_profile(activities=_weeks([240, 150, 150, 150]), profile=_profile(), today=TODAY,
                                  previous_plan=_done_last_week(), pain=True)
    assert runner["decision"] == "odpusc" and runner["week_cap_min"] < 150


def test_steady_progress_is_not_cut_back():
    assert week_reference([120, 130, 140, 150]) == 150
    assert week_cap([120, 130, 140, 150], "doloz") == 165


def test_right_after_a_spike_the_week_stays_below_it():
    # Ostatni tydzień 240 przy zwykłych 150: dokładanie kolejnych 10% byłoby skokiem obciążenia.
    assert week_cap([150, 150, 150, 240], "doloz") == round(172.5 * 1.3) < 240


def test_a_missed_week_counts_as_zero_minutes():
    assert week_reference([150, 150, 0, 150]) == 150 and week_reference([0, 0, 0, 0]) is None


def test_the_model_sees_the_usual_week():
    runner = build_runner_profile(activities=_weeks([240, 150, 150, 150]), profile=_profile(), today=TODAY)
    lines = "\n".join(profile_lines(runner))
    assert "zwykły tydzień 150 min" in lines and f"cały tydzień najwyżej {runner['week_cap_min']} min" in lines


# --- Poziom -----------------------------------------------------------------------------------

def test_years_of_short_runs_are_not_a_beginner():
    runs = [_run(d, 40) for d in range(1, 29, 2)]
    assert build_runner_profile(activities=runs, profile=_profile(), today=TODAY)["level"] == "regularny"
    assert build_runner_profile(activities=runs, profile=_profile(running_since="6to24"),
                                today=TODAY)["level"] == "regularny"


def test_without_the_years_or_with_very_short_runs_it_stays_a_beginner():
    runs = [_run(d, 40) for d in range(1, 29, 2)]
    unknown = {k: v for k, v in _profile().items() if k != "running_since"}
    assert build_runner_profile(activities=runs, profile=unknown, today=TODAY)["level"] == "poczatkujacy"
    short = [_run(d, 25) for d in range(1, 29, 2)]
    assert build_runner_profile(activities=short, profile=_profile(), today=TODAY)["level"] == "poczatkujacy"


# --- Tętno spokojnych biegów ------------------------------------------------------------------

def _quality_weeks(quality_hr=165, ate=None):
    """Dwa akcenty i jeden spokojny bieg w tygodniu; spokojny w strefie 2."""
    runs = []
    for weeks_back in range(4):
        runs += [_run(7 * weeks_back + 1, 50), _run(7 * weeks_back + 3, 45, hr=quality_hr, ate=ate),
                 _run(7 * weeks_back + 5, 45, hr=quality_hr, ate=ate)]
    return runs


def _quality_plan():
    return {"workouts": [{"date": str(TODAY - timedelta(days=1)), "type": "easy", "duration_min": 50},
                         {"date": str(TODAY - timedelta(days=3)), "type": "intervals", "duration_min": 45},
                         {"date": str(TODAY - timedelta(days=5)), "type": "tempo", "duration_min": 45}]}


def test_planned_hard_sessions_do_not_count_as_too_hard_easy_runs():
    runner = build_runner_profile(activities=_quality_weeks(), profile=_profile(), today=TODAY,
                                  previous_plan=_quality_plan())
    # Oceniany jest tylko bieg, który w planie miał być spokojny — i był w strefie 2.
    assert runner["runs_above_z2"] == 0 and runner["easy_runs_with_hr"] == 1
    assert runner["decision"] == "doloz"


def test_an_easy_run_done_too_hard_still_counts():
    runs = _quality_weeks()
    runs[0]["avg_hr"] = 158  # spokojny bieg z poprzedniego tygodnia ze średnim tętnem w strefie 3
    runner = build_runner_profile(activities=runs, profile=_profile(), today=TODAY, previous_plan=_quality_plan())
    assert runner["runs_above_z2"] == 1


def test_hard_sessions_recognised_by_the_watch_do_not_count_either():
    runner = build_runner_profile(activities=_quality_weeks(ate=3.0), profile=_profile(), today=TODAY,
                                  previous_plan=_quality_plan())
    assert runner["runs_above_z2"] == 0 and runner["decision"] == "doloz"


# --- Opuszczone treningi ----------------------------------------------------------------------

def test_skipped_sessions_alone_keep_the_volume_instead_of_easing():
    runs = _weeks([150, 150, 150, 150])
    plan = {"workouts": [{"date": str(TODAY - timedelta(days=d)), "type": "easy", "duration_min": 50}
                         for d in (1, 2, 3, 4, 5, 6)]}  # 3 z 6 wykonane, w pełnej długości
    runner = build_runner_profile(activities=runs, profile=_profile(), today=TODAY, previous_plan=plan)
    assert runner["adherence"] == 0.5 and runner["decision"] == "utrzymaj"


def test_skipped_and_cut_short_sessions_ease_the_week():
    runs = _weeks([150, 150, 150, 150])
    plan = {"workouts": [{"date": str(TODAY - timedelta(days=d)), "type": "easy", "duration_min": 90}
                         for d in (1, 2, 3, 4, 5, 6)]}  # wykonane biegi po 50 min z planowanych 90
    runner = build_runner_profile(activities=runs, profile=_profile(), today=TODAY, previous_plan=plan)
    assert runner["shortened"] and runner["decision"] == "odpusc"


# --- Mocne dni z rzędu i długość akcentu ------------------------------------------------------

def _context(runner, max_quality=2):
    monday = date(2026, 11, 16)
    days = [{"date": str(monday + timedelta(days=i)), "day": key, "available": True,
             "min_minutes": 20, "max_minutes": 150}
            for i, key in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"))]
    return {"week_start": str(monday), "week_end": str(monday + timedelta(days=6)), "week_days": days,
            "hr_zone_floors": FLOORS, "recent_activities": [], "runner": runner, "max_quality_sessions": max_quality}


def _intervals(day, minutes=45):
    return {"date": day, "kind": "intervals", "name": "Odcinki", "duration_min": minutes, "hr_zone": 4,
            "pace_target": "4:40-4:50", "repetitions": 5, "work_seconds": 180, "rest_seconds": 120}


def _tempo(day, minutes=45):
    return {"date": day, "kind": "tempo", "name": "Tempo", "duration_min": minutes, "hr_zone": 3,
            "pace_target": "5:00-5:10"}


def _regular():
    return build_runner_profile(activities=_weeks([200, 200, 200, 200]), profile=_profile(), today=TODAY)


def test_two_hard_days_in_a_row_become_hard_then_easy():
    response = {"workouts": [_intervals("2026-11-17"), _tempo("2026-11-18"),
                             {"date": "2026-11-22", "kind": "long", "name": "Długi", "duration_min": 70, "hr_zone": 2}]}
    workouts = plan_service.normalize_plan(response, context=_context(_regular()))["workouts"]
    tuesday, wednesday, sunday = workouts[1], workouts[2], workouts[6]
    assert tuesday["type"] == "intervals" and tuesday["repetitions"] == 5
    assert wednesday["type"] == "easy" and wednesday["pace_target"] is None and "repetitions" not in wednesday
    assert "regeneracji" in wednesday["notes"] and wednesday["hr_zone"] == "Z2"
    assert sunday["type"] == "long"


def test_no_hard_session_the_day_after_the_long_run():
    response = {"workouts": [{"date": "2026-11-21", "kind": "long", "name": "Długi", "duration_min": 70, "hr_zone": 2},
                             _intervals("2026-11-22")]}
    workouts = plan_service.normalize_plan(response, context=_context(_regular()))["workouts"]
    assert workouts[5]["type"] == "long" and workouts[6]["type"] == "easy"


def test_hard_days_with_a_day_between_stay():
    response = {"workouts": [_intervals("2026-11-17"), _tempo("2026-11-19")]}
    workouts = plan_service.normalize_plan(response, context=_context(_regular()))["workouts"]
    assert workouts[1]["type"] == "intervals" and workouts[3]["type"] == "tempo"


def test_a_hard_session_is_not_longer_than_the_longest_recent_run():
    runner = _regular()
    response = {"workouts": [_tempo("2026-11-18", minutes=120)]}
    wednesday = plan_service.normalize_plan(response, context=_context(runner))["workouts"][2]
    assert wednesday["type"] == "tempo" and wednesday["duration_min"] == runner["longest_min"]


# --- Gotowość: wczorajszy trening -------------------------------------------------------------

def _health():
    return {"daily_health": [{"rhr": 50, "stress_avg": 20}], "sleep": [{"score": 92, "total_h": 8}],
            "hrv": [{"status": "BALANCED", "last_night": 75, "baseline_low": 67, "baseline_high": 82}]}


def _yesterday(**fields):
    return [{"date": "2026-11-15 18:00", "duration_min": 45, **fields}]


def test_yesterday_load_levels():
    assert yesterday_load([], "2026-11-16") == "rest"
    assert yesterday_load(_yesterday(te=2.8), "2026-11-16") == "light"
    assert yesterday_load(_yesterday(te=3.7), "2026-11-16") == "moderate"
    assert yesterday_load(_yesterday(ate=3.1), "2026-11-16") == "hard"
    assert yesterday_load(_yesterday(duration_min=100), "2026-11-16") == "hard"
    assert yesterday_load(_yesterday(te=4.5) + [{"date": "2026-11-14", "te": 1.0}], "2026-11-16") == "hard"


def test_a_hard_day_yesterday_lowers_an_otherwise_perfect_score():
    rested = compute_readiness_breakdown(_health(), rhr_baseline=50, activities=[], day="2026-11-16")
    tired = compute_readiness_breakdown(_health(), rhr_baseline=50, activities=_yesterday(ate=3.0), day="2026-11-16")
    assert rested["score"] == 10 and rested["level"] == "ready"
    assert tired["score"] < 9 and tired["yesterday_load"] == "hard"
    row = next(d for d in tired["details"] if d["metric"] == "Load")
    assert row["status"] == "FAIL" and row["points"] == 0 and "mocny trening" in row["message"]


def test_without_activities_the_score_is_unchanged_and_training_never_replaces_body_data():
    plain = compute_readiness_breakdown(_health(), rhr_baseline=50)
    assert all(d["metric"] != "Load" for d in plain["details"]) and plain["confidence"] == "high"
    nothing = compute_readiness_breakdown({}, activities=[], day="2026-11-16")
    assert nothing["level"] == "no_data" and nothing["score"] == 0
    assert all(d["metric"] != "Load" for d in nothing["details"])
