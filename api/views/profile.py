# -*- coding: utf-8 -*-
"""Widok profilu biegacza na stronie ustawień."""
from __future__ import annotations

_PROFILE_RUNNER_FIELDS = (
    ("name", "Imię", ""),
    ("age", "Wiek", "lat"),
    ("weight_kg", "Waga", "kg"),
    ("height_cm", "Wzrost", "cm"),
    ("device", "Zegarek", ""),
)
_PROFILE_HEART_FIELDS = (
    ("hr_max", "Tętno maksymalne", "bpm"),
    ("hr_rest", "Tętno spoczynkowe", "bpm"),
    ("lactate_threshold_hr", "Tętno progowe (LTHR)", "bpm"),
    ("vo2max_running", "VO2max (bieg)", ""),
)
_PROFILE_GOAL_FIELDS = (
    ("target_race", "Zawody docelowe", ""),
    ("target_date", "Data celu", ""),
    ("target_time", "Czas docelowy", ""),
    ("target_hm", "Cel na półmaraton", ""),
    ("current_hm_record", "Obecny rekord półmaratonu", ""),
    ("training_frequency", "Liczba treningów w tygodniu", ""),
)


def _profile_rows(profile: dict, fields) -> list[dict]:
    """Zbuduj wiersze profilu tylko z zapisanych pól. Nic nie jest domyślane."""
    rows = []
    for key, label, unit in fields:
        value = profile.get(key)
        rows.append({
            "label": label,
            "value": None if value is None or value == "" else value,
            "unit": unit,
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
