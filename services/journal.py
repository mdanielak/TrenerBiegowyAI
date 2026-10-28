# -*- coding: utf-8 -*-
"""Dziennik samopoczucia: samopoczucie, RPE, ból i notatka dzień po dniu.

Zapis jest append-only w ``local/journal.jsonl``, tak jak rejestr treningów:
plik nigdy nie jest przepisywany, a obowiązuje ostatni wpis z danego dnia.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta

from trainer.config import SETTINGS

logger = logging.getLogger(__name__)

JOURNAL_PATH = SETTINGS.local_dir / "journal.jsonl"
FEELINGS = {"great": "świetnie", "good": "dobrze", "poor": "słabo"}
PAIN_AREAS = {"calf": "łydka", "foot": "stopa", "knee": "kolano", "hip": "biodro",
              "back": "plecy", "other": "inne"}
NOTE_LIMIT = 300
PAIN_NOTE_LIMIT = 120
AI_NOTE_LIMIT = 120
# Wpis wstecz ma sens dla wczoraj i kilku dni; dalej to już nie jest dziennik bieżący.
BACKDATE_DAYS = 7


def _clean(text, limit) -> str:
    return " ".join(str(text or "").split())[:limit]


def validate_entry(*, day, feeling, rpe, pain_areas, pain_note, note, today: date) -> dict:
    """Sprawdź pola formularza; błąd to ValueError z komunikatem dla użytkownika."""
    try:
        entry_day = day if isinstance(day, date) else date.fromisoformat(str(day))
    except ValueError:
        raise ValueError("Podaj datę wpisu w formacie RRRR-MM-DD.") from None
    if entry_day > today:
        raise ValueError("Wpis nie może dotyczyć przyszłego dnia.")
    if entry_day < today - timedelta(days=BACKDATE_DAYS):
        raise ValueError(f"Wpis można dodać najwyżej {BACKDATE_DAYS} dni wstecz.")
    if feeling not in FEELINGS:
        raise ValueError("Wybierz, jak się czujesz.")
    rpe_value = None
    if rpe not in (None, ""):
        try:
            rpe_value = int(rpe)
        except (TypeError, ValueError):
            raise ValueError("RPE to liczba od 1 do 10.") from None
        if not 1 <= rpe_value <= 10:
            raise ValueError("RPE to liczba od 1 do 10.")
    areas = [area for area in dict.fromkeys(pain_areas or []) if area in PAIN_AREAS]
    if len(areas) != len(set(pain_areas or [])):
        raise ValueError("Nieznane miejsce bólu.")
    return {
        "date": entry_day.isoformat(),
        "feeling": feeling,
        "rpe": rpe_value,
        "pain": areas,
        "pain_note": _clean(pain_note, PAIN_NOTE_LIMIT) if areas else "",
        "note": _clean(note, NOTE_LIMIT),
    }


def add_entry(entry: dict, *, path=None) -> dict:
    """Dopisz zwalidowany wpis na końcu pliku i potwierdź zapis na dysku."""
    target = path or JOURNAL_PATH
    record = dict(entry, ts=datetime.now().replace(microsecond=0).isoformat())
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record


def entries_by_day(*, path=None) -> dict[str, dict]:
    """Obowiązujący wpis dla każdego dnia: późniejszy wpis zastępuje wcześniejszy."""
    target = path or JOURNAL_PATH
    result = {}
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return result
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed journal line")
            continue
        if isinstance(record, dict) and isinstance(record.get("date"), str):
            result[record["date"]] = record
    return result


def recent_entries(*, today: date, days: int = 14, path=None) -> list[dict]:
    """Wpisy z ostatnich `days` dni, najnowszy pierwszy."""
    since = (today - timedelta(days=days - 1)).isoformat()
    by_day = entries_by_day(path=path)
    return [by_day[day] for day in sorted(by_day, reverse=True) if since <= day <= today.isoformat()]


def summary_for_ai(*, today: date, days: int = 7, path=None) -> dict | None:
    """Zwięzłe podsumowanie dla AI: tylko pola strukturalne i krótkie notatki."""
    recent = recent_entries(today=today, days=days, path=path)
    if not recent:
        return None
    rpe = [entry["rpe"] for entry in recent if isinstance(entry.get("rpe"), int)]
    pain_days = [entry for entry in recent if entry.get("pain")]
    return {
        "days_with_entries": len(recent),
        "feelings": {label: sum(1 for e in recent if e.get("feeling") == key) for key, label in FEELINGS.items()},
        "average_rpe": round(sum(rpe) / len(rpe), 1) if rpe else None,
        "pain_days": [{
            "date": entry["date"],
            "areas": [PAIN_AREAS.get(area, area) for area in entry["pain"]],
            "note": _clean(entry.get("pain_note"), AI_NOTE_LIMIT),
        } for entry in pain_days],
        "notes": [{"date": entry["date"], "note": _clean(entry.get("note"), AI_NOTE_LIMIT)}
                  for entry in recent if entry.get("note")],
    }
