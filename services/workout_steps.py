# -*- coding: utf-8 -*-
"""Rozpisanie treningu na kroki dokładnie tak, jak wykona je zegarek.

Źródłem jest ``spec`` z rejestru Garmina (argumenty buildera z
``trainer/garmin_workouts.py``) albo trening z planu AI przełożony przez
``services.plan.plan_workout_to_garmin`` na tę samą postać.
"""
from __future__ import annotations


def _minutes(value) -> str:
    minutes = float(value or 0)
    return f"{int(minutes)} min" if minutes.is_integer() else f"{minutes:.1f} min".replace(".", ",")


def _seconds(value) -> str:
    seconds = int(value or 0)
    if seconds and seconds % 60 == 0:
        return f"{seconds // 60} min"
    if seconds > 60:
        return f"{seconds // 60} min {seconds % 60} s"
    return f"{seconds} s"


def _number(value) -> float:
    """Liczba z pola specyfikacji; brak lub zły format to 0, żeby pasek nie padł na starych wpisach."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _zone_number(value) -> int | None:
    try:
        zone = int(value)
    except (TypeError, ValueError):
        return None
    return zone if 1 <= zone <= 5 else None


def _pace(faster, slower) -> str:
    if faster and slower:
        return f"tempo {faster}–{slower} /km"
    return ""


def _zone(zone, floors) -> str:
    from services.plan import hr_band

    if zone is None:
        return ""
    band = hr_band(zone, floors or {})
    return f"strefa Z{zone}" + (f" · {band.replace('-', '–')}" if band else "")


def spec_from_plan(workout) -> dict | None:
    """Trening z planu AI w postaci ``spec`` z rejestru (te same nazwy pól)."""
    from services.plan import plan_workout_to_garmin

    mapped = plan_workout_to_garmin(workout)
    if mapped is None:
        return None
    kind, args = mapped
    if kind == "hr_zone_run":
        return {"kind": "hr_zone_run", "duration_min": args["minutes"], "zone_number": args["zone_number"],
                "warmup_min": args.get("warmup_min", 6), "warmup_pace_faster": args.get("warmup_pace_faster"),
                "warmup_pace_slower": args.get("warmup_pace_slower")}
    if kind == "tempo":
        return {"kind": "tempo_run", "tempo_min": args["minutes"], "pace_faster": args["pace_from"],
                "pace_slower": args["pace_to"], "warmup_min": 10, "cooldown_min": 10}
    if kind == "intervals":
        return {"kind": "threshold_intervals", "num_intervals": args.get("repeats"), "work_sec": args.get("work_seconds"),
                "rest_sec": args.get("rest_seconds"), "pace_faster": args["pace_from"], "pace_slower": args["pace_to"],
                "warmup_min": 10, "cooldown_min": 10}
    return None


def workout_steps(spec, floors=None) -> list[dict]:
    """Lista kroków {label, time, target, phase, minutes, zone}; nieznany rodzaj to pusta lista.

    ``minutes`` (przybliżony czas kroku) wyznacza szerokość odcinka na pasku przebiegu,
    ``zone`` jego kolor; ``None`` znaczy, że długości nie da się podać w minutach (np. km).
    """
    spec = spec or {}
    kind = spec.get("kind")
    steps = []

    def add(phase, label, time, target="", minutes=None, zone=None):
        steps.append({"phase": phase, "label": label, "time": time, "target": target,
                      "minutes": _number(minutes), "zone": zone})

    def repeated(count, seconds):
        return _number(count) * _number(seconds) / 60 if _number(count) and _number(seconds) else None

    if kind in ("easy_run", "long_run"):
        add("main", "Bieg spokojny" if kind == "easy_run" else "Długi bieg", _minutes(spec.get("duration_min")),
            "swobodnie, rozmowa bez zadyszki", spec.get("duration_min"))
    elif kind == "hr_zone_run":
        warmup = int(spec.get("warmup_min") or 0)
        if warmup:
            add("warmup", "Rozgrzewka", _minutes(warmup),
                " · ".join(filter(None, [_pace(spec.get("warmup_pace_faster"), spec.get("warmup_pace_slower")),
                                         "bez alarmu tętna"])), warmup)
        main = max(0, int(spec.get("duration_min") or 0) - warmup)
        add("main", "Bieg w strefie", _minutes(main),
            " · ".join(filter(None, [_zone(spec.get("zone_number"), floors),
                                     "zegarek ostrzeże po przekroczeniu"])), main, _zone_number(spec.get("zone_number")))
    elif kind == "easy_run_zoned":
        if spec.get("warmup_km"):
            add("warmup", "Rozgrzewka", f"{spec['warmup_km']} km",
                _pace(spec.get("warmup_pace_faster"), spec.get("warmup_pace_slower")))
        elif spec.get("warmup_min"):
            add("warmup", "Rozgrzewka", _minutes(spec["warmup_min"]),
                _pace(spec.get("warmup_pace_faster"), spec.get("warmup_pace_slower")), spec["warmup_min"])
        add("main", "Bieg w strefie", _minutes(spec.get("main_min")), _zone(spec.get("zone_number", 2), floors),
            spec.get("main_min"), _zone_number(spec.get("zone_number", 2)))
        if spec.get("strides"):
            add("work", "Przebieżki", f"{spec['strides']} × {_seconds(spec.get('stride_sec', 20))}",
                f"przerwy {_seconds(spec.get('stride_rest_sec', 90))} spokojnie",
                repeated(spec["strides"], _number(spec.get("stride_sec", 20)) + _number(spec.get("stride_rest_sec", 90))))
        if spec.get("cooldown_min"):
            add("cooldown", "Schłodzenie", _minutes(spec["cooldown_min"]), "trucht", spec["cooldown_min"])
    elif kind == "tempo_run":
        if spec.get("warmup_min"):
            add("warmup", "Rozgrzewka", _minutes(spec["warmup_min"]), "spokojny trucht", spec["warmup_min"])
        add("work", "Tempo", _minutes(spec.get("tempo_min")), _pace(spec.get("pace_faster"), spec.get("pace_slower")),
            spec.get("tempo_min"))
        if spec.get("cooldown_min"):
            add("cooldown", "Schłodzenie", _minutes(spec["cooldown_min"]), "spokojny trucht", spec["cooldown_min"])
    elif kind == "threshold_intervals":
        if spec.get("warmup_min"):
            add("warmup", "Rozgrzewka", _minutes(spec["warmup_min"]), "spokojny trucht", spec["warmup_min"])
        add("work", "Odcinki", f"{spec.get('num_intervals')} × {_seconds(spec.get('work_sec'))}",
            _pace(spec.get("pace_faster"), spec.get("pace_slower")),
            repeated(spec.get("num_intervals"), spec.get("work_sec")))
        if spec.get("rest_sec"):
            add("rest", "Przerwy między odcinkami", _seconds(spec["rest_sec"]), "trucht",
                repeated(max(_number(spec.get("num_intervals")) - 1, 1), spec["rest_sec"]))
        if spec.get("cooldown_min"):
            add("cooldown", "Schłodzenie", _minutes(spec["cooldown_min"]), "spokojny trucht", spec["cooldown_min"])
    elif kind == "strides":
        add("main", "Bieg spokojny", _minutes(spec.get("base_min")), "swobodnie", spec.get("base_min"))
        add("work", "Przebieżki", f"{spec.get('num_strides')} × {_seconds(spec.get('stride_sec', 20))}",
            f"przerwy {_seconds(spec.get('rest_sec', 90))}",
            repeated(spec.get("num_strides"), _number(spec.get("stride_sec", 20)) + _number(spec.get("rest_sec", 90))))
        add("cooldown", "Schłodzenie", "2 min 30 s", "trucht", 2.5)
    return steps
