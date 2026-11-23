# -*- coding: utf-8 -*-
"""Bezpieczniki trenera: limit tygodnia, poziom, tętno spoczynkowych biegów, mocne dni z rzędu, gotowość."""
from datetime import date, timedelta

import pytest

from services import plan as plan_service
from services.readiness import compute_readiness_breakdown, yesterday_load
from services.runner_profile import build_runner_profile, profile_lines
from services.week_decision import week_cap, week_reference

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
    assert runner["week_cap_min"] == 172  # +15% wobec zwykłego tygodnia (150), a nie wobec 240


def test_an_easier_week_is_really_easier_than_the_last_one():
    runner = build_runner_profile(activities=_weeks([240, 150, 150, 150]), profile=_profile(), today=TODAY,
                                  previous_plan=_done_last_week(), pain=True)
    assert runner["decision"] == "regeneracja" and runner["week_cap_min"] < 150


def test_steady_progress_is_not_cut_back():
    assert week_reference([120, 130, 140, 150]) == 150
    assert week_cap([120, 130, 140, 150], "doloz") == 172


def test_right_after_a_spike_the_week_stays_below_it():
    # Ostatni tydzień 240 przy zwykłych 150: dokładanie kolejnych 10% byłoby skokiem obciążenia.
    assert week_cap([150, 150, 150, 240], "doloz") == round(172.5 * 1.3) < 240
    assert week_cap([100, 100, 100, 300], "doloz") == 195  # tygodnia-skoku nie powtarza się w całości


def _history(totals, hr=135):
    """Trzy biegi w tygodniu; ``totals``: {tygodni wstecz: minuty}, 0 = ostatni pełny tydzień, brak = bez biegów."""
    return [_run(7 * weeks_back + day, total / 3, hr=hr) for weeks_back, total in totals.items() if total
            for day in (1, 3, 5)]


UNEVEN = {3: 60, 2: 0, 1: 40, 0: 120}  # nierówne tygodnie z jednym pustym
EARLIER = {weeks_back: 200 for weeks_back in range(4, 12)}  # wcześniej regularnie 200 min


def _missed_plan():
    """Poprzedni plan z trzema treningami, z których żaden nie został wykonany."""
    return {"workouts": [{"date": str(TODAY - timedelta(days=d)), "type": "easy", "duration_min": 40}
                         for d in (2, 4, 6)]}


def test_with_a_bigger_past_a_missed_week_does_not_cut_below_last_week():
    # Tętno za wysokie: bez szybkiego powrotu, ale też bez cięcia poniżej przebiegniętych 120 min.
    runner = build_runner_profile(activities=_history({**EARLIER, **UNEVEN}, hr=160), profile=_profile(),
                                  today=TODAY)
    assert runner["decision"] == "utrzymaj" and runner["week_cap_min"] == 120


def test_without_history_a_jump_week_is_still_protected():
    # 120 min po 60, 0 i 40: to największy znany tydzień, więc ochrona przed skokiem zostaje.
    runner = build_runner_profile(activities=_history(UNEVEN), profile=_profile(), today=TODAY)
    assert runner["week_cap_min"] == 78  # 1,3 × największy z wcześniejszych tygodni (60 min)


def test_coming_back_to_an_earlier_volume_grows_faster():
    runner = build_runner_profile(activities=_history({**EARLIER, **UNEVEN}), profile=_profile(), today=TODAY)
    assert runner["earlier_week_min"] == 200 and runner["comeback"] is True
    assert runner["week_cap_min"] == 150  # +25% wobec ostatnich 120 min, w drodze do 200


def test_the_comeback_never_goes_above_the_earlier_usual_week():
    earlier = {weeks_back: 130 for weeks_back in range(4, 12)}
    runner = build_runner_profile(activities=_history({**earlier, **UNEVEN}), profile=_profile(), today=TODAY)
    assert runner["week_cap_min"] == 130


def test_no_fast_comeback_after_skipped_sessions():
    runner = build_runner_profile(activities=_history({**EARLIER, **UNEVEN}), profile=_profile(), today=TODAY,
                                  previous_plan=_missed_plan())
    assert runner["decision"] == "utrzymaj" and runner["comeback"] is False and runner["week_cap_min"] == 120


def test_an_irregular_past_is_not_an_earlier_volume():
    earlier = {4: 90, 6: 90, 9: 90}  # trzy tygodnie z ośmiu
    runner = build_runner_profile(activities=_history({**earlier, 3: 40, 2: 40, 1: 40, 0: 40}),
                                  profile=_profile(), today=TODAY)
    assert runner["earlier_week_min"] is None and runner["week_cap_min"] == 44


def test_an_easier_week_stays_easier_even_with_a_bigger_past():
    runner = build_runner_profile(activities=_history({**EARLIER, **UNEVEN}), profile=_profile(), today=TODAY,
                                  pain=True)
    assert runner["decision"] == "regeneracja" and runner["week_cap_min"] < 120


def test_after_a_long_break_there_is_no_fast_comeback():
    earlier = {weeks_back: 200 for weeks_back in range(5, 12)}  # potem 4 tygodnie bez biegania
    runs = _history(earlier) + [_run(2, 40)]
    runner = build_runner_profile(activities=runs, profile=_profile(), today=TODAY)
    assert runner["returning"] and runner["comeback"] is False and runner["week_cap_min"] == 40


def test_the_model_is_told_the_comeback_in_the_decision_itself():
    runner = build_runner_profile(activities=_history({**EARLIER, **UNEVEN}), profile=_profile(), today=TODAY)
    lines = "\n".join(profile_lines(runner))
    assert "wcześniej (5–12 tygodni temu) zwykły tydzień 200 min" in lines
    assert "DECYZJA TYGODNIA: odbuduj — powrót do znanej objętości" in lines and "bez dokładania" not in lines
    assert "cały tydzień najwyżej 150 min" in lines
    plain = "\n".join(profile_lines(build_runner_profile(activities=_history(UNEVEN), profile=_profile(),
                                                         today=TODAY)))
    assert "wcześniej" not in plain and "powrót do znanej" not in plain


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
    """Regularnie 4 razy w tygodniu: przy dwóch akcentach w ustawieniach oba są dozwolone."""
    runs = [_run(7 * week + day, 50) for week in range(4) for day in (1, 2, 4, 6)]
    return build_runner_profile(activities=runs, profile=_profile(), today=TODAY)


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


def test_a_request_to_the_coach_raises_the_week_limit_by_20_percent_except_when_easing_off():
    week = [120, 125, 125, 125]
    assert week_cap(week, "utrzymaj") == 138  # 125 × 1,1
    assert week_cap(week, "utrzymaj", request=True) == 165  # sufit o 20% wyżej
    assert week_cap(week, "odpusc", request=True) == week_cap(week, "odpusc")  # zmęczenie nie jest do negocjacji


def test_the_long_run_grows_by_about_ten_percent_with_a_five_minute_minimum():
    from services.week_decision import long_run_limit
    plain = {"decision": "utrzymaj"}
    assert (long_run_limit(plain, 30), long_run_limit(plain, 67), long_run_limit(plain, 120)) == (35, 74, 132)
    assert long_run_limit({"user_request": True, "decision": "utrzymaj"}, 67) == 77  # prośba: +15%
    assert long_run_limit({"user_request": True, "decision": "odpusc"}, 67) == 50  # lekki tydzień: długi krótszy
    assert long_run_limit(plain, 170) == 180 and long_run_limit(plain, 200) == 200  # sufit 3 h, bez skracania zrobionego


# --- Pięć stopni decyzji tygodnia ---------------------------------------------------------------

def test_resting_heart_rate_picks_the_lighter_or_the_regeneration_step():
    def decision(up):
        trend = {"recent": 50 + up, "average": 50}
        return build_runner_profile(activities=_weeks([100, 100, 100, 100]), profile=_profile(), today=TODAY,
                                    previous_plan=_done_last_week(), rhr_trend=trend)["decision"]
    assert (decision(4), decision(5), decision(7), decision(8)) == ("doloz", "odpusc", "odpusc", "regeneracja")


def test_three_rising_weeks_in_a_row_end_with_a_lighter_week_then_a_steady_one():
    plan = _done_last_week()
    rising = build_runner_profile(activities=_weeks([100, 108, 117, 126]), profile=_profile(), today=TODAY,
                                  previous_plan=plan)
    assert (rising["decision"], rising["decision_cause"]) == ("odpusc", "step_back")
    after = build_runner_profile(activities=_weeks([108, 117, 126, 95]), profile=_profile(), today=TODAY,
                                 previous_plan=plan)
    assert (after["decision"], after["decision_cause"]) == ("utrzymaj", "stabilise")
    ordinary = build_runner_profile(activities=_weeks([100, 110, 100, 105]), profile=_profile(), today=TODAY,
                                    previous_plan=plan)
    assert ordinary["decision"] == "doloz"  # zwykłe wahania nie są cofnięciem


def test_the_weeks_before_the_race_do_not_grow_and_the_race_week_is_light():
    def decision(days):
        race = (TODAY + timedelta(days=days)).isoformat()
        runner = build_runner_profile(activities=_weeks([100, 100, 100, 100]), profile=_profile(target_date=race),
                                      today=TODAY, previous_plan=_done_last_week())
        return runner["decision"], runner["decision_cause"]
    assert decision(60) == ("doloz", "ready")
    assert decision(17) == ("utrzymaj", "before_taper")
    assert decision(10) == ("odpusc", "taper")
    assert decision(3) == ("odpusc", "race_week")
    assert decision(-2) == ("odpusc", "after_race")


def test_the_taper_cuts_volume_by_the_literature_and_keeps_intensity():
    from ai.prompts import modules_for

    def runner(days):
        race = (TODAY + timedelta(days=days)).isoformat()
        return build_runner_profile(activities=_weeks([100, 100, 100, 100]), profile=_profile(target_date=race),
                                    today=TODAY, previous_plan=_done_last_week())
    week_before, race_week = runner(10), runner(3)
    assert (week_before["week_cap_min"], race_week["week_cap_min"]) == (80, 55)
    assert "zdrowie/regeneracja-i-przemeczenie" not in modules_for(race_week)
    assert "intensywność zostaje" in "\n".join(profile_lines(week_before))
    assert "około 80% zwykłego tygodnia (ok. 80 min)" in "\n".join(profile_lines(week_before))


def test_a_comeback_to_known_volume_is_its_own_step():
    runner = build_runner_profile(activities=_history({**EARLIER, **UNEVEN}), profile=_profile(), today=TODAY)
    assert runner["decision"] == "odbuduj" and runner["comeback"] is True


def test_a_request_does_not_lift_the_light_steps_and_stays_below_the_known_volume_when_rebuilding():
    asked = build_runner_profile(activities=_weeks([100, 100, 100, 100]), profile=_profile(), today=TODAY,
                                 previous_plan=_done_last_week(), pain=True, user_request=True)
    plain = build_runner_profile(activities=_weeks([100, 100, 100, 100]), profile=_profile(), today=TODAY,
                                 previous_plan=_done_last_week(), pain=True)
    assert asked["decision"] == "regeneracja" and asked["week_cap_min"] == plain["week_cap_min"]
    rebuilding = build_runner_profile(activities=_history({**EARLIER, **UNEVEN}), profile=_profile(), today=TODAY,
                                      user_request=True)
    assert rebuilding["week_cap_min"] <= rebuilding["earlier_week_min"]



# --- Punkty 3–5 oceny trenerskiej ----------------------------------------------------------------

def _hrv(weekly, low=60, status="BALANCED", days_ago=0):
    return [{"date": str(TODAY - timedelta(days=days_ago)), "weekly_avg": weekly, "last_night": weekly,
             "baseline_low": low, "baseline_high": 75, "status": status}]


def test_low_hrv_blocks_adding_and_with_a_higher_resting_rate_lightens_the_week():
    def runner(hrv, up=0):
        return build_runner_profile(activities=_weeks([100, 100, 100, 100]), profile=_profile(), today=TODAY,
                                    previous_plan=_done_last_week(), hrv=hrv,
                                    rhr_trend={"recent": 50 + up, "average": 50})
    assert runner(_hrv(66))["decision"] == "doloz"
    low = runner(_hrv(55))
    assert (low["decision"], low["decision_cause"]) == ("utrzymaj", "hrv_low")
    assert "HRV: średnia z tygodnia 55 ms" in "\n".join(profile_lines(low))
    assert runner(_hrv(55), up=3)["decision"] == "odpusc"
    assert runner(_hrv(55, days_ago=10))["decision"] == "doloz"  # stary pomiar nic nie mówi o dziś


def test_easy_runs_at_the_top_of_zone_two_are_flagged_for_the_coach_without_changing_the_week():
    floors_z3 = FLOORS["z3"]
    runs = [_run(day, 40, hr=floors_z3 - 2) for day in (1, 3, 5, 8, 10, 12)]
    runner = build_runner_profile(activities=runs, profile=_profile(), today=TODAY)
    lines = "\n".join(profile_lines(runner))
    assert runner["runs_near_z2_top"] == runner["easy_runs_with_hr"] and runner["runs_above_z2"] == 0
    assert "przy samej górnej granicy strefy 2" in lines


def test_a_goal_written_only_as_a_name_still_reaches_the_coach():
    from ai.prompts import modules_for
    from services.runner_profile import goal_distance
    assert goal_distance({"target_race": "półmaraton"}) == "hm"
    assert goal_distance({"target_race": "Bieg po zdrowie"}) is None
    assert goal_distance({"target_distance": "10k", "target_race": "półmaraton"}) == "10k"
    runner = build_runner_profile(activities=_weeks([100, 100, 100, 100]), profile=_profile(target_race="półmaraton"),
                                  today=TODAY, previous_plan=_done_last_week())
    assert "cel/polmaraton" in modules_for(runner)


def test_a_planned_step_back_week_is_not_described_as_fatigue():
    from ai.prompts import modules_for
    runner = build_runner_profile(activities=_weeks([100, 108, 117, 126]), profile=_profile(), today=TODAY,
                                  previous_plan=_done_last_week())
    assert runner["decision_cause"] == "step_back"
    assert "zdrowie/regeneracja-i-przemeczenie" not in modules_for(runner)
    assert "tydzień cofnięcia" in "\n".join(profile_lines(runner))


def test_the_strategy_starts_from_regular_running_not_from_a_short_pause():
    from services.strategy_builder import recent_volume
    regular = [_run(d, 50) for d in (2, 4, 6, 9, 11, 13)]  # 6 biegów po 5 km w ostatnich dwóch tygodniach
    for run in regular:
        run["distance_km"] = 5.0
    paused_runs = regular + [dict(_run(27, 50), distance_km=5.0)]  # potem 14 dni przerwy wcześniej
    weekly, _ = recent_volume(paused_runs, TODAY)
    assert weekly > 35 / 4  # średnia nie dzieli przez puste tygodnie przerwy


@pytest.mark.parametrize(("distance", "days", "expected"), [
    ("5k", 3, ("odpusc", "race_week", 75)),
    ("5k", 10, ("utrzymaj", "before_taper", None)),   # przy 5 km tylko tydzień startu jest lżejszy
    ("10k", 10, ("odpusc", "taper", 85)),
    ("hm", 10, ("odpusc", "taper", 80)),
    ("marathon", 3, ("odpusc", "race_week", 50)),
    ("marathon", 10, ("odpusc", "taper", 70)),
    ("marathon", 17, ("odpusc", "taper", 85)),        # maraton: trzy tygodnie zmniejszania
    ("marathon", 24, ("utrzymaj", "before_taper", None)),
])
def test_the_taper_depends_on_the_race_distance(distance, days, expected):
    race = (TODAY + timedelta(days=days)).isoformat()
    runner = build_runner_profile(activities=_weeks([100, 100, 100, 100]), today=TODAY, previous_plan=_done_last_week(),
                                  profile=_profile(target_date=race, target_distance=distance))
    assert (runner["decision"], runner["decision_cause"], runner["taper_percent"]) == expected
    if expected[2]:
        assert runner["week_cap_min"] == expected[2]  # zwykły tydzień 100 min


def test_after_a_marathon_the_first_week_is_regeneration_and_the_second_lighter():
    def runner(days_after):
        race = (TODAY - timedelta(days=days_after)).isoformat()
        return build_runner_profile(activities=_weeks([100, 100, 100, 100]), today=TODAY,
                                    previous_plan=_done_last_week(),
                                    profile=_profile(target_date=race, target_distance="marathon"))
    assert runner(3)["decision"] == "regeneracja" and runner(10)["decision"] == "odpusc"


def test_a_new_watch_still_gets_a_week_limit_from_the_days_it_has_seen():
    runs = [_run(day, 60) for day in (2, 3, 4, 5, 6)]  # jeden tydzień danych, 300 min
    runner = build_runner_profile(activities=runs, today=TODAY, profile=_profile())
    assert runner["short_history"] and runner["week_cap_min"] == 330
    assert runner["decision"] != "doloz"


def test_yesterday_load_is_judged_against_the_runners_own_longest_run():
    from services.readiness import yesterday_load
    day = "2026-11-16"
    def runs(longest, yesterday):
        history = [{"date": f"2026-11-{d:02d} 07:00", "type": "running", "duration_min": longest} for d in (2, 9)]
        return history + [{"date": "2026-11-15 07:00", "type": "running", "duration_min": yesterday}]
    assert yesterday_load(runs(150, 75), day) == "light"      # maratończyk: 75 min spokojnie to zwykły bieg
    assert yesterday_load(runs(150, 120), day) == "moderate"
    assert yesterday_load(runs(150, 150), day) == "hard"      # długi bieg
    assert yesterday_load(runs(30, 80), day) == "moderate"    # początkująca: progi jak dotąd (75 i 90 min)
    assert yesterday_load(runs(30, 95), day) == "hard"


# --- Znaleziska niezależnej recenzji (straznik-limitow, 2026-11-23) -------------------------------------

def test_pain_means_no_quality_and_no_long_run_and_a_shorter_long_limit():
    from services.runner_profile import quality_sessions_limit
    runner = build_runner_profile(activities=_weeks([200, 200, 200, 200]), profile=_profile(), today=TODAY,
                                  previous_plan=_done_last_week(), pain=True)
    assert runner["decision"] == "regeneracja" and quality_sessions_limit(runner, 2) == 0
    response = {"workouts": [_intervals("2026-11-18"),
                             {"date": "2026-11-22", "kind": "long", "name": "Długi", "duration_min": 88, "hr_zone": 2}]}
    workouts = plan_service.normalize_plan(response, context=_context(runner, max_quality=2))["workouts"]
    assert all(w["type"] not in ("intervals", "tempo", "threshold", "long") for w in workouts)
    from services.week_decision import long_run_limit
    assert long_run_limit(runner, 80) == 48  # regeneracja: 60% najdłuższego, bez wzrostu


def test_after_the_race_the_race_itself_is_not_the_longest_run():
    race = TODAY - timedelta(days=1)  # niedziela, maraton 205 min
    runs = _weeks([300, 300, 300, 300]) + [dict(_run(1, 205), date=f"{race} 09:00")]
    runner = build_runner_profile(activities=runs, today=TODAY, previous_plan=_done_last_week(),
                                  profile=_profile(target_date=str(race), target_distance="marathon"))
    from services.week_decision import long_run_limit
    assert runner["decision"] == "regeneracja" and runner["longest_min"] < 205
    assert long_run_limit(runner, runner["longest_min"]) < runner["longest_min"]


def test_a_plan_made_on_sunday_for_next_week_uses_next_weeks_taper():
    sunday = TODAY - timedelta(days=1)
    race = TODAY + timedelta(days=6)  # niedziela planowanego tygodnia
    profile = _profile(target_date=str(race), target_distance="marathon")
    planned = build_runner_profile(activities=_weeks([300, 300, 300, 300]), profile=profile, today=sunday,
                                   previous_plan=_done_last_week(), plan_monday=TODAY)
    assert (planned["decision_cause"], planned["taper_percent"]) == ("race_week", 50)


def test_a_rest_day_keeps_the_strength_session_even_when_running_is_not_available():
    runner = _regular()
    context = _context(runner)
    context["week_days"][2]["available"] = False  # środa bez czasu na bieganie
    response = {"workouts": [{"date": "2026-11-18", "kind": "rest", "name": "Siła 15 min",
                              "description": "2 × 12 mostków biodrowych, 3 × 10 wspięć na palce."}]}
    wednesday = plan_service.normalize_plan(response, context=context)["workouts"][2]
    assert wednesday["type"] == "rest" and "mostków" in wednesday["description"]


def test_the_week_limit_is_hard_even_with_the_twenty_minute_floor():
    runner = _regular()
    runner["week_cap_min"] = 39
    response = {"workouts": [{"date": f"2026-11-{d}", "kind": "easy", "name": "Łatwy", "duration_min": 20, "hr_zone": 2}
                             for d in (17, 19, 21)]}
    workouts = plan_service.normalize_plan(response, context=_context(runner))["workouts"]
    assert sum(w["duration_min"] or 0 for w in workouts if w["type"] != "rest") <= 39


def test_no_quality_session_on_monday_after_sundays_long_run():
    context = _context(_regular(), max_quality=2)
    context["hard_day_before"] = str(TODAY - timedelta(days=1))
    monday = plan_service.normalize_plan({"workouts": [_intervals(str(TODAY))]}, context=context)["workouts"][0]
    assert monday["type"] == "easy" and "regeneracji" in monday["notes"]


def test_race_day_is_a_start_and_does_not_count_toward_the_limits():
    context = _context(_regular())
    context.update(race_date="2026-11-22", race_name="maraton")
    response = {"workouts": [{"date": "2026-11-22", "kind": "long", "name": "Maraton", "duration_min": 210, "hr_zone": 3}]}
    sunday = plan_service.normalize_plan(response, context=context)["workouts"][6]
    assert sunday["type"] == "rest" and sunday["name"] == "Start: maraton" and sunday["duration_min"] is None


# --- Ponowna recenzja (straznik-limitow): pozostałe luki ------------------------------------------------

def test_in_a_light_week_an_easy_run_cannot_be_longer_than_the_long_run_limit():
    from services.week_decision import easy_run_limit, long_run_limit
    pain = build_runner_profile(activities=_weeks([200, 200, 200, 200]), profile=_profile(), today=TODAY,
                                previous_plan=_done_last_week(), pain=True)
    assert easy_run_limit(pain, 80) == long_run_limit(pain, 80) == 48
    lines = "\n".join(profile_lines(pain))
    assert "bieg łatwy i akcent najwyżej" in lines
    after = {"decision": "regeneracja", "decision_cause": "after_race"}
    assert easy_run_limit(after, 150) == 45  # tydzień po maratonie: krótko


def test_the_hard_week_limit_shortens_before_it_removes_runs():
    runner = _regular()
    runner["week_cap_min"] = 150
    response = {"workouts": [
        {"date": "2026-11-16", "kind": "easy", "name": "Łatwy", "duration_min": 30, "hr_zone": 2},
        {"date": "2026-11-17", "kind": "easy", "name": "Łatwy", "duration_min": 25, "hr_zone": 2},
        {"date": "2026-11-18", "kind": "tempo", "name": "Tempo", "duration_min": 45, "hr_zone": 3, "pace_target": "4:45-4:50"},
        {"date": "2026-11-19", "kind": "easy", "name": "Łatwy", "duration_min": 25, "hr_zone": 2},
        {"date": "2026-11-20", "kind": "easy", "name": "Łatwy", "duration_min": 20, "hr_zone": 2},
        {"date": "2026-11-22", "kind": "long", "name": "Długi", "duration_min": 40, "hr_zone": 2}]}
    workouts = plan_service.normalize_plan(response, context=_context(runner))["workouts"]
    runs = [w for w in workouts if w["type"] != "rest"]
    assert len(runs) == 6 and sum(w["duration_min"] for w in runs) <= 150  # liczba biegów zostaje


def test_a_tiny_limit_keeps_two_runs_and_the_long_run_is_not_shorter_than_easy_ones():
    runner = _regular()
    runner["week_cap_min"] = 39
    response = {"workouts": [{"date": "2026-11-17", "kind": "easy", "name": "Łatwy", "duration_min": 20, "hr_zone": 2},
                             {"date": "2026-11-19", "kind": "easy", "name": "Łatwy", "duration_min": 20, "hr_zone": 2},
                             {"date": "2026-11-22", "kind": "long", "name": "Długi", "duration_min": 25, "hr_zone": 2}]}
    workouts = plan_service.normalize_plan(response, context=_context(runner))["workouts"]
    runs = [w for w in workouts if w["type"] != "rest"]
    assert len(runs) == 2 and sum(w["duration_min"] for w in runs) <= 39
    longs = [w["duration_min"] for w in runs if w["type"] == "long"]
    assert not longs or longs[0] >= max(w["duration_min"] for w in runs if w["type"] != "long")


def test_weeks_to_race_and_the_decision_agree_for_a_sunday_plan():
    race = TODAY + timedelta(days=6)
    planned = build_runner_profile(activities=_weeks([300, 300, 300, 300]), today=TODAY - timedelta(days=1),
                                   previous_plan=_done_last_week(), plan_monday=TODAY,
                                   profile=_profile(target_date=str(race), target_distance="marathon"))
    assert planned["weeks_to_race"] == 0 and planned["decision_cause"] == "race_week"


def test_a_hard_sunday_is_detected_from_the_watch_without_a_saved_plan():
    from services.plan import _hard_day_before
    sunday = TODAY - timedelta(days=1)
    history = [{"date": f"{TODAY - timedelta(days=d)} 07:00", "type": "running", "duration_min": 150} for d in (8, 15)]
    long_run = {"date": f"{sunday} 07:00", "type": "running", "duration_min": 150}
    assert _hard_day_before(None, history + [long_run], TODAY) == str(sunday)
    easy = {"date": f"{sunday} 07:00", "type": "running", "duration_min": 50}
    assert _hard_day_before(None, history + [easy], TODAY) is None
