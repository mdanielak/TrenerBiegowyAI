"""Plan tygodniowy z terminala: ułóż, wypisz albo wyślij plan na zegarek."""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from services import plan as plan_service


def _iso_date(value: str) -> str:
    """Sprawdź, czy tekst jest datą ISO, i zwróć go bez zmian."""
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("wymagana data ISO RRRR-MM-DD") from error
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trainer plan", description="Układa plan treningowy na tydzień pon–niedz")
    parser.add_argument("--week", type=_iso_date, help="dowolny dzień wybranego tygodnia (RRRR-MM-DD)")
    parser.add_argument("--show", action="store_true", help="wypisz zapisany plan, bez AI")
    parser.add_argument("--push", action="store_true", help="wyślij zapisany plan do Garmina, bez AI")
    return parser


def _target_day(week) -> datetime:
    """Dzienń, którego tydzień ma zostać zaplanowany lub pokazany."""
    if not week:
        return datetime.now()
    return datetime.fromisoformat(str(week)[:10])


def _print_plan(plan) -> None:
    """Wypisz plan dzień po dniu w kolejności dat."""
    print(f"PLAN {plan.get('start_date')} – {plan.get('end_date')}")
    if plan.get("focus"):
        print(f"Cel tygodnia: {plan['focus']}")
    if plan.get("summary"):
        print(plan["summary"])
    sessions = 0
    distance = 0.0
    for index, workout in enumerate(plan.get("workouts", []), start=1):
        kind = workout.get("type") or "rest"
        if kind != "rest":
            sessions += 1
            distance += float(workout.get("distance_km") or 0)
        details = []
        if workout.get("duration_min") is not None:
            details.append(f"{workout['duration_min']} min")
        if workout.get("distance_km") is not None:
            details.append(f"{workout['distance_km']} km")
        if workout.get("hr_zone"):
            details.append(str(workout["hr_zone"]))
        if workout.get("pace_target"):
            details.append(str(workout["pace_target"]))
        line = f"{index}. {workout.get('date')} — {workout.get('name')} ({kind})"
        if details:
            line += ": " + ", ".join(details)
        print(line)
        if workout.get("notes"):
            print(f"    Uwagi: {workout['notes']}")
    print(f"Razem: {sessions} treningów, {distance:.1f} km")


def _show(target) -> int:
    """Wypisz zapisany plan; brak planu kończy się kodem 1."""
    plan = plan_service.load_week_plan(target)
    if plan is None:
        print("Brak planu na ten tydzień. Uruchom: python -m trainer plan", file=sys.stderr)
        return 1
    _print_plan(plan)
    return 0


def _push(target) -> int:
    """Wyślij zapisany plan na zegarek; brak planu kończy się kodem 1."""
    from services.actions import push_plan_to_garmin

    if plan_service.load_week_plan(target) is None:
        print("Najpierw ułóż plan na ten tydzień.", file=sys.stderr)
        return 1
    result = push_plan_to_garmin(week_start=target)
    print(f"Na zegarek wysłano {len(result['created'])} treningów, pominięto {result['skipped']}.")
    return 0


def _generate(target) -> int:
    """Ułóż plan przez AI, zapisz go i wypisz."""
    from services.actions import generate_week_plan

    try:
        plan = generate_week_plan(week_start=target)
    except ValueError as error:
        print(f"BŁĄD: {error}", file=sys.stderr)
        return 1
    _print_plan(plan)
    return 0


def main(argv=None, *, week=None, show=False, push=False) -> int:
    """Ułóż, wypisz albo wyślij plan tygodniowy."""
    if argv is not None:
        options = _parser().parse_args(argv)
        week, show, push = options.week, options.show, options.push

    target = _target_day(week)
    if show:
        return _show(target)
    if push:
        return _push(target)
    return _generate(target)
