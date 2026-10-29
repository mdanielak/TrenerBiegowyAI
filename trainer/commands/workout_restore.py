# -*- coding: utf-8 -*-
"""Odtworzenie treningu usuniętego z Garmina (np. przez „Nadpisz” przy wysyłce planu).

Bez numeru wypisuje ostatnio usunięte treningi z rejestru; z numerem wgrywa trening
ponownie z zapisanej definicji, na oryginalną albo podaną datę.
"""
from __future__ import annotations

from services.workout_registry import list_workouts, restore_entry

RECENT = 15


def main(workout_id: int | None = None, date_str: str | None = None, *, session_factory=None) -> int:
    if workout_id is None:
        deleted = sorted(list_workouts("deleted"), key=lambda e: e.get("deleted_at") or "", reverse=True)
        if not deleted:
            print("W rejestrze nie ma usuniętych treningów.")
            return 0
        print("Ostatnio usunięte treningi (odtworzysz je: python -m trainer workouts restore NUMER):")
        for entry in deleted[:RECENT]:
            print(f"  {entry['workout_id']}  {entry.get('date') or '—'}  {entry.get('name') or 'Trening'}"
                  f"  ({entry.get('reason') or 'usunięty'})")
        return 0
    try:
        entry = restore_entry(workout_id)
    except KeyError:
        print(f"Treningu {workout_id} nie ma w rejestrze.")
        return 1
    if entry.get("status") != "deleted":
        print(f"Trening {workout_id} nie był usunięty — nie ma czego odtwarzać.")
        return 1
    if session_factory is None:
        from trainer.garmin_workouts import GarminWorkout

        def session_factory():
            return GarminWorkout().login()
    session_factory().restore(entry, date_str)
    return 0
