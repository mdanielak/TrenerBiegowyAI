# -*- coding: utf-8 -*-
"""Widok profilu biegacza na stronie ustawień."""
from __future__ import annotations

# (klucz profilu, etykieta, jednostka, ikona wiersza w 07_ui_icons)
_PROFILE_RUNNER_FIELDS = (
    ("name", "Imię", "", "tile_person"),
    ("age", "Wiek", "lat", "tile_age"),
    ("weight_kg", "Waga", "kg", "tile_weight"),
    ("height_cm", "Wzrost", "cm", "tile_height"),
    ("device", "Zegarek", "", "tile_watch"),
)
_PROFILE_HEART_FIELDS = (
    ("hr_max", "Tętno maksymalne", "bpm", "tile_heart_max"),
    ("hr_rest", "Tętno spoczynkowe", "bpm", "tile_heart_rest"),
    ("lactate_threshold_hr", "Tętno progowe (LTHR)", "bpm", "tile_threshold"),
    ("vo2max_running", "VO2max (bieg)", "", "tile_vo2max"),
)
_PROFILE_GOAL_FIELDS = (
    ("target_race", "Zawody docelowe", "", "tile_race"),
    ("target_date", "Data celu", "", "tile_date"),
    ("target_time", "Czas docelowy", "", "tile_time"),
    ("target_hm", "Cel (dystans i czas)", "", "tile_finish"),
    ("current_hm_record", "Obecny rekord na dystansie celu", "", "tile_trophy"),
    ("training_frequency", "Liczba treningów w tygodniu", "", "tile_frequency"),
)


def profile_icon_references() -> list[str]:
    """Ścieżki ikon wierszy ustawień, dla testów i skryptu skalowania grafik."""
    fields = _PROFILE_RUNNER_FIELDS + _PROFILE_HEART_FIELDS + _PROFILE_GOAL_FIELDS
    return sorted({f"07_ui_icons/{icon}.png" for *_rest, icon in fields})


def _profile_rows(profile: dict, fields) -> list[dict]:
    """Zbuduj wiersze profilu tylko z zapisanych pól. Nic nie jest domyślane."""
    rows = []
    for key, label, unit, icon in fields:
        value = profile.get(key)
        rows.append({
            "label": label,
            "value": None if value is None or value == "" else value,
            "unit": unit,
            "icon": f"07_ui_icons/{icon}.png",
        })
    return rows


def _hr_zone_rows(profile: dict) -> list[dict]:
    """Pokaż strefy dokładnie tak, jak zapisał je profil — bez przeliczania granic."""
    zones = profile.get("hr_zones")
    rows = []
    if isinstance(zones, str) and zones.strip():
        for entry in zones.split(","):
            parts = entry.strip().split(" ", 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                rows.append({"name": parts[0], "range": parts[1].replace("-", "–")})
        if rows:
            return rows
    floors = profile.get("hr_zone_floors")
    if isinstance(floors, dict):
        for key in ("z1", "z2", "z3", "z4", "z5"):
            if floors.get(key) is not None:
                rows.append({"name": key.upper(), "range": f"od {floors[key]}"})
    return rows
