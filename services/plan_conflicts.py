# -*- coding: utf-8 -*-
"""Wykrywanie konfliktów przy układaniu i wysyłce planu oraz bezpieczne wersje planu.

Nic nie jest kasowane: zastąpione pliki planu trafiają do ``archive/``, a druga
wersja do ``variants/`` w katalogu miesiąca. Oba podkatalogi leżą poza zasięgiem
``plan_files.find_plan_file``, który czyta tylko pliki bezpośrednio w katalogu
miesiąca, więc nigdy nie staną się aktywnym planem przypadkiem.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from services import plan_files

ON_CONFLICT = ("overwrite", "add", "cancel")
ARCHIVE_DIR = "archive"
VARIANTS_DIR = "variants"
_VARIANT_NAME = re.compile(r"^\d{1,2}-\d{1,2}\.\d{8}-\d{6}\.json$")
_WEEKDAYS = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")
_KIND_LABELS = {"easy": "bieg łatwy", "recovery": "regeneracja", "long": "długi bieg", "tempo": "tempo",
                "threshold": "próg", "intervals": "interwały", "rest": "odpoczynek"}


class PlanConflictError(ValueError):
    """Akcja nadpisałaby istniejący plan lub treningi, a nie wybrano, co zrobić."""


def _day_label(iso_day: str) -> str:
    day = datetime.fromisoformat(iso_day)
    return f"{_WEEKDAYS[day.weekday()]} {day.day}.{day.month:02d}"


def _stamp(now=None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d-%H%M%S")


def plan_conflict_days(plan) -> list[dict]:
    """Dni istniejącego planu do pokazania w pytaniu o nadpisanie; pusty plan to brak konfliktu."""
    days = []
    for workout in (plan or {}).get("workouts") or []:
        kind = workout.get("type") or "rest"
        if kind == "rest" and not workout.get("garmin_upload"):
            continue
        days.append({
            "date": workout.get("date"),
            "label": _day_label(workout["date"]),
            "name": workout.get("name") or _KIND_LABELS.get(kind, kind),
            "minutes": workout.get("duration_min"),
            "on_watch": bool(workout.get("garmin_upload")),
        })
    return days


def garmin_conflict_days(plan, active_entries) -> list[dict]:
    """Dni do wysłania, na które rejestr ma już aktywny trening spoza tego planu."""
    from services.plan import plan_workout_to_garmin

    workouts = (plan or {}).get("workouts") or []
    own_ids = {w.get("garmin_workout_id") for w in workouts if w.get("garmin_workout_id")}
    by_date = {}
    for entry in active_entries or []:
        if entry.get("workout_id") in own_ids or entry.get("atp_plan_id"):
            continue
        by_date.setdefault(entry.get("date"), []).append(entry)
    conflicts = []
    for workout in workouts:
        if workout.get("garmin_upload") or plan_workout_to_garmin(workout) is None:
            continue
        existing = by_date.get(workout.get("date"))
        if existing:
            conflicts.append({
                "date": workout["date"],
                "label": _day_label(workout["date"]),
                "name": workout.get("name") or "Trening",
                "existing": [{"workout_id": e.get("workout_id"), "schedule_id": e.get("schedule_id"),
                              "name": e.get("name") or "trening"} for e in existing],
            })
    return conflicts


def week_plan_files(monday, plans_dir=None) -> list[Path]:
    """Wszystkie pliki planu pokrywające dni tygodnia, także rewizje w środku tygodnia."""
    files = []
    for offset in range(7):
        path = plan_files.find_plan_file(monday + timedelta(days=offset), plans_dir)
        if path is not None and path not in files:
            files.append(path)
    return files


def _move_to(path: Path, target_dir: Path, stamp: str) -> Path:
    target_dir.mkdir(exist_ok=True)
    target = target_dir / f"{path.stem}.{stamp}{path.suffix}"
    path.replace(target)
    twin = path.with_suffix(".csv")
    if twin.is_file():
        twin.replace(target.with_suffix(".csv"))
    return target


def archive_week(monday, plans_dir=None, *, now=None) -> list[Path]:
    """Odłóż obecne pliki planu tygodnia do archiwum; zwraca ich nowe ścieżki."""
    stamp = _stamp(now)
    return [_move_to(path, path.parent / ARCHIVE_DIR, stamp) for path in week_plan_files(monday, plans_dir)]


def save_variant(plan, plans_dir=None, *, now=None) -> Path:
    """Zapisz plan jako drugą wersję obok obecnego, bez zmiany aktywnego planu."""
    monday = datetime.strptime(plan["start_date"], "%Y-%m-%d")
    canonical = plan_files.plan_path(monday, plans_dir)
    target_dir = canonical.parent / VARIANTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{canonical.stem}.{_stamp(now)}.json"
    target.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _variant_path(monday, name, plans_dir=None) -> Path:
    """Ścieżka wersji z nazwy z formularza; odrzuca wszystko poza katalogiem wersji tygodnia."""
    if not isinstance(name, str) or not _VARIANT_NAME.match(name):
        raise ValueError("Nieznana wersja planu.")
    canonical = plan_files.plan_path(monday, plans_dir)
    if not name.startswith(f"{canonical.stem}."):
        raise ValueError("Ta wersja nie dotyczy wybranego tygodnia.")
    path = canonical.parent / VARIANTS_DIR / name
    if not path.is_file():
        raise ValueError("Ta wersja planu już nie istnieje.")
    return path


def list_variants(monday, plans_dir=None) -> list[tuple[str, dict]]:
    """Wersje planu dla tygodnia, najnowsza pierwsza."""
    canonical = plan_files.plan_path(monday, plans_dir)
    folder = canonical.parent / VARIANTS_DIR
    variants = []
    for path in sorted(folder.glob(f"{canonical.stem}.*.json"), reverse=True) if folder.is_dir() else []:
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if plan.get("start_date") == monday.date().isoformat() and _VARIANT_NAME.match(path.name):
            variants.append((path.name, plan))
    return variants


def activate_variant(monday, name, plans_dir=None, *, now=None) -> dict:
    """Uczyń wersję aktywnym planem; obecne pliki tygodnia trafiają do archiwum."""
    from services.plan import save_plan

    path = _variant_path(monday, name, plans_dir)
    plan = json.loads(path.read_text(encoding="utf-8"))
    archive_week(monday, plans_dir, now=now)
    save_plan(plan, plans_dir=plans_dir)
    _move_to(path, path.parent.parent / ARCHIVE_DIR, _stamp(now))
    return plan


def archive_variant(monday, name, plans_dir=None, *, now=None) -> Path:
    """Odłóż wersję do archiwum bez zmiany aktywnego planu."""
    path = _variant_path(monday, name, plans_dir)
    return _move_to(path, path.parent.parent / ARCHIVE_DIR, _stamp(now))
