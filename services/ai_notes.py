# -*- coding: utf-8 -*-
"""Wiadomość od biegacza dla AI, przypisana do tygodnia planu.

Np. „w sobotę wesele, długi bieg w niedzielę”. Trafia do układania planu tego
tygodnia i do rekomendacji dziennych w tym tygodniu. Plik ``local/ai-notes.jsonl``
tylko przyrasta; obowiązuje ostatni wpis dla tygodnia, a pusty tekst ją czyści.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta

from trainer.config import SETTINGS

logger = logging.getLogger(__name__)

NOTES_PATH = SETTINGS.local_dir / "ai-notes.jsonl"
WEEK_NOTE_LIMIT = 500
MESSAGE_LIMIT = 300


def clean(text, limit) -> str:
    """Jeden akapit bez nadmiarowych spacji, ucięty do limitu."""
    return " ".join(str(text or "").split())[:limit]


def _monday(day) -> date:
    day = day.date() if isinstance(day, datetime) else day
    return day - timedelta(days=day.weekday())


def set_week_note(monday, text, *, path=None) -> dict:
    """Zapisz (albo wyczyść pustym tekstem) wiadomość dla tygodnia zaczynającego się w `monday`."""
    target = path or NOTES_PATH
    record = {"week": _monday(monday).isoformat(), "text": clean(text, WEEK_NOTE_LIMIT),
              "ts": datetime.now().replace(microsecond=0).isoformat()}
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record


def note_for_week(monday, *, path=None) -> str:
    """Obowiązująca wiadomość tygodnia albo pusty tekst."""
    week = _monday(monday).isoformat()
    text = ""
    try:
        lines = (path or NOTES_PATH).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return ""
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed AI note line")
            continue
        if isinstance(record, dict) and record.get("week") == week:
            text = str(record.get("text") or "")
    return text


def note_for_day(day, *, path=None) -> str:
    """Wiadomość tygodnia, do którego należy dany dzień."""
    return note_for_week(day, path=path)
