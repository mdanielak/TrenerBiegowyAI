"""Bezpieczny zapis lokalnego profilu biegacza."""
from __future__ import annotations

import json

from trainer.files import write_atomic
from collections.abc import Mapping

from .config import SETTINGS


_ZONE_KEYS = ("z1", "z2", "z3", "z4", "z5")


def load_profile() -> dict:
    """Wczytaj lokalny profil lub zgłoś zrozumiały błąd jego braku."""
    path = SETTINGS.runner_profile_local
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError("Nie znaleziono lokalnego profilu: local/profile.json") from exc
    if not isinstance(data, dict):
        raise ValueError("Profil biegacza musi być obiektem JSON.")
    return data


def save_profile(data) -> None:
    """Atomowo zapisz profil jako UTF-8, bez zmiany kolejności kluczy."""
    if not isinstance(data, Mapping):
        raise ValueError("Profil biegacza musi być słownikiem.")
    write_atomic(SETTINGS.runner_profile_local, json.dumps(dict(data), ensure_ascii=False, indent=2) + "\n")


def update_profile(**fields) -> dict:
    """Uaktualnij wskazane pola, zachowując pola nieznane starszym modułom."""
    profile = load_profile()
    profile.update(fields)
    save_profile(profile)
    return profile


def set_hr_zones(floors: dict, hr_max: int, source: str) -> dict:
    """Zapisz strefy HR w formie strukturalnej i kompatybilnej tekstowej."""
    if set(floors) != set(_ZONE_KEYS):
        raise ValueError("Progi stref muszą zawierać klucze z1, z2, z3, z4 i z5.")
    try:
        normalized = {key: int(floors[key]) for key in _ZONE_KEYS}
        maximum = int(hr_max)
    except (TypeError, ValueError) as exc:
        raise ValueError("Progi stref i HR maksymalne muszą być liczbami całkowitymi.") from exc
    if maximum < normalized["z5"]:
        raise ValueError("HR maksymalne nie może być niższe od progu Z5.")

    ranges = []
    for index, key in enumerate(_ZONE_KEYS):
        upper = maximum if index == len(_ZONE_KEYS) - 1 else normalized[_ZONE_KEYS[index + 1]] - 1
        ranges.append(f"Z{index + 1} {normalized[key]}-{upper}")
    return update_profile(
        hr_max=maximum,
        hr_zones=", ".join(ranges),
        hr_zone_floors=normalized,
        hr_zones_source=str(source),
    )
