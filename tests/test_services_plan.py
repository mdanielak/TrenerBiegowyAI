# -*- coding: utf-8 -*-
"""Testy dla services/plan.py — deterministyczne reguły tygodnia."""
import csv
from datetime import datetime

from ai.plan_generation import PlanWorkout, WeekPlanResponse
from services import plan as plan_service


FLOORS = {"z1": 96, "z2": 122, "z3": 137, "z4": 155, "z5": 173}


def _day(date, day, *, available=True, min_minutes=35, max_minutes=45, pause_reason=None):
    return {
        "date": date,
        "day": day,
        "weekday": "poniedziałek",
        "available": available,
        "min_minutes": min_minutes,
        "max_minutes": max_minutes,
        "pause_reason": pause_reason,
        "readiness_score": None,
        "readiness_level": None,
    }


def _context(days=None, max_quality=1):
    days = days or [
        _day("2026-10-26", "mon"),
        _day("2026-10-27", "tue"),
        _day("2026-10-28", "wed", available=False),
        _day("2026-10-29", "thu"),
        _day("2026-10-30", "fri", pause_reason="Rekonwalescencja po zabiegu"),
        _day("2026-10-31", "sat", available=False),
        _day("2026-11-01", "sun", min_minutes=60, max_minutes=90),
    ]
    return {
        "week_start": "2026-10-26",
        "week_end": "2026-11-01",
        "week_days": days,
        "max_quality_sessions": max_quality,
        "hr_zone_floors": FLOORS,
    }


def _response(workouts):
    return WeekPlanResponse(
        start_date="2026-10-26", end_date="2026-11-01", focus="Baza tygodnia",
        summary="Jeden akcent i dwa biegi regeneracyjne.",
        workouts=workouts,
    )


def _normalize(workouts, context=None):
    return plan_service.normalize_plan(_response(workouts), context=context or _context())


def _workout(date, kind="easy", **fields):
    return PlanWorkout(date=date, kind=kind, name=fields.pop("name", "Bieg"), **fields)


def test_unavailable_day_becomes_rest():
    plan = _normalize([_workout("2026-10-28", duration_min=40, hr_zone=2)])

    wednesday = plan["workouts"][2]
    assert wednesday["type"] == "rest"
    assert wednesday["duration_min"] is None
    assert wednesday["hr_zone"] is None
    assert wednesday["name"] == "Odpoczynek"


def test_paused_day_becomes_rest_with_reason_in_description():
    plan = _normalize([_workout("2026-10-30", duration_min=40, hr_zone=2)])

    friday = plan["workouts"][4]
    assert friday["type"] == "rest"
    assert friday["description"] == "Rekonwalescencja po zabiegu"


def test_duration_is_clipped_to_the_day_window_with_a_note():
    plan = _normalize([_workout("2026-10-26", duration_min=90, hr_zone=2)])

    monday = plan["workouts"][0]
    assert monday["duration_min"] == 45
    assert "Skrócono do 45 min (limit dostępności w tym dniu)." in monday["notes"]


def test_second_quality_session_is_downgraded_with_a_note():
    plan = _normalize([
        _workout("2026-10-26", "tempo", duration_min=45, pace_target="5:00-5:10"),
        _workout("2026-10-27", "tempo", duration_min=45, pace_target="5:00-5:10"),
    ])

    assert plan["workouts"][0]["type"] == "tempo"
    assert plan["workouts"][1]["type"] == "easy"
    assert "Zmieniono na bieg łatwy (limit 1 treningu jakościowego w tygodniu)." in plan["workouts"][1]["notes"]


def test_second_long_run_is_downgraded_with_a_note():
    plan = _normalize([
        _workout("2026-10-26", "long", duration_min=60, hr_zone=2),
        _workout("2026-10-29", "long", duration_min=60, hr_zone=2),
    ])

    assert plan["workouts"][0]["type"] == "long"
    assert plan["workouts"][3]["type"] == "easy"
    assert "Zmieniono na bieg łatwy (limit 1 długiego biegu w tygodniu)." in plan["workouts"][3]["notes"]


def test_missing_day_becomes_named_rest():
    plan = _normalize([_workout("2026-10-26", duration_min=40, hr_zone=2)])

    thursday = plan["workouts"][3]
    assert thursday["type"] == "rest"
    assert thursday["name"] == "Odpoczynek"


def test_entries_use_the_plan_file_schema():
    plan = _normalize([_workout("2026-10-26", duration_min=40, hr_zone=2)])

    monday = plan["workouts"][0]
    assert monday["day"] == "mon"
    assert monday["date"] == "2026-10-26"
    assert monday["garmin_upload"] is False
    assert monday["garmin_workout_id"] is None
    assert monday["hr_zone"] == "Z2"
    assert monday["hr_target"] == "122-136 bpm"
    assert "repetitions" not in monday
    assert plan["start_date"] == "2026-10-26"
    assert plan["end_date"] == "2026-11-01"
    assert len(plan["workouts"]) == 7


def test_tempo_without_parsable_pace_is_downgraded_with_a_note():
    plan = _normalize([_workout("2026-10-26", "tempo", duration_min=45, pace_target="szybko")])

    monday = plan["workouts"][0]
    assert monday["type"] == "easy"
    assert "Zmieniono na bieg łatwy (brak parsowalnego tempa docelowego)." in monday["notes"]


def test_intervals_without_parameters_are_downgraded_with_a_note():
    plan = _normalize([_workout("2026-10-26", "intervals", duration_min=45, pace_target="4:40")])

    monday = plan["workouts"][0]
    assert monday["type"] == "easy"
    assert "Zmieniono na bieg łatwy (brak kompletnych parametrów interwałów)." in monday["notes"]


def test_pace_target_is_normalized_with_the_faster_bound_first():
    plan = _normalize([_workout("2026-10-26", "tempo", duration_min=45, pace_target="5:10-5:00")])

    assert plan["workouts"][0]["pace_target"] == "5:00-5:10"


def test_dates_outside_the_week_are_ignored():
    plan = _normalize([
        _workout("2026-11-02", duration_min=40, hr_zone=2),
        _workout("2026-10-26", duration_min=40, hr_zone=2),
    ])

    assert [entry["date"] for entry in plan["workouts"]] == [
        "2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01",
    ]


def test_easy_run_maps_to_hr_zone_workout():
    kind, kwargs = plan_service.plan_workout_to_garmin({
        "type": "easy", "name": "Bieg łatwy", "duration_min": 40, "hr_zone": "Z2", "date": "2026-10-26",
    })

    assert kind == "hr_zone_run"
    assert kwargs == {
        "minutes": 40, "zone_number": 2, "date": "2026-10-26",
        "warmup_min": 6, "warmup_pace_faster": "7:00", "warmup_pace_slower": "8:30",
    }


def test_tempo_maps_to_tempo_workout_without_warmup_in_minutes():
    kind, kwargs = plan_service.plan_workout_to_garmin({
        "type": "tempo", "name": "Tempo", "duration_min": 50, "pace_target": "5:00-5:10", "date": "2026-10-27",
    })

    assert kind == "tempo"
    assert kwargs == {"minutes": 30, "pace_from": "5:00", "pace_to": "5:10", "date": "2026-10-27"}


def test_intervals_map_to_intervals_workout():
    kind, kwargs = plan_service.plan_workout_to_garmin({
        "type": "intervals", "name": "Interwały", "duration_min": 45, "pace_target": "4:40",
        "repetitions": 5, "work_seconds": 180, "rest_seconds": 90, "date": "2026-10-29",
    })

    assert kind == "intervals"
    assert kwargs == {
        "repeats": 5, "work_seconds": 180, "rest_seconds": 90,
        "pace_from": "4:40", "pace_to": "4:40", "date": "2026-10-29",
    }


def test_rest_day_has_no_garmin_workout():
    assert plan_service.plan_workout_to_garmin({"type": "rest", "name": "Odpoczynek"}) is None


def test_hr_band_reads_zone_floors():
    assert plan_service.hr_band(2, FLOORS) == "122-136 bpm"
    assert plan_service.hr_band(5, FLOORS) == "173+ bpm"
    assert plan_service.hr_band("Z3", FLOORS) == "137-154 bpm"
    assert plan_service.hr_band(2, {}) is None


def test_save_and_load_plan_with_its_csv_twin(tmp_path, monkeypatch):
    monkeypatch.setattr("services.plan_files.TRAINING_PLANS_DIR", tmp_path)
    plan = _normalize([_workout("2026-10-26", duration_min=40, hr_zone=2)])

    path = plan_service.save_plan(plan)

    assert path == tmp_path / "2026-10" / "26-1.json"
    assert path.is_file()
    assert path.with_suffix(".csv").is_file()
    with open(path.with_suffix(".csv"), encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert len(rows) == 8

    loaded = plan_service.load_week_plan(datetime(2026, 10, 29))
    assert loaded is not None
    assert len(loaded["workouts"]) == 7
    assert loaded["workouts"][0]["type"] == "easy"


def test_trim_cuts_on_a_word_boundary_with_an_ellipsis():
    assert plan_service._trim("krótki tekst", 50) == "krótki tekst"
    assert plan_service._trim("Spokojny tydzień, potem akcent progowy", 20) == "Spokojny tydzień…"
    assert len(plan_service._trim("słowo " * 100, 300)) <= 300


def test_plan_trends_are_aggregates_only():
    from datetime import date, timedelta

    days = [(date(2026, 10, 28) - timedelta(days=i)).isoformat() for i in range(84)]
    data = {"daily_health": [{"date": d, "rhr": 50 if i < 7 else 48} for i, d in enumerate(days)],
            "activities": [{"date": "2026-10-20 07:00", "type": "running/x", "distance_km": 10.0, "duration_min": 55}]}

    trends = plan_service._plan_trends(data, date(2026, 10, 28))

    assert trends["metrics"]["rhr"]["direction"] == "up"
    assert trends["metrics"]["hrv"]["recent"] is None
    assert trends["weekly_km"] == [0, 0, 0, 10.0]
    assert set(trends) == {"metrics", "weekly_km"}


def test_days_that_already_passed_become_rest_and_are_named_for_the_ai(monkeypatch):
    """Plan ułożony w czwartek nie wstawia treningów w miniony poniedziałek."""
    from datetime import datetime
    from ai.plan_generation import build_plan_message
    from services import plan as plan_service
    every_day = {key: {"available": True, "min_minutes": 30, "max_minutes": 60}
                 for key in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    monkeypatch.setattr("trainer.preferences.get_weekly_availability", lambda: every_day)
    monkeypatch.setattr("trainer.preferences.get_active_pause", lambda day: None)
    context = plan_service.build_plan_context(snapshot_data={}, profile={}, preferences={},
                                              today=datetime(2026, 10, 1, 9), week_start="2026-09-28")
    assert [day["available"] for day in context["week_days"]] == [False, False, False, True, True, True, True]
    assert "- poniedziałek, 2026-09-28: już minął" in build_plan_message(context)

    response = {"workouts": [{"date": "2026-09-28", "kind": "easy", "name": "Bieg", "duration_min": 40,
                              "hr_zone": "Z2"}]}
    monday = plan_service.normalize_plan(response, context=context)["workouts"][0]
    assert (monday["type"], monday["description"]) == ("rest", "Ten dzień już minął.")


def _beginner_context(recent_minutes):
    """Biegaczka do 5 km: biega 30-40 min, w niedzielę ma wolne 60-90 min."""
    days = []
    for index, key in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun")):
        free = key in ("tue", "thu", "sun")
        days.append({"date": f"2026-11-0{index + 2}", "day": key, "available": free,
                     "min_minutes": 60 if key == "sun" else (30 if free else 0),
                     "max_minutes": 90 if key == "sun" else (45 if free else 0)})
    return {"week_start": "2026-11-02", "week_end": "2026-11-08", "week_days": days,
            "hr_zone_floors": {"z1": 98, "z2": 120, "z3": 138, "z4": 156, "z5": 172},
            "recent_activities": [{"duration_min": m} for m in recent_minutes]}


def test_long_run_grows_from_the_longest_recent_run_and_is_never_stretched_to_fill_free_time():
    from services import plan as plan_service
    response = {"workouts": [
        {"date": "2026-11-03", "kind": "easy", "name": "Łatwy", "duration_min": 50, "distance_km": 7.0, "hr_zone": 2},
        {"date": "2026-11-05", "kind": "easy", "name": "Łatwy", "duration_min": 30, "hr_zone": 2},
        {"date": "2026-11-08", "kind": "long", "name": "Długi", "duration_min": 60, "distance_km": 8.0, "hr_zone": 2},
    ]}
    workouts = {w["day"]: w for w in plan_service.normalize_plan(response, context=_beginner_context([30, 38, 35]))["workouts"]}
    assert workouts["sun"]["duration_min"] == 48  # 38 + 10, nie 60
    assert workouts["sun"]["distance_km"] == 6.4 and "najdłuższy z ostatnich biegów trwał 38 min" in workouts["sun"]["notes"]
    assert workouts["tue"]["duration_min"] == 38  # łatwy nie dłuższy niż najdłuższy bieg
    assert workouts["thu"]["duration_min"] == 30  # krótszego nie wydłużamy do okna dostępności


def test_without_running_history_only_the_availability_limit_applies():
    from services import plan as plan_service
    response = {"workouts": [{"date": "2026-11-08", "kind": "long", "name": "Długi", "duration_min": 40, "hr_zone": 2}]}
    sunday = plan_service.normalize_plan(response, context=_beginner_context([]))["workouts"][6]
    assert sunday["duration_min"] == 40  # okno 60-90 min nie wydłuża treningu


def test_plan_prompt_names_the_longest_recent_run_and_the_gradual_rule():
    from ai.plan_generation import build_plan_message, build_system_prompt
    message = build_plan_message(_beginner_context([30, 38]))
    assert "- najdłuższy z nich: 38 min" in message
    system = build_system_prompt()
    assert "długi bieg najwyżej 10 minut dłuższy niż najdłuższy z ostatnich biegów" in system
    assert "nie wydłużaj sesji, żeby je wypełnić" in system
    from trainer.config import IMPORTANT_PROMPT
    assert "half-marathon" not in IMPORTANT_PROMPT.read_text(encoding="utf-8")  # ogólny prompt nie zakłada półmaratonu
