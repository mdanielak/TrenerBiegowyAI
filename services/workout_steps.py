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
    """Lista kroków {label, time, target, phase}; nieznany rodzaj to pusta lista."""
    spec = spec or {}
    kind = spec.get("kind")
    steps = []

    def add(phase, label, time, target=""):
        steps.append({"phase": phase, "label": label, "time": time, "target": target})

    if kind in ("easy_run", "long_run"):
        add("main", "Bieg spokojny" if kind == "easy_run" else "Długi bieg", _minutes(spec.get("duration_min")),
            "swobodnie, rozmowa bez zadyszki")
    elif kind == "hr_zone_run":
        warmup = int(spec.get("warmup_min") or 0)
        if warmup:
            add("warmup", "Rozgrzewka", _minutes(warmup),
                " · ".join(filter(None, [_pace(spec.get("warmup_pace_faster"), spec.get("warmup_pace_slower")),
                                         "bez alarmu tętna"])))
        add("main", "Bieg w strefie", _minutes(max(0, int(spec.get("duration_min") or 0) - warmup)),
            " · ".join(filter(None, [_zone(spec.get("zone_number"), floors),
                                     "zegarek ostrzeże po przekroczeniu"])))
    elif kind == "easy_run_zoned":
        if spec.get("warmup_km"):
            add("warmup", "Rozgrzewka", f"{spec['warmup_km']} km",
                _pace(spec.get("warmup_pace_faster"), spec.get("warmup_pace_slower")))
        elif spec.get("warmup_min"):
            add("warmup", "Rozgrzewka", _minutes(spec["warmup_min"]),
                _pace(spec.get("warmup_pace_faster"), spec.get("warmup_pace_slower")))
        add("main", "Bieg w strefie", _minutes(spec.get("main_min")), _zone(spec.get("zone_number", 2), floors))
        if spec.get("strides"):
            add("work", "Przebieżki", f"{spec['strides']} × {_seconds(spec.get('stride_sec', 20))}",
                f"przerwy {_seconds(spec.get('stride_rest_sec', 90))} spokojnie")
        if spec.get("cooldown_min"):
            add("cooldown", "Schłodzenie", _minutes(spec["cooldown_min"]), "trucht")
    elif kind == "tempo_run":
        if spec.get("warmup_min"):
            add("warmup", "Rozgrzewka", _minutes(spec["warmup_min"]), "spokojny trucht")
        add("work", "Tempo", _minutes(spec.get("tempo_min")), _pace(spec.get("pace_faster"), spec.get("pace_slower")))
        if spec.get("cooldown_min"):
            add("cooldown", "Schłodzenie", _minutes(spec["cooldown_min"]), "spokojny trucht")
    elif kind == "threshold_intervals":
        if spec.get("warmup_min"):
            add("warmup", "Rozgrzewka", _minutes(spec["warmup_min"]), "spokojny trucht")
        add("work", "Odcinki", f"{spec.get('num_intervals')} × {_seconds(spec.get('work_sec'))}",
            _pace(spec.get("pace_faster"), spec.get("pace_slower")))
        if spec.get("rest_sec"):
            add("rest", "Przerwy między odcinkami", _seconds(spec["rest_sec"]), "trucht")
        if spec.get("cooldown_min"):
            add("cooldown", "Schłodzenie", _minutes(spec["cooldown_min"]), "spokojny trucht")
    elif kind == "strides":
        add("main", "Bieg spokojny", _minutes(spec.get("base_min")), "swobodnie")
        add("work", "Przebieżki", f"{spec.get('num_strides')} × {_seconds(spec.get('stride_sec', 20))}",
            f"przerwy {_seconds(spec.get('rest_sec', 90))}")
        add("cooldown", "Schłodzenie", "2 min 30 s", "trucht")
    return steps
