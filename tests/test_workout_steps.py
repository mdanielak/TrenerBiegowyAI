# -*- coding: utf-8 -*-
"""Rozpiska treningu krok po kroku."""
from services.workout_steps import spec_from_plan, workout_steps

FLOORS = {"z1": 96, "z2": 122, "z3": 137, "z4": 155, "z5": 173}


def _labels(steps):
    return [(s["label"], s["time"]) for s in steps]


def test_zone_run_splits_warmup_from_the_zone_part():
    steps = workout_steps({"kind": "hr_zone_run", "duration_min": 40, "zone_number": 2, "warmup_min": 6,
                           "warmup_pace_faster": "7:00", "warmup_pace_slower": "8:30"}, FLOORS)

    assert _labels(steps) == [("Rozgrzewka", "6 min"), ("Bieg w strefie", "34 min")]
    assert steps[0]["target"] == "tempo 7:00–8:30 /km · bez alarmu tętna"
    assert steps[1]["target"].startswith("strefa Z2 · 122–136")


def test_intervals_show_repeats_rest_and_paces():
    steps = workout_steps({"kind": "threshold_intervals", "num_intervals": 3, "work_sec": 360, "rest_sec": 120,
                           "pace_faster": "5:45", "pace_slower": "6:00", "warmup_min": 10, "cooldown_min": 8})

    assert _labels(steps) == [("Rozgrzewka", "10 min"), ("Odcinki", "3 × 6 min"),
                              ("Przerwy między odcinkami", "2 min"), ("Schłodzenie", "8 min")]
    assert steps[1]["target"] == "tempo 5:45–6:00 /km"


def test_other_kinds():
    assert _labels(workout_steps({"kind": "easy_run", "duration_min": 30})) == [("Bieg spokojny", "30 min")]
    assert _labels(workout_steps({"kind": "tempo_run", "tempo_min": 20, "pace_faster": "5:00", "pace_slower": "5:10",
                                  "warmup_min": 10, "cooldown_min": 10}))[1] == ("Tempo", "20 min")
    strides = workout_steps({"kind": "strides", "base_min": 30, "num_strides": 6})
    assert _labels(strides)[1] == ("Przebieżki", "6 × 20 s") and strides[1]["target"] == "przerwy 1 min 30 s"
    assert workout_steps({"kind": "nieznany"}) == []


def test_plan_workouts_become_the_same_steps_as_the_watch():
    spec = spec_from_plan({"type": "easy", "duration_min": 40, "hr_zone": "Z2", "date": "2026-10-29"})

    assert _labels(workout_steps(spec, FLOORS)) == [("Rozgrzewka", "6 min"), ("Bieg w strefie", "34 min")]
    assert spec_from_plan({"type": "rest"}) is None


def test_steps_carry_minutes_and_zone_for_the_profile_bar():
    zone_run = workout_steps({"kind": "hr_zone_run", "duration_min": 40, "zone_number": 2, "warmup_min": 6}, FLOORS)
    assert [(s["minutes"], s["zone"]) for s in zone_run] == [(6.0, None), (34.0, 2)]
    intervals = workout_steps({"kind": "threshold_intervals", "num_intervals": 5, "work_sec": 360, "rest_sec": 120,
                               "warmup_min": 10, "cooldown_min": 10})
    assert [s["minutes"] for s in intervals] == [10.0, 30.0, 8.0, 10.0]  # 4 przerwy między 5 odcinkami
    assert workout_steps({"kind": "easy_run_zoned", "warmup_km": 1, "main_min": 30})[0]["minutes"] == 0.0
