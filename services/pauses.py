# -*- coding: utf-8 -*-
"""Przerwy treningowe z poziomu dashboardu: walidacja, widok listy i kolizje z planem.

Zapis i odczyt robi istniejące ``trainer.preferences``; plan AI już traktuje dzień
w przerwie jako odpoczynek (``services.plan._normalize_day``).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from services import plan_files

PAUSE_TYPES = {
    "illness": "Choroba",
    "vacation": "Wyjazd",
    "break": "Przerwa",
    "medical": "Zabieg",
    "recovery": "Rekonwalescencja",
}
NOTE_LIMIT = 120
PAST_DAYS = 30
FUTURE_DAYS = 365
# Kolizje z planem sprawdzamy na tyle dni do przodu; dalsze plany zwykle jeszcze nie istnieją.
OVERLAP_DAYS = 21


def validate_pause(*, pause_type, start, end, note, today: date) -> dict:
    """Sprawdź pola formularza; błąd to ValueError z komunikatem dla użytkownika."""
    if pause_type not in PAUSE_TYPES:
        raise ValueError("Wybierz rodzaj przerwy.")
    try:
        start_day, end_day = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    except ValueError:
        raise ValueError("Podaj daty w formacie RRRR-MM-DD.") from None
    if end_day < start_day:
        raise ValueError("Koniec przerwy nie może być przed jej początkiem.")
    if start_day < today - timedelta(days=PAST_DAYS):
        raise ValueError(f"Przerwa może zaczynać się najwyżej {PAST_DAYS} dni wstecz.")
    if end_day > today + timedelta(days=FUTURE_DAYS):
        raise ValueError("Przerwa może trwać najwyżej rok naprzód.")
    note = " ".join(str(note or "").split())[:NOTE_LIMIT]
    label = PAUSE_TYPES[pause_type]
    return {"start_date": start_day.isoformat(), "end_date": end_day.isoformat(), "type": pause_type,
            # AI planu widzi tylko powód, więc rodzaj trafia na jego początek.
            "reason": f"{label}: {note}" if note else label}


def pause_views(pauses, *, today: date) -> list[dict]:
    """Bieżące i przyszłe przerwy, najbliższa pierwsza; zakończone są pomijane."""
    views = []
    for pause in pauses or []:
        start, end = str(pause.get("start_date", "")), str(pause.get("end_date", ""))
        if not start or not end or end < today.isoformat():
            continue
        views.append({
            "start_date": start,
            "end_date": end,
            "type_label": PAUSE_TYPES.get(pause.get("type"), "Przerwa"),
            "reason": pause.get("reason") or "",
            "is_active": start <= today.isoformat() <= end,
        })
    return sorted(views, key=lambda item: item["start_date"])


def planned_workouts_in(start: str, end: str, *, today: date) -> list[str]:
    """Daty w przerwie (od dziś, do OVERLAP_DAYS naprzód), na które plan ma trening."""
    first = max(date.fromisoformat(start), today)
    last = min(date.fromisoformat(end), today + timedelta(days=OVERLAP_DAYS))
    days = []
    current = first
    while current <= last:
        moment = datetime.combine(current, datetime.min.time())
        try:
            plan = plan_files.load_plan(moment)
        except ValueError:
            plan = None
        workout = plan_files.get_today_workout_from_plan(plan, moment) if plan else None
        if workout and workout.get("type") != "rest":
            days.append(current.isoformat())
        current += timedelta(days=1)
    return days
