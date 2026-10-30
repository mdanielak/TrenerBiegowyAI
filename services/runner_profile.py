# -*- coding: utf-8 -*-
"""Profil biegacza liczony przy każdym planie: poziom, objętość, tętno, ostatni tydzień, cel, ciało.

Czysta logika na przekazanych danych. Liczony co tydzień, więc plan sam się dostosowuje:
gdy biegacz biega więcej i regularniej, rośnie poziom; gdy tętno albo wykonanie planu
sygnalizują zmęczenie, decyzja tygodnia każe odpuścić.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from services.activity_matching import find_activity_for_workout

# Odpowiedź z kreatora → przybliżony staż w miesiącach.
RUNNING_SINCE = {"start": 0, "under6": 3, "6to24": 12, "over24": 30}
RUNNING_SINCE_LABELS = {"start": "dopiero zaczyna", "under6": "do 6 miesięcy", "6to24": "6–24 miesiące",
                        "over24": "ponad 2 lata"}
LEVEL_LABELS = {"poczatkujacy": "początkujący", "regularny": "regularny", "zaawansowany": "zaawansowany"}
DECISION_LABELS = {
    "odpusc": "odpuść — lżejszy tydzień (mniej czasu niż ostatnio)",
    "utrzymaj": "utrzymaj — podobna objętość jak ostatnio, bez dokładania",
    "doloz": "dołóż — objętość może wzrosnąć o 5–10%",
}
# Mnożnik największego tygodnia z ostatnich czterech, którego plan nie przekroczy.
WEEK_LIMIT = {"odpusc": 0.9, "utrzymaj": 1.0, "doloz": 1.1}
WINDOW_DAYS = 28


def _run_day(activity) -> date | None:
    try:
        return date.fromisoformat(str(activity.get("date") or "")[:10])
    except ValueError:
        return None


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _runs(activities):
    return [a for a in activities or [] if isinstance(a, dict) and str(a.get("type") or "").startswith("running")
            and _run_day(a) is not None]


def _returning(run_days: list[date], today: date) -> bool:
    """Biega znowu (ostatnie 14 dni) po co najmniej trzech tygodniach bez biegania."""
    recent = [d for d in run_days if d >= today - timedelta(days=14)]
    if not recent:
        return False
    before = [d for d in run_days if d < min(recent)]
    return bool(before) and (min(recent) - max(before)).days >= 21


def _adherence(previous_plan, activities, monday: date):
    """Ile treningów z poprzedniego tygodnia wykonano i ile z nich było wyraźnie krótszych."""
    planned = [w for w in (previous_plan or {}).get("workouts") or []
               if isinstance(w, dict) and w.get("type") != "rest" and str(w.get("date") or "") < monday.isoformat()]
    if not planned:
        return None, 0, 0
    done = shortened = 0
    for workout in planned:
        activity, _ = find_activity_for_workout(workout=workout, activities=activities)
        if activity is None:
            continue
        done += 1
        planned_min, actual = _number(workout.get("duration_min")), _number(activity.get("duration_min"))
        if planned_min and actual is not None and actual < 0.8 * planned_min:
            shortened += 1
    return done / len(planned), done, shortened


def _frequency(text) -> int | None:
    """Liczba treningów w tygodniu z kreatora („3 treningi w tygodniu”)."""
    match = re.search(r"\d", str(text or ""))
    return int(match.group(0)) if match and 1 <= int(match.group(0)) <= 7 else None


def _phase(target_date, today: date):
    try:
        race = date.fromisoformat(str(target_date or "")[:10])
    except ValueError:
        return None, None
    weeks = (race - today).days // 7
    if weeks < 0:
        return None, None
    return weeks, ("taper" if weeks <= 2 else "budowanie" if weeks <= 12 else "baza")


def build_runner_profile(*, activities, profile, today: date, rhr_trend=None, previous_plan=None,
                         pain=False) -> dict:
    """Profil do promptu i do bezpieczników planu.

    ``rhr_trend``: {"recent": średnia 7 dni, "average": średnia 12 tygodni} tętna spoczynkowego.
    ``previous_plan``: plan poprzedniego tygodnia (do policzenia wykonania).
    """
    profile = profile or {}
    monday = today - timedelta(days=today.weekday())
    runs = _runs(activities)
    window = [a for a in runs if monday - timedelta(days=WINDOW_DAYS) <= _run_day(a) < monday]
    weeks = {}
    for activity in window:
        key = (monday - _run_day(activity)).days // 7
        week = weeks.setdefault(key, {"runs": 0, "km": 0.0, "minutes": 0.0})
        week["runs"] += 1
        week["km"] += _number(activity.get("distance_km")) or 0
        week["minutes"] += _number(activity.get("duration_min")) or 0
    durations = [_number(a.get("duration_min")) for a in window if _number(a.get("duration_min"))]
    longest = round(max(durations)) if durations else None
    run_days = sorted(_run_day(a) for a in runs)
    # Zegarek z historią krótszą niż 3 tygodnie nie mówi jeszcze, jak ktoś biega.
    short_history = not run_days or (monday - run_days[0]).days < 21
    runs_per_week = len(window) / 4
    km_per_week = sum(w["km"] for w in weeks.values()) / 4

    since = profile.get("running_since")
    months = RUNNING_SINCE.get(since)
    if short_history and months is not None:
        level = "poczatkujacy" if months < 6 else "regularny"
    elif (months is not None and months < 6) or runs_per_week < 2 or (longest or 0) < 45:
        level = "poczatkujacy"
    elif (months is None or months >= 24) and runs_per_week >= 4 and ((longest or 0) >= 90 or km_per_week >= 40):
        level = "zaawansowany"
    else:
        level = "regularny"

    floors = profile.get("hr_zone_floors") or {}
    z3 = _number(floors.get("z3"))
    last_two_weeks = [a for a in runs if _run_day(a) >= monday - timedelta(days=14)]
    with_hr = [a for a in last_two_weeks if _number(a.get("avg_hr"))]
    too_hard = sum(1 for a in with_hr if z3 and _number(a.get("avg_hr")) >= z3)
    rhr_recent = _number((rhr_trend or {}).get("recent"))
    rhr_normal = _number((rhr_trend or {}).get("average"))
    rhr_up = round(rhr_recent - rhr_normal) if rhr_recent is not None and rhr_normal is not None else None

    adherence, done, shortened = _adherence(previous_plan, activities, monday)
    returning = _returning(run_days, today)
    if pain or (rhr_up is not None and rhr_up >= 5) or (adherence is not None and adherence < 0.6):
        decision = "odpusc"
    elif adherence is None or adherence < 0.9 or returning or (len(with_hr) >= 2 and too_hard * 2 >= len(with_hr)):
        decision = "utrzymaj"
    else:
        decision = "doloz"

    weight, height = _number(profile.get("weight_kg")), _number(profile.get("height_cm"))
    weeks_to_race, phase = _phase(profile.get("target_date"), today)
    return {
        "level": "poczatkujacy" if returning else level,
        "returning": returning,
        "running_since": since,
        "short_history": short_history,
        "runs_per_week": round(runs_per_week, 1),
        "km_per_week": round(km_per_week, 1),
        "longest_min": longest,
        "max_week_minutes": round(max((w["minutes"] for w in weeks.values()), default=0)) or None,
        "regular_weeks": sum(1 for w in weeks.values() if w["runs"] >= 2),
        "easy_runs_with_hr": len(with_hr),
        "runs_above_z2": too_hard,
        "rhr_up": rhr_up,
        "vo2max": _number(profile.get("vo2max_running")),
        "adherence": adherence,
        "done": done,
        "shortened": shortened,
        "pain": bool(pain),
        "decision": decision,
        "goal_distance": profile.get("target_distance"),
        "frequency": _frequency(profile.get("training_frequency")),
        "weeks_to_race": weeks_to_race,
        "phase": phase,
        "age": _number(profile.get("age")),
        "sex": profile.get("sex"),
        "bmi": round(weight / (height / 100) ** 2, 1) if weight and height else None,
        "health_notes": str(profile.get("health_notes") or "").strip()[:300],
    }


def profile_lines(runner: dict) -> list[str]:
    """Sekcja PROFIL BIEGACZA w wiadomości do AI: fakty i decyzja tygodnia."""
    def value(number, unit=""):
        return "brak" if number is None else f"{str(number).replace('.', ',')}{unit}"

    lines = [f"- poziom: {LEVEL_LABELS[runner['level']]}"
             + (" (powrót po co najmniej 3 tygodniach przerwy)" if runner["returning"] else "")]
    if runner.get("running_since"):
        lines.append(f"- biega regularnie: {RUNNING_SINCE_LABELS.get(runner['running_since'], 'brak')}")
    if runner["short_history"]:
        lines.append("- historia z zegarka: krótsza niż 3 tygodnie, liczby poniżej są niepełne")
    lines.append(f"- ostatnie 4 tygodnie: średnio {value(runner['runs_per_week'])} biegu/tydz., "
                 f"{value(runner['km_per_week'], ' km')}/tydz., najdłuższy bieg {value(runner['longest_min'], ' min')}, "
                 f"największy tydzień {value(runner['max_week_minutes'], ' min')}")
    if runner["easy_runs_with_hr"]:
        lines.append(f"- tętno na biegach (2 tyg.): {runner['runs_above_z2']} z {runner['easy_runs_with_hr']} "
                     "biegów ze średnim tętnem powyżej strefy 2")
    if runner["rhr_up"] is not None:
        lines.append(f"- tętno spoczynkowe: {runner['rhr_up']:+d} bpm wobec normy z 12 tygodni")
    if runner["adherence"] is not None:
        lines.append(f"- poprzedni tydzień: wykonano {round(runner['adherence'] * 100)}% treningów z planu"
                     + (f", {runner['shortened']} wyraźnie krótszych" if runner["shortened"] else ""))
    if runner["vo2max"]:
        lines.append(f"- VO2max z zegarka: {value(runner['vo2max'])}")
    if runner["weeks_to_race"] is not None:
        lines.append(f"- do startu: {runner['weeks_to_race']} tyg. (faza: {runner['phase']})")
    body = [f"wiek {value(runner['age'] and int(runner['age']))}"]
    if runner.get("sex") in ("female", "male"):
        body.append("kobieta" if runner["sex"] == "female" else "mężczyzna")
    if runner["bmi"]:
        body.append(f"BMI {value(runner['bmi'])}")
    lines.append("- ciało: " + ", ".join(body))
    if runner["health_notes"]:
        lines.append(f"- zdrowie (opis biegacza): {runner['health_notes']}")
    lines.append(f"- DECYZJA TYGODNIA: {DECISION_LABELS[runner['decision']]}")
    return lines
