"""Odczyt i atomowy zapis prywatnych preferencji treningowych."""
from __future__ import annotations

import copy
import json

from trainer.files import write_atomic
from datetime import date
from pathlib import Path

from .config import SETTINGS


_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _default_preferences() -> dict:
    return {
        "version": 1,
        "days": {day: {"available": False, "min_minutes": 0, "max_minutes": 0} for day in _DAYS},
        "max_quality_sessions_per_week": 0,
        "notes": "",
        "planned_pauses": [],
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
    write_atomic(_preferences_path(), json.dumps(_normalize(data), ensure_ascii=False, indent=2) + "\n")


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


def get_active_pause(target_date: str | date | None = None) -> dict | None:
    """Sprawdź, czy na dany dzień przypada zaplanowana przerwa (np. zabieg, choroba)."""
    if target_date is None:
        target_date_str = date.today().isoformat()
    elif isinstance(target_date, str):
        target_date_str = target_date[:10]
    elif hasattr(target_date, "isoformat"):
        target_date_str = target_date.isoformat()[:10]
    else:
        target_date_str = str(target_date)[:10]

    preferences = load_preferences()
    for pause in preferences.get("planned_pauses", []):
        if not isinstance(pause, dict):
            continue
        start = str(pause.get("start_date", ""))
        end = str(pause.get("end_date", ""))
        if start and end and start <= target_date_str <= end:
            return pause
    return None


def add_planned_pause(start_date: str, end_date: str, reason: str, pause_type: str = "medical") -> dict:
    """Dodaj planowaną przerwę treningową (np. zabieg, chorobę, wyjazd)."""
    date.fromisoformat(start_date)
    date.fromisoformat(end_date)
    if start_date > end_date:
        raise ValueError("Data początkowa nie może być późniejsza niż data końcowa.")
    entry = {
        "start_date": start_date,
        "end_date": end_date,
        "reason": reason,
        "type": pause_type,
    }
    preferences = load_preferences()
    pauses = [p for p in preferences.get("planned_pauses", []) if isinstance(p, dict)]
    pauses = [p for p in pauses if not (p.get("start_date") == start_date and p.get("end_date") == end_date)]
    pauses.append(entry)
    preferences["planned_pauses"] = sorted(pauses, key=lambda x: str(x.get("start_date", "")))
    save_preferences(preferences)
    return entry


def remove_planned_pause(start_date: str, end_date: str) -> bool:
    """Usuń zaplanowaną przerwę."""
    preferences = load_preferences()
    initial_len = len(preferences.get("planned_pauses", []))
    pauses = [p for p in preferences.get("planned_pauses", [])
              if not (isinstance(p, dict) and p.get("start_date") == start_date and p.get("end_date") == end_date)]
    if len(pauses) == initial_len:
        return False
    preferences["planned_pauses"] = pauses
    save_preferences(preferences)
    return True


def list_planned_pauses() -> list[dict]:
    """Zwróć listę wszystkich zaplanowanych przerw."""
    preferences = load_preferences()
    return [p for p in preferences.get("planned_pauses", []) if isinstance(p, dict)]
