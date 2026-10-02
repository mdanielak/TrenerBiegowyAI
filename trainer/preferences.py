"""Odczyt i atomowy zapis prywatnych preferencji treningowych."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

from .config import SETTINGS


_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _default_preferences() -> dict:
    return {
        "version": 1,
        "days": {day: {"available": False, "min_minutes": 0, "max_minutes": 0} for day in _DAYS},
        "max_quality_sessions_per_week": 0,
        "notes": "",
    }


def _preferences_path() -> Path:
    return SETTINGS.local_dir / "training_preferences.json"


def _normalize(data: object) -> dict:
    result = _default_preferences()
    if not isinstance(data, dict):
        return result
    result.update(data)  # zachowuje pola prywatnego, starszego formatu
    source_days = data.get("days", {})
    days = copy.deepcopy(_default_preferences()["days"])
    if isinstance(source_days, dict):
        for day, raw in source_days.items():
            if day not in _DAYS:
                continue
            if isinstance(raw, bool):
                days[day]["available"] = raw
            elif isinstance(raw, dict):
                days[day].update(raw)
    result["version"] = 1
    result["days"] = days
    return result


def load_preferences() -> dict:
    """Wczytaj preferencje; brak pliku oznacza bezpieczne wartości domyślne."""
    try:
        raw = json.loads(_preferences_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _default_preferences()
    return _normalize(raw)


def save_preferences(data) -> None:
    """Atomowo zapisz preferencje, zachowując nieznane pola przekazane przez klienta."""
    if not isinstance(data, dict):
        raise ValueError("Preferencje treningowe muszą być słownikiem.")
    path = _preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(_normalize(data), ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def get_weekly_availability(day: str | None = None) -> dict:
    """Zwróć dostępność tygodnia albo pojedynczego dnia."""
    days = load_preferences()["days"]
    if day is None:
        return days
    if day not in _DAYS:
        raise ValueError("Dzień musi mieć skrót od mon do sun.")
    return days[day]


def set_weekly_availability(day: str, available: bool, min_minutes: int = 0, max_minutes: int = 0) -> dict:
    """Ustaw dostępność jednego dnia, zachowując pozostałe preferencje."""
    if day not in _DAYS:
        raise ValueError("Dzień musi mieć skrót od mon do sun.")
    preferences = load_preferences()
    preferences["days"][day] = {
        **preferences["days"].get(day, {}),
        "available": bool(available),
        "min_minutes": int(min_minutes),
        "max_minutes": int(max_minutes),
    }
    save_preferences(preferences)
    return preferences["days"][day]
