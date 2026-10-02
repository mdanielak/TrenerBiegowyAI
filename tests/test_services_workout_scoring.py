# -*- coding: utf-8 -*-
from services.workout_scoring import planned_duration_min, score_execution, zone_band


ZONES = {"z1": 96, "z2": 122, "z3": 137, "z4": 155, "z5": 173}


def score(*, planned=None, execution=None, readiness=6):
    return score_execution(
        planned=planned or {"spec": {"duration_min": 40, "zone_number": 2}},
        execution=execution or {"happened": True, "duration_min": 40, "avg_hr": 130},
        readiness_score=readiness, hr_zone_floors=ZONES, hr_max=192,
    )


def test_zone_band():
    assert zone_band(2, ZONES, 192) == (122, 136)
    assert zone_band(5, ZONES, 192) == (173, 192)
    assert zone_band(6, ZONES, 192) is None


def test_not_happened_scores():
    result = score(execution={"happened": False}, readiness=2)
    assert result["zgodnosc_z_planem"] == 0
    assert result["dopasowanie_do_formy"] == 8
    assert score(execution={"happened": False}, readiness=6)["dopasowanie_do_formy"] == 3


def test_ideal_execution():
    result = score()
    assert result["zgodnosc_z_planem"] == result["dopasowanie_do_formy"] == 10
    assert result["pewnosc"] == "wysoka"


def test_warmup_tolerance_is_not_penalized():
    result = score(execution={"happened": True, "duration_min": 40, "avg_hr": 115})
    assert result["odchylenie_tetna_bpm"] == 0
    assert result["zgodnosc_z_planem"] == 10


def test_below_warmup_tolerance_loses_one_point():
    result = score(execution={"happened": True, "duration_min": 40, "avg_hr": 113})
    assert result["odchylenie_tetna_bpm"] == -1
    assert result["zgodnosc_z_planem"] == 9


def test_large_time_deviation_loses_five_points():
    assert score(execution={"happened": True, "duration_min": 60, "avg_hr": 130})["zgodnosc_z_planem"] == 5


def test_missing_target_zone_has_no_hr_penalty_and_lower_confidence():
    result = score(planned={"spec": {"duration_min": 40}}, execution={"happened": True, "duration_min": 40, "avg_hr": 130})
    assert result["odchylenie_tetna_bpm"] is None
    assert result["zgodnosc_z_planem"] == 10
    assert result["pewnosc"] != "wysoka"


def test_scores_stay_in_range():
    result = score(execution={"happened": True, "duration_min": 1_000, "avg_hr": 300}, readiness=2)
    assert 0 <= result["zgodnosc_z_planem"] <= 10
    assert 0 <= result["dopasowanie_do_formy"] <= 10


def test_float_readiness_matches_integer():
    assert score(readiness=6.0) == score(readiness=6)


def test_planned_duration_uses_explicit_duration_min():
    assert planned_duration_min({"kind": "hr_zone_run", "duration_min": 40}) == 40
    assert planned_duration_min({"kind": "easy_run", "duration_min": 45}) == 45


def test_planned_duration_for_easy_run_zoned_without_strides():
    spec = {"kind": "easy_run_zoned", "warmup_min": 6, "main_min": 39, "cooldown_min": 0, "strides": 0}
    assert planned_duration_min(spec) == 45


def test_planned_duration_for_easy_run_zoned_with_strides():
    spec = {"kind": "easy_run_zoned", "warmup_min": 6, "main_min": 28, "cooldown_min": 4,
            "strides": 4, "stride_sec": 20, "stride_rest_sec": 90}
    assert planned_duration_min(spec) == 45


def test_planned_duration_for_easy_run_zoned_with_warmup_distance_is_unknown():
    assert planned_duration_min({"kind": "easy_run_zoned", "warmup_km": 1.0, "main_min": 30}) is None


def test_planned_duration_for_easy_run_zoned_without_main_is_unknown():
    assert planned_duration_min({"kind": "easy_run_zoned", "warmup_min": 6}) is None


def test_planned_duration_for_threshold_intervals_with_three_intervals():
    spec = {"kind": "threshold_intervals", "warmup_min": 9, "cooldown_min": 8,
            "num_intervals": 3, "work_sec": 480, "rest_sec": 120}
    assert planned_duration_min(spec) == 45


def test_planned_duration_for_threshold_intervals_with_two_intervals():
    spec = {"kind": "threshold_intervals", "warmup_min": 9, "cooldown_min": 6,
            "num_intervals": 2, "work_sec": 840, "rest_sec": 120}
    assert planned_duration_min(spec) == 45


def test_planned_duration_for_threshold_intervals_without_count_is_unknown():
    assert planned_duration_min({"kind": "threshold_intervals", "work_sec": 480}) is None


def test_planned_duration_for_unknown_kind_is_unknown():
    assert planned_duration_min({"kind": "unknown"}) is None


def test_score_uses_calculated_easy_run_zoned_duration():
    planned = {"spec": {"kind": "easy_run_zoned", "zone_number": 2, "warmup_min": 6,
                         "main_min": 28, "cooldown_min": 4, "strides": 4,
                         "stride_sec": 20, "stride_rest_sec": 90}}
    result = score(planned=planned, execution={"happened": True, "duration_min": 45, "avg_hr": 130})
    assert result["odchylenie_czasu_proc"] == 0
    assert result["pewnosc"] == "wysoka"
