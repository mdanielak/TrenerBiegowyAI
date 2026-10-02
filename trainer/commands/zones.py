"""Odczyt i synchronizacja stref tętna Garmin Connect."""
from __future__ import annotations

from datetime import date

from .. import profile_store
from ..garmin_profile import parse_hr_zones


def _print_zones(profile: dict, heading: str = "Strefy tętna") -> None:
    print(f"{heading}: {profile.get('hr_zones', 'brak skonfigurowanych stref')}")
    source = profile.get("hr_zones_source")
    if source:
        print(f"Źródło: {source}")
    else:
        print("Ostrzeżenie: brak informacji o źródle stref; mogą być nieaktualne.")


def main(sync: bool = False) -> int:
    """Wyświetl lokalne strefy lub pobierz je z Garmin Connect."""
    try:
        before = profile_store.load_profile()
    except FileNotFoundError as exc:
        print(f"BŁĄD: {exc}")
        return 5
    if not sync:
        _print_zones(before)
        return 0

    try:
        from trainer.workouts import GarminWorkout

        workout = GarminWorkout().login()
        if workout.api is None:
            raise ValueError("brak połączenia z Garmin Connect")
        parsed = parse_hr_zones(workout.api.get_heart_rate_zones())
        if not parsed:
            print("BŁĄD: Garmin Connect nie zwrócił stref tętna.")
            return 1
        floors, hr_max = parsed
        source = f"Garmin Connect — synchronizacja {date.today().isoformat()}"
        after = profile_store.set_hr_zones(floors, hr_max, source)
    except (KeyError, TypeError, ValueError) as exc:
        print(f"BŁĄD: Garmin Connect zwrócił niepoprawne strefy tętna ({exc}).")
        return 1
    except Exception as exc:
        print(f"BŁĄD: nie udało się zsynchronizować stref tętna ({type(exc).__name__}).")
        return 1

    _print_zones(before, "Strefy przed synchronizacją")
    _print_zones(after, "Strefy po synchronizacji")
    return 0
