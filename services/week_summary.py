# -*- coding: utf-8 -*-
"""Podsumowanie tygodnia: plan a wykonanie do dziś i propozycja na kolejny tydzień.

Czysta logika na przekazanych danych, bez AI. Propozycja „odpuść / utrzymaj / dołóż” to ta sama
decyzja, którą dostanie trener przy układaniu następnego planu (services.runner_profile).
"""
from __future__ import annotations

from datetime import date, timedelta

from services.activity_matching import find_activity_for_workout
from services.runner_profile import decision_reason

_WEEKDAYS = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")
_PROPOSALS = {
    "odpusc": "Odpuść — kolejny tydzień wyraźnie lżejszy",
    "utrzymaj": "Utrzymaj — podobnie jak w tym tygodniu, bez dokładania",
    "doloz": "Dołóż — kolejny tydzień może być o 5–10% większy",
}
# Propozycja ma sens, gdy większość tygodnia jest już za biegaczem: od piątku.
_PROPOSAL_FROM_WEEKDAY = 4


def _minutes(value) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def build_week_summary(plan, activities, *, today: date, runner=None) -> dict | None:
    """Zwróć podsumowanie tygodnia albo None, gdy żaden zaplanowany trening jeszcze nie minął."""
    try:
        monday = date.fromisoformat(str((plan or {}).get("start_date"))[:10])
    except ValueError:
        return None
    activities = [a for a in activities or [] if isinstance(a, dict)]
    # Dzisiejszy trening liczy się tylko wtedy, gdy już jest zrobiony; do końca dnia nie jest „opuszczony”.
    due = [w for w in plan.get("workouts") or []
           if isinstance(w, dict) and w.get("type") != "rest"
           and (str(w.get("date") or "") < today.isoformat()
                or (str(w.get("date") or "") == today.isoformat()
                    and find_activity_for_workout(workout=w, activities=activities)[0] is not None))]
    if not due:
        return None

    done = shortened = 0
    planned_min = done_min = 0.0
    missed = []
    for workout in due:
        planned_min += _minutes(workout.get("duration_min"))
        activity, _ = find_activity_for_workout(workout=workout, activities=activities)
        if activity is None:
            day = date.fromisoformat(workout["date"])
            missed.append(f"{_WEEKDAYS[day.weekday()]} — {workout.get('name') or 'trening'}")
            continue
        done += 1
        actual = _minutes(activity.get("duration_min"))
        done_min += actual
        if workout.get("duration_min") and actual < 0.8 * _minutes(workout.get("duration_min")):
            shortened += 1

    sunday = monday + timedelta(days=6)
    week_runs = [a for a in activities if str(a.get("type") or "").startswith("running")
                 and monday.isoformat() <= str(a.get("date") or "")[:10] <= sunday.isoformat()]
    over = today > sunday
    proposal = None
    if runner and not over and today.weekday() >= _PROPOSAL_FROM_WEEKDAY and runner.get("decision") in _PROPOSALS:
        proposal = {"key": runner["decision"], "label": _PROPOSALS[runner["decision"]],
                    "reason": decision_reason(runner)}
    return {
        "over": over,
        "due": len(due),
        "done": done,
        "shortened": shortened,
        "missed": missed,
        "planned_min": round(planned_min),
        "done_min": round(done_min),
        "km": round(sum(_minutes(a.get("distance_km")) for a in week_runs), 1),
        "runs": len(week_runs),
        "proposal": proposal,
    }


def summarize_week(stored, data, today, profile_provider) -> tuple[dict | None, dict | None]:
    """Podsumowanie tygodnia i profil biegacza, z którego liczy się propozycja na kolejny tydzień.

    Ten sam profil dostaje trener przy układaniu planu, więc strona Plan i ocena tygodnia mówią to samo.
    Bez profilu (błąd odczytu danych) podsumowanie zostaje bez propozycji, same liczby nadal są.
    """
    import logging

    if not stored or not isinstance(data, dict):
        return None, None
    runner = None
    try:
        from ai.context import build_training_context
        from services.plan import _plan_trends
        from services.runner_profile import build_runner_profile

        training = build_training_context(data, plan=None, today=today)
        runner = build_runner_profile(
            activities=data.get("activities"), profile=profile_provider(), today=today.date(),
            rhr_trend=((_plan_trends(data, today.date()) or {}).get("metrics") or {}).get("rhr"),
            previous_plan=stored, pain=bool((training.get("journal") or {}).get("pain_days")))
    except Exception:  # noqa: BLE001 - bez propozycji strona planu nadal pokazuje liczby
        logging.getLogger(__name__).warning("Could not build the weekly proposal")
    try:
        return build_week_summary(stored, data.get("activities"), today=today.date(), runner=runner), runner
    except (KeyError, TypeError, ValueError):
        return None, runner
