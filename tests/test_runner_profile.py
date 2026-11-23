# -*- coding: utf-8 -*-
"""Profil biegacza: poziom, decyzja tygodnia, dobór modułów promptu i bezpieczniki planu."""
from datetime import date, timedelta
from pathlib import Path

from ai.prompts import coach_prompt, modules_for
from services import plan as plan_service
from services.runner_profile import (_history_level, _settle_level, build_runner_profile, level_message, profile_lines,
                                     quality_sessions_limit, running_months)

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
    assert "# Poziom: początkujący" in prompt and "# Cel: 5 km" in prompt and "półmaraton" not in prompt
    assert "# Forma zwracania się: żeńska" in prompt  # płeć z konta Garmin, bez wyboru w kreatorze


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
    limit = round(runner["max_week_minutes"] * 1.1)  # decyzja „utrzymaj” bez poprzedniego planu
    assert sum(w["duration_min"] or 0 for w in workouts if w["type"] != "rest") <= limit
    assert "Skrócono do" in sunday["notes"] and thursday["duration_min"] >= 20


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
    assert sum(w["duration_min"] for w in runs) <= runner["week_cap_min"]


def test_each_ai_call_gets_its_mode_and_examples_only_go_to_the_weekly_plan():
    runner = build_runner_profile(activities=_tester(), profile=_profile(running_since="under6"), today=TODAY)
    plan, day, review = (coach_prompt(runner, mode=m, private_path=Path("brak.md")) for m in ("plan", "dzien", "trening"))
    assert "# Tryb: plan tygodnia" in plan and "# Przykłady decyzji trenera" in plan and "# Prewencja urazów" in plan
    assert "# Tryb: rekomendacja na dziś" in day and "# Przykłady" not in day
    assert "# Tryb: komentarz do zakończonego treningu" in review
    for prompt in (plan, day, review):
        assert "# 01 — Bramka bezpieczeństwa" in prompt and "jedynym źródłem prawdy" in prompt
        assert "Czy sprawdziłem" not in prompt and "wyłączyłem" not in prompt  # lista kontrolna bezosobowa


def test_address_form_follows_the_wizard_choice_then_garmin_then_neutral():
    from services.runner_profile import address_form
    assert address_form({"address_form": "male", "sex": "female"}) == "male"
    assert address_form({"sex": "female"}) == "female"
    assert address_form({}) == "neutral" and address_form({"address_form": "bzdura"}) == "neutral"
    texts = {form: coach_prompt(mode="dzien", address_form=form, private_path=Path("brak.md"))
             for form in ("male", "female", "neutral")}
    assert "zrobiłeś" in texts["male"] and "zrobiłaś" in texts["female"] and "bez form płciowych" in texts["neutral"]


def test_the_model_is_told_the_same_limits_the_app_enforces():
    runner = build_runner_profile(activities=_tester(), today=TODAY,
                                  profile=_profile(running_since="under6", training_frequency="3 treningi w tygodniu"))
    lines = "\n".join(profile_lines(runner))
    assert f"długi bieg najwyżej {runner['longest_min'] + 10} min" in lines
    assert "najwyżej 3 treningi w tygodniu" in lines and f"najwyżej {runner['week_cap_min']} min" in lines
    assert "bez interwałów, biegu progowego i tempowego" in lines
    easing = build_runner_profile(activities=_tester(), today=TODAY, pain=True, profile=_profile(running_since="6to24"))
    assert easing["week_cap_min"] == round(easing["max_week_minutes"] * 0.75)
    assert "zdrowie/regeneracja-i-przemeczenie" in modules_for(easing) and "zdrowie/kontuzje" in modules_for(easing)


def test_high_bmi_module_only_for_someone_still_building_a_base():
    heavy = dict(weight_kg=100, height_cm=175)
    experienced = build_runner_profile(activities=_runs(range(3, 31), 50, km=8.0), today=TODAY,
                                       profile=_profile(running_since="over24", **heavy))
    beginner = build_runner_profile(activities=_tester(), today=TODAY, profile=_profile(running_since="under6", **heavy))
    assert "zdrowie/wysoka-waga" not in modules_for(experienced)
    assert "zdrowie/wysoka-waga" in modules_for(beginner)


def test_planning_next_week_judges_the_current_week_without_its_future_days():
    """W środę ocena bieżącego tygodnia: poniedziałek zrobiony, piątek dopiero nadejdzie — nie jest opuszczony."""
    this_week = {"workouts": [{"date": "2026-11-02", "type": "easy", "duration_min": 35},
                              {"date": "2026-11-06", "type": "long", "duration_min": 45}]}
    runs = _tester() + [{"date": "2026-11-02 18:00", "type": "running/generic", "duration_min": 35}]
    runner = build_runner_profile(activities=runs, profile=_profile(running_since="6to24"), today=TODAY,
                                  previous_plan=this_week)
    assert runner["adherence"] == 1.0 and runner["done"] == 1


def test_daily_recommendation_gets_no_weekly_decision_or_limits():
    from unittest.mock import MagicMock
    from ai.recommendation import DailyRecommendation, get_daily_recommendation
    runner = build_runner_profile(activities=_tester(), profile=_profile(running_since="under6"), today=TODAY)
    daily = "\n".join(profile_lines(runner, weekly=False))
    assert "DECYZJA TYGODNIA" not in daily and "LIMITY APLIKACJI" not in daily and "poziom: początkujący" in daily
    provider = MagicMock()
    provider.chat.return_value = DailyRecommendation(readiness="ready", recommendation="x", adjustment_needed=False,
                                                     reasoning_summary="x", warnings=[])
    context = {"runner": runner, "runner_profile": {"age": 32, "weight_kg": 60, "height_cm": 165, "hr_max": 190,
               "hr_rest": 50, "lactate_threshold_hr": 170, "hr_zones": "", "current_hm_record": "", "target_hm": "5 km",
               "target_date": "2027-03-01"}, "goal": {"target": "5 km", "deadline": "2027-03-01", "current_record": ""},
               "recent_activities": [], "weekly_load": {"total_km": 0, "total_min": 0, "sessions": 0}, "today_plan": None,
               "health_metrics": {k: None for k in ("rhr", "hrv_last_night", "hrv_status", "hrv_baseline", "sleep_total_h",
                                                     "sleep_score", "sleep_deep_h", "stress_avg")},
               "hrv_alert": None, "journal": None}
    get_daily_recommendation(provider, context)
    kwargs = provider.chat.call_args[1]
    assert "# Tryb: rekomendacja na dziś" in kwargs["system_prompt"]  # prompt składa sama rekomendacja dnia
    assert "DECYZJA TYGODNIA" not in kwargs["user_message"]


def test_years_of_running_grow_from_the_wizard_answer():
    p = _profile(running_since="start", running_since_at="2025-10-01")
    assert running_months(p, date(2026, 11, 4)) == 13
    assert running_months(_profile(running_since="start", onboarding_completed_at="2026-05-04T10:00:00"),
                          date(2026, 11, 4)) == 6
    assert running_months(_profile(running_since="under6"), date(2026, 11, 4)) == 3   # bez daty — jak dziś
    assert running_months(_profile(), date(2026, 11, 4)) is None


def test_a_year_after_starting_a_frequent_runner_is_no_longer_a_beginner():
    runs = _runs(range(3, 113, 2), 50)   # ~3,5 biegu tygodniowo przez 16 tygodni
    runner = build_runner_profile(activities=runs, today=TODAY,
                                  profile=_profile(running_since="start", running_since_at="2025-10-01"))
    assert runner["level"] == "regularny"


MONDAY = TODAY - timedelta(days=TODAY.weekday())
_RUN_DAYS = (5, 1, 3, 6)  # sobota, wtorek, czwartek, niedziela


def _weeks(*segments, extra=()):
    """Biegi w pełnych tygodniach przed bieżącym: (tygodnie, biegi w tygodniu, minuty), od najstarszych.

    Ostatni segment kończy się w poprzednim tygodniu; ``extra`` — dni wstecz od TODAY z biegiem 30 min.
    """
    total = sum(segment[0] for segment in segments)
    runs, week = [], total
    for count, per_week, minutes, *km in segments:
        for _ in range(count):
            start = MONDAY - timedelta(days=7 * week)
            runs += [{"date": f"{start + timedelta(days=d)} 18:00", "type": "running/generic",
                      "duration_min": minutes, "distance_km": km[0] if km else 5.0, "avg_hr": 130}
                     for d in _RUN_DAYS[:per_week]]
            week -= 1
    return runs + _runs(extra, 30)


def test_steady_weeks_promote_and_too_few_do_not():
    # Ocena tygodnia patrzy na 28 dni: 4 tygodnie po 4 biegi dają 3 oceny „regularny” z rzędu, 3 tygodnie — dwie.
    runner = build_runner_profile(activities=_weeks((8, 1, 30), (4, 4, 50)), profile=_profile(), today=TODAY)
    assert runner["level"] == "regularny" and runner["level_changed"] == "up"
    assert runner["level_since"] == MONDAY.isoformat()
    assert runner["level_reason"] == "W ostatnich 4 tygodniach biegasz średnio 4 razy w tygodniu, a najdłuższy bieg trwał 50 min."
    assert level_message(runner) == (runner["level_reason"]
                                     + " Trener traktuje Cię teraz jak osobę biegającą regularnie.")
    slower = build_runner_profile(activities=_weeks((8, 1, 30), (3, 4, 50)), profile=_profile(), today=TODAY)
    assert slower["level"] == "poczatkujacy" and slower["level_changed"] is None and level_message(slower) is None


def test_a_lighter_stretch_lowers_advanced_slowly_but_beginner_at_once():
    # Z zaawansowanego na regularny dopiero po 4 słabszych ocenach z rzędu.
    three = build_runner_profile(activities=_weeks((8, 4, 50, 10.0), (3, 4, 50, 6.0)), profile=_profile(), today=TODAY)
    assert three["level"] == "zaawansowany" and three["level_changed"] is None
    four = build_runner_profile(activities=_weeks((8, 4, 50, 10.0), (4, 4, 50, 6.0)), profile=_profile(), today=TODAY)
    assert four["level"] == "regularny" and four["level_changed"] == "down"
    assert level_message(four) == ("Ostatnie tygodnie były lżejsze, więc trener planuje teraz jak dla osoby"
                                   " biegającej regularnie.")
    # Bieganie rzadziej niż 2 razy w tygodniu: od razu ostrożnie, bez akcentów (bezpiecznik ważniejszy niż stabilność).
    light = build_runner_profile(activities=_weeks((8, 4, 50), (3, 1, 30)), profile=_profile(), today=TODAY)
    assert light["level"] == "poczatkujacy" and light["level_changed"] == "down"
    assert level_message(light) == ("Ostatnie tygodnie były lżejsze, więc trener na razie planuje ostrożniej"
                                    " — jak dla osoby, która zaczyna biegać.")


def test_the_sliding_history_does_not_change_the_level_by_itself():
    ratings = ["regularny", "zaawansowany", "zaawansowany"] * 6
    assert {_settle_level(ratings[i:i + 12])[0] for i in range(4)} == {"regularny"}


def test_years_of_running_do_not_grow_without_running():
    # Odpowiedź „start” 10 miesięcy temu, a zegarek pokazuje bieganie dopiero od 2 tygodni.
    runner = build_runner_profile(activities=_runs([2, 5, 9, 12], 30), today=TODAY,
                                  profile=_profile(running_since="start", running_since_at="2026-01-10"))
    assert runner["level"] == "poczatkujacy"


def test_a_manual_level_raises_at_most_one_step():
    beginner = _weeks((8, 1, 20))
    chosen = build_runner_profile(activities=beginner, profile=_profile(level_override="zaawansowany"), today=TODAY)
    assert chosen["level_auto"] == "poczatkujacy" and chosen["level"] == "regularny"
    lower = build_runner_profile(activities=_weeks((8, 4, 50)), profile=_profile(level_override="poczatkujacy"),
                                 today=TODAY)
    assert lower["level"] == "poczatkujacy"
    fresh = build_runner_profile(activities=_runs([2, 5], 20), today=TODAY,
                                 profile=_profile(running_since="start", level_override="regularny"))
    assert fresh["short_history"] and fresh["level"] == "poczatkujacy"


def test_weeks_without_running_are_not_evidence():
    pause = build_runner_profile(activities=_weeks((8, 4, 50), (2, 0, 0)), profile=_profile(), today=TODAY)
    assert pause["level_auto"] == "regularny" and pause["level_changed"] is None
    back = build_runner_profile(activities=_weeks((8, 4, 50), (4, 0, 0)) + _runs([1, 6, 3], 30),
                                profile=_profile(), today=TODAY)
    assert back["returning"] and back["level"] == "poczatkujacy"


def test_manual_level_wins_except_after_a_break():
    steady = _weeks((8, 4, 50))
    chosen = build_runner_profile(activities=steady, profile=_profile(level_override="zaawansowany"), today=TODAY)
    assert chosen["level"] == "zaawansowany" and chosen["level_auto"] == "regularny"
    assert level_message(chosen) is None
    unknown = build_runner_profile(activities=steady, profile=_profile(level_override="cokolwiek"), today=TODAY)
    assert unknown["level"] == "regularny" and unknown["level_override"] is None
    back = _weeks((8, 4, 50), (4, 0, 0)) + _runs([1, 6, 3], 30)
    after_break = build_runner_profile(activities=back, profile=_profile(level_override="zaawansowany"), today=TODAY)
    assert after_break["level"] == "poczatkujacy"


def test_a_change_is_announced_only_in_its_own_week():
    runner = build_runner_profile(activities=_weeks((8, 1, 30), (4, 4, 50)), profile=_profile(),
                                  today=TODAY + timedelta(days=7))
    assert runner["level"] == "regularny" and runner["level_changed"] is None
    assert runner["level_since"] == MONDAY.isoformat()


def test_a_monday_after_a_break_plans_carefully_before_the_first_run_back():
    runner = build_runner_profile(activities=_weeks((8, 4, 50, 10.0), (3, 0, 0)), profile=_profile(), today=MONDAY)
    assert runner["level"] == "poczatkujacy" and quality_sessions_limit(runner, 2) == 0


def test_a_level_that_only_slid_into_the_window_is_not_announced():
    A, R = "zaawansowany", "regularny"
    ratings = [A, A, A, R, A, R, A, R, A, R, A, A, A]   # 13 tygodni: poprzednie 12 i bieżące 12
    assert _settle_level(ratings[:-1])[0] == A and _settle_level(ratings[1:])[2] == "up"
    assert _history_level(ratings) == (A, None)


def test_a_steady_level_has_no_since_date():
    runner = build_runner_profile(activities=_weeks((10, 4, 50)), profile=_profile(), today=TODAY)
    assert runner["level"] == "regularny" and runner["level_since"] is None
