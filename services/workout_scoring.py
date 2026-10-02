# -*- coding: utf-8 -*-
"""Deterministyczne, lokalne punktowanie wykonania treningu."""

HR_TOLERANCE_WARMUP_BPM = 8


def zone_band(zone_number: int, hr_zone_floors: dict, hr_max: int) -> tuple[int, int] | None:
    """Zwróć dolną i górną granicę strefy tętna."""
    if zone_number not in range(1, 6):
        return None
    lower = hr_zone_floors.get(f"z{zone_number}")
    upper = hr_max if zone_number == 5 else hr_zone_floors.get(f"z{zone_number + 1}")
    if lower is None or upper is None:
        return None
    return lower, upper if zone_number == 5 else upper - 1


def planned_duration_min(spec: dict) -> int | None:
    """Zwróć łączny czas planu, gdy da się go ustalić bez założeń."""
    duration = spec.get("duration_min")
    if duration is not None:
        return round(duration)

    kind = spec.get("kind")
    if kind == "easy_run_zoned":
        main_min = spec.get("main_min")
        if main_min is None or (spec.get("warmup_min") is None and spec.get("warmup_km") is not None):
            return None
        strides = spec.get("strides") or 0
        strides_min = 0
        if strides > 0:
            stride_sec = spec.get("stride_sec")
            stride_rest_sec = spec.get("stride_rest_sec")
            if stride_sec is not None and stride_rest_sec is not None:
                strides_min = strides * (stride_sec + stride_rest_sec) / 60
        return round((spec.get("warmup_min") or 0) + main_min + (spec.get("cooldown_min") or 0) + strides_min)

    if kind == "threshold_intervals":
        num_intervals = spec.get("num_intervals")
        work_sec = spec.get("work_sec")
        if num_intervals is None or work_sec is None:
            return None
        intervals_min = (num_intervals * work_sec + (num_intervals - 1) * (spec.get("rest_sec") or 0)) / 60
        return round((spec.get("warmup_min") or 0) + (spec.get("cooldown_min") or 0) + intervals_min)

    return None


def _execution_zone(avg_hr, hr_zone_floors):
    if avg_hr is None:
        return None
    floors = [hr_zone_floors.get(f"z{number}") for number in range(1, 6)]
    if any(floor is None for floor in floors):
        return None
    zone = 1
    for number, floor in enumerate(floors, 1):
        if avg_hr >= floor:
            zone = number
    return zone


def score_execution(*, planned, execution, readiness_score, hr_zone_floors, hr_max) -> dict:
    """Policz rubrykę treningu bez dostępu do danych zewnętrznych."""
    planned = planned or {}
    execution = execution or {}
    spec = planned.get("spec") or {}
    target_zone = spec.get("zone_number")
    target_band = zone_band(target_zone, hr_zone_floors, hr_max) if target_zone is not None else None
    planned_duration = planned_duration_min(spec)
    duration = execution.get("duration_min")
    time_deviation = None
    if planned_duration not in (None, 0) and duration is not None:
        time_deviation = round(abs(duration - planned_duration) / planned_duration * 100)

    avg_hr = execution.get("avg_hr")
    hr_deviation = None
    if avg_hr is not None and target_band is not None:
        lower, upper = target_band
        effective_lower = lower - HR_TOLERANCE_WARMUP_BPM
        if avg_hr < effective_lower:
            hr_deviation = avg_hr - effective_lower
        elif avg_hr > upper:
            hr_deviation = avg_hr - upper
        else:
            hr_deviation = 0
    execution_zone = _execution_zone(avg_hr, hr_zone_floors)
    happened = execution.get("happened") is True

    if not happened:
        adherence = 0
        if readiness_score is None:
            fitness = 5
        elif 0 <= readiness_score <= 3:
            fitness = 8
        else:
            fitness = 3
        confidence = "wysoka" if readiness_score is not None else "niska"
    else:
        adherence = 10
        if time_deviation is not None:
            if 10 <= abs(time_deviation) <= 20:
                adherence -= 1
            elif 21 <= abs(time_deviation) <= 40:
                adherence -= 3
            elif abs(time_deviation) > 40:
                adherence -= 5
        if hr_deviation is not None:
            if 1 <= abs(hr_deviation) <= 5:
                adherence -= 1
            elif 6 <= abs(hr_deviation) <= 10:
                adherence -= 2
            elif abs(hr_deviation) > 10:
                adherence -= 4
        fitness = 10
        if readiness_score is not None:
            if 4 <= readiness_score <= 6 and hr_deviation is not None and hr_deviation > 5:
                fitness -= 3
            elif 0 <= readiness_score <= 3:
                if execution_zone is not None and execution_zone >= 3:
                    fitness -= 5
                elif execution_zone in (1, 2):
                    fitness -= 1
        missing = sum(value is None for value in (time_deviation, hr_deviation, readiness_score))
        confidence = "wysoka" if missing == 0 else "srednia" if missing == 1 else "niska"

    return {
        "zgodnosc_z_planem": max(0, min(10, adherence)),
        "dopasowanie_do_formy": max(0, min(10, fitness)),
        "pewnosc": confidence,
        "odchylenie_czasu_proc": time_deviation,
        "odchylenie_tetna_bpm": hr_deviation,
        "strefa_wykonania": execution_zone,
        "zakres_docelowy": target_band,
        "strefa_docelowa": target_zone,
    }
