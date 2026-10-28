"""Lokalny profil biegacza oraz opcjonalne odświeżenie z Garmin Connect."""
from __future__ import annotations

from datetime import date

from .. import profile_store
from ..garmin_profile import fetch_snapshot

# Kolejność wyświetlania: etykieta i opcjonalna jednostka.
_LABELS: tuple[tuple[str, str, str], ...] = (
    ("name", "Imię", ""),
    ("age", "Wiek", "lat"),
    ("weight_kg", "Waga", "kg"),
    ("height_cm", "Wzrost", "cm"),
    ("hr_max", "Tętno maksymalne", "bpm"),
    ("hr_rest", "Tętno spoczynkowe", "bpm"),
    ("lactate_threshold_hr", "Próg mleczanowy HR", "bpm"),
    ("vo2max_running", "VO2max (bieg)", ""),
    ("hr_zones", "Strefy tętna", ""),
    ("hr_zones_source", "Źródło stref", ""),
    ("current_hm_record", "Aktualny rekord", ""),
    ("target_race", "Docelowy bieg", ""),
    ("target_time", "Zakładany czas", ""),
    ("target_hm", "Cel", ""),
    ("target_date", "Data celu", ""),
    ("training_frequency", "Częstotliwość", ""),
    ("device", "Urządzenie", ""),
)

# Pola liczbowe, w których tekstowy zakres typu "75-76" oznacza brak pomiaru.
_NUMERIC = ("age", "weight_kg", "height_cm", "hr_max", "hr_rest", "lactate_threshold_hr")

# Klucze snapshotu Garmina mapowane na nazwy pól profilu.
_FROM_GARMIN = (
    ("age", "age"),
    ("weight", "weight_kg"),
    ("height", "height_cm"),
    ("hr_rest", "hr_rest"),
    ("lactate_threshold_hr", "lactate_threshold_hr"),
    ("vo2max_running", "vo2max_running"),
)


def _render(profile: dict) -> None:
    """Wypisz profil czytelnie, zamiast zrzucać słownik Pythona."""
    print("=== Profil biegacza ===")
    width = max(len(label) for _, label, _ in _LABELS) + 1
    for key, label, unit in _LABELS:
        if key not in profile:
            continue
        # "target_hm" jest tylko złożeniem biegu i czasu dla zgodności wstecznej,
        # więc pokazujemy je wyłącznie w starszych profilach bez pól składowych.
        if key == "target_hm" and "target_race" in profile:
            continue
        value = profile[key]
        suffix = f" {unit}" if unit and value not in ("", None) else ""
        print(f"{label + ':':{width}} {value}{suffix}")
    shown = {key for key, _, _ in _LABELS}
    extra = [key for key in profile if key not in shown and key != "hr_zone_floors"]
    if extra:
        print("Pozostałe pola: " + ", ".join(sorted(extra)))
    unclear = [label for key, label, _ in _LABELS
               if key in _NUMERIC and not isinstance(profile.get(key), (int, float))
               and profile.get(key) not in ("", None)]
    if unclear:
        print("\nUwaga: te pola nie są liczbami (np. zapisany zakres): " + ", ".join(unclear) + ".")
        print("Odśwież je z Garmina: python -m trainer profile --sync")


def main(sync: bool = False) -> int:
    """Pokaż profil, a z ``--sync`` odśwież fizjologię i strefy z Garmina."""
    try:
        profile = profile_store.load_profile()
    except FileNotFoundError:
        print("BŁĄD: Nie znaleziono lokalnego profilu. Uruchom: python -m trainer setup")
        return 5
    if not sync:
        _render(profile)
        return 0

    try:
        from trainer.garmin_workouts import GarminWorkout

        snapshot = fetch_snapshot(GarminWorkout().login().api)
    except Exception as exc:
        print(f"BŁĄD: nie udało się pobrać profilu z Garmin Connect ({type(exc).__name__}).")
        return 1
    if not snapshot:
        print("BŁĄD: Garmin Connect nie zwrócił żadnych danych profilu.")
        return 1

    floors = snapshot.get("hr_zone_floors")
    hr_max = snapshot.get("hr_max")
    if floors and hr_max:
        profile_store.set_hr_zones(floors, hr_max, f"Garmin Connect — synchronizacja {date.today().isoformat()}")
    # Dni treningowe należą do preferencji, nie do profilu, więc ich tu nie zapisujemy.
    fields = {target: snapshot[source] for source, target in _FROM_GARMIN if source in snapshot}
    if fields:
        profile_store.update_profile(**fields)
    print("Profil zaktualizowany z Garmin Connect.")
    _render(profile_store.load_profile())
    return 0
