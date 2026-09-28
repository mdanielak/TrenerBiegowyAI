# -*- coding: utf-8 -*-
"""
Odswiez daty "ostatnio uzywany" dla treningow z biblioteki Garmina.

Usage:
  python update_workout_usage.py             # pokaz raport
  python update_workout_usage.py --delete    # + usun treningi nieuzywane > 3 miesiace

Dopasowanie: aktywnosc o nazwie "<lokalizacja> - <nazwa treningu>" albo dokladnie
nazwa treningu. Zwykly substring odpada — szablon "Bieg" pasowalby do prawie
wszystkiego.

Uruchamiaj raz w miesiacu. Usuwanie jest bezpieczne: kazdy trening ma w rejestrze
pelna definicje, wiec da sie go odtworzyc.
"""
import sys
import sqlite3
import logging

from logging_config import setup_logging
from config import ACT_DB
from services import workout_registry as reg

logger = logging.getLogger(__name__)

STALE_DAYS = 90


def load_activities():
    """Return activity dictionaries for every running activity."""
    with sqlite3.connect(ACT_DB) as conn:
        return [{'activity_id': activity_id, 'name': str(name), 'date': str(start_time)[:10]}
                for (activity_id, name, start_time) in conn.execute(
            "SELECT activity_id, name, start_time FROM activities WHERE sport='running'"
        )]


def _counts(workout, activity_name, activity_date, require_date=False):
    """Does this activity count as a run of this workout?

    A name match is only conclusive when the name identifies one workout. Two
    things break that: Garmin cuts long activity names off mid-word, and two
    library entries can end up sharing a name (a template rebuilt with a new
    structure). In both cases the name no longer says which workout was run,
    so the only thing that counts is a run on the day it was scheduled for.

    Erring towards matching is deliberate: a false match leaves an unused
    workout in the library, while a miss would mark a used workout as stale
    and get it deleted.
    """
    name = (workout.get('name') or '').strip()
    if not name:
        return False
    exact = activity_name == name or activity_name.endswith(' - ' + name)
    if not exact and not reg.matches_activity(name, activity_name):
        return False
    if exact and not require_date:
        return True
    scheduled = (workout.get('date') or '')[:10]
    return not scheduled or scheduled == activity_date


def shared_names(workouts):
    """Names used by more than one workout — matches on these can't identify one."""
    seen, shared = set(), set()
    for w in workouts:
        name = w.get('name')
        if not name:
            continue
        if name in seen:
            shared.add(name)
        seen.add(name)
    return shared


def _activity_dict(activity):
    """Accept old (name, date) test tuples while production uses dictionaries."""
    if isinstance(activity, dict):
        return activity
    name, date = activity
    return {'activity_id': None, 'name': name, 'date': date}


def last_used_for(workout, activities, require_date=False):
    """Most recent matching activity, or None."""
    normalized = [_activity_dict(activity) for activity in activities]
    known_id = workout.get('activity_id')
    if known_id is not None:
        exact = [a for a in normalized if a.get('activity_id') is not None and str(a['activity_id']) == str(known_id)]
        if exact:
            return max(exact, key=lambda a: a.get('date') or ''), 'id'
    matches = [a for a in normalized if _counts(workout, a.get('name', ''), a.get('date', ''), require_date=require_date)]
    if not matches:
        return None, None
    return max(matches, key=lambda a: a.get('date') or ''), 'heuristic'


def refresh(activities):
    """Update the registry with the current last-used date of every workout."""
    lib = reg.library('active')
    shared = shared_names(lib)
    changed = 0
    for w in lib:
        activity, match_method = last_used_for(w, activities, require_date=w.get('name') in shared)
        # An empty/incomplete scan must not erase a previously observed use.
        if activity is None:
            continue
        last = activity['date']
        if last != w.get('last_used') or activity.get('activity_id') != w.get('activity_id'):
            reg.record_usage(w['workout_id'], last, activity_id=activity.get('activity_id'),
                             match_method=match_method)
            changed += 1
    return changed


def main():
    setup_logging()
    delete = '--delete' in sys.argv

    activities = load_activities()
    changed = refresh(activities)
    print(f"Zaktualizowano daty dla {changed} treningow "
          f"(w bazie {len(activities)} aktywnosci)\n")

    lib = reg.library('active')
    dupes = shared_names(lib)
    print(f"=== BIBLIOTEKA GARMINA: {len(lib)} treningow ===")
    for w in sorted(lib, key=lambda x: x.get('last_used') or '', reverse=True):
        last = w.get('last_used') or 'nigdy'
        mark = ' <-- nazwa nieunikalna' if w.get('name') in dupes else ''
        print(f"  {w['workout_id']:>12} | ostatnio uzyty {last:>10} | {w.get('name')}{mark}")
    if dupes:
        print("\n  UWAGA: te nazwy wystepuja wiecej niz raz — dopasowanie po nazwie")
        print("  ich nie rozroznia, wiec liczy sie tylko bieg w dniu zaplanowania.")

    stale = reg.cleanup_candidates(STALE_DAYS)
    print(f"\n=== NIEUZYWANE > {STALE_DAYS} DNI: {len(stale)} ===")
    for w in stale:
        print(f"  {w['workout_id']:>12} | ostatnio {w.get('last_used') or 'nigdy':>10} | {w.get('name')}")

    if not stale:
        print("  (nic do usuniecia)")
        return

    if not delete:
        print("\nTryb raportu — nic nie usunieto. Dodaj --delete, aby usunac.")
        return

    print()
    # Import dopiero tutaj: tryb raportu dziala bez garminconnect i bez logowania.
    from services.workouts import GarminWorkout

    gw = GarminWorkout().login()
    for w in stale:
        gw.delete(w['workout_id'], reason=f"nieuzywany ponad {STALE_DAYS} dni")
    print(f"\nUsunieto {len(stale)} treningow. Definicje pozostaja w rejestrze "
          f"i mozna je odtworzyc.")


if __name__ == '__main__':
    main()
