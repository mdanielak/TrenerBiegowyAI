"""Append-only magazyn ocen wykonanych treningów."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path


logger = logging.getLogger(__name__)

REVIEWS_PATH = Path("local/workout-reviews.jsonl")


def save_review(*, review_key: str, score: dict, comment: str,
                path: Path | None = None) -> None:
    """Dopisz ocenę treningu; błędy zapisu są przekazywane wywołującemu."""
    target = path or REVIEWS_PATH
    entry = {
        "review_key": review_key,
        "score": score,
        "comment": comment,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_review(*, review_key: str, path: Path | None = None) -> dict | None:
    """Wczytaj najnowszą ocenę dla klucza, pomijając uszkodzone linie."""
    target = path or REVIEWS_PATH
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
                logger.warning("Pomijanie uszkodzonej linii magazynu ocen: %s", line[:80])
                continue
            if entry.get("review_key") == review_key:
                result = entry
    return result
