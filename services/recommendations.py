"""Magazyn dziennych rekomendacji AI.

Ścieżka pochodzi z `trainer.config.SETTINGS.local_dir`, więc zapis zawsze
trafia do katalogu `local/` obok reszty danych prywatnych.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from trainer.config import SETTINGS


logger = logging.getLogger(__name__)

RECOMMENDATIONS_PATH = SETTINGS.local_dir / "recommendations.jsonl"


def save_recommendation(*, date: str, recommendation: dict, path: Path | None = None) -> None:
    """Dopisz rekomendację dnia; błędy zapisu są przekazywane wywołującemu."""
    target = Path(path) if path is not None else RECOMMENDATIONS_PATH
    entry = {
        "date": date,
        "recommendation": recommendation,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_recommendation(*, date: str, path: Path | None = None) -> dict | None:
    """Wczytaj ostatnią rekomendację dla daty, pomijając uszkodzone linie."""
    target = Path(path) if path is not None else RECOMMENDATIONS_PATH
    if not target.is_file():
        return None

    result = None
    with open(target, encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Pomijanie uszkodzonej linii magazynu rekomendacji: %s", line[:80])
                continue
            if isinstance(entry, dict) and entry.get("date") == date:
                result = entry
    if result is None:
        return None
    recommendation = result.get("recommendation")
    return recommendation if isinstance(recommendation, dict) else None
