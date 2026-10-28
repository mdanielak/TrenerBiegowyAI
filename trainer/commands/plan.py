"""Plan tygodniowy z terminala: ułóż, wypisz albo wyślij plan na zegarek."""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from services import plan as plan_service
from services.plan_conflicts import ON_CONFLICT

_ANSWERS = {"n": "overwrite", "d": "add", "a": "cancel"}


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
    parser.add_argument("--on-conflict", choices=ON_CONFLICT,
                        help="co zrobić, gdy plan lub treningi już istnieją (bez pytania)")
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


def _ask(question, rows, *, add_label, stdin=None) -> str:
    """Zapytaj o decyzję; bez terminala interaktywnego nic nie nadpisujemy."""
    stream = stdin or sys.stdin
    print(question)
    for row in rows:
        print(f"  - {row}")
    if not stream.isatty():
        print("Brak terminala interaktywnego: anulowano. Użyj --on-conflict, aby zdecydować z góry.")
        return "cancel"
    print(f"[n]adpisz / [d] {add_label} / [a]nuluj: ", end="", flush=True)
    return _ANSWERS.get(stream.readline().strip().lower()[:1], "cancel")


def _push(target, on_conflict=None, *, stdin=None) -> int:
    """Wyślij zapisany plan na zegarek; brak planu kończy się kodem 1."""
    from services.actions import push_plan_to_garmin
    from services.plan_conflicts import garmin_conflict_days
    from services.workout_registry import library

    plan = plan_service.load_week_plan(target)
    if plan is None:
        print("Najpierw ułóż plan na ten tydzień.", file=sys.stderr)
        return 1
    conflicts = garmin_conflict_days(plan, library("active"))
    if conflicts and on_conflict is None:
        rows = [f"{c['label']}: na zegarku {', '.join(e['name'] for e in c['existing'])}; nowy: {c['name']}"
                for c in conflicts]
        on_conflict = _ask("Na te dni są już treningi na zegarku:", rows, add_label="dodaj obok", stdin=stdin)
    if on_conflict == "cancel":
        print("Anulowano, nic nie wysłano.")
        return 0
    result = push_plan_to_garmin(week_start=target, on_conflict=on_conflict)
    replaced = f", zastąpiono {len(result['replaced'])}" if result.get("replaced") else ""
    print(f"Na zegarek wysłano {len(result['created'])} treningów, pominięto {result['skipped']}{replaced}.")
    return 0


def _generate(target, on_conflict=None, *, stdin=None) -> int:
    """Ułóż plan przez AI, zapisz go i wypisz."""
    from services.actions import generate_week_plan
    from services.plan_conflicts import plan_conflict_days

    existing = plan_service.load_week_plan(target)
    if existing is not None and on_conflict is None:
        rows = [f"{d['label']}: {d['name']}" + (" (na zegarku)" if d["on_watch"] else "")
                for d in plan_conflict_days(existing)] or ["same dni odpoczynku"]
        on_conflict = _ask("Na ten tydzień jest już plan:", rows, add_label="zapisz jako drugą wersję", stdin=stdin)
    if on_conflict == "cancel":
        print("Anulowano, plan bez zmian.")
        return 0
    try:
        plan = generate_week_plan(week_start=target, on_conflict=on_conflict if existing is not None else None)
    except ValueError as error:
        print(f"BŁĄD: {error}", file=sys.stderr)
        return 1
    if on_conflict == "add":
        print("Zapisano drugą wersję; obecny plan obowiązuje. Porównasz je na stronie planu.")
    _print_plan(plan)
    return 0


def main(argv=None, *, week=None, show=False, push=False, on_conflict=None, stdin=None) -> int:
    """Ułóż, wypisz albo wyślij plan tygodniowy."""
    if argv is not None:
        options = _parser().parse_args(argv)
        week, show, push, on_conflict = options.week, options.show, options.push, options.on_conflict

    target = _target_day(week)
    if show:
        return _show(target)
    if push:
        return _push(target, on_conflict, stdin=stdin)
    return _generate(target, on_conflict, stdin=stdin)
