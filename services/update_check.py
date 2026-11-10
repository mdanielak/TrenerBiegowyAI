# -*- coding: utf-8 -*-
"""Sprawdzenie, czy na GitHubie jest nowsze wydanie aplikacji.

Jedno zapytanie na dobę o numer najnowszego wydania (to samo źródło, z którego korzysta
update.bat). Nie wysyła żadnych danych biegacza; wynik leży w local/update-check.json.
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trainer.config import SETTINGS
from trainer.files import write_atomic

RELEASE_URL = "https://api.github.com/repos/mdanielak/TrenerBiegowyAI/releases/latest"
CHECK_EVERY = timedelta(hours=24)
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def _cache_path() -> Path:
    return SETTINGS.local_dir / "update-check.json"


def _parse(version) -> tuple[int, int, int] | None:
    match = _VERSION.match(str(version or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def newer_version(current: str, latest: str) -> str | None:
    """Numer nowszego wydania (bez „v”) albo None, gdy aktualizacja nie jest potrzebna."""
    now, new = _parse(current), _parse(latest)
    if now is None or new is None or new <= now:
        return None
    return ".".join(str(part) for part in new)


def _fetch_latest() -> str:
    request = urllib.request.Request(RELEASE_URL, headers={"Accept": "application/vnd.github+json",
                                                           "User-Agent": "TrenerBiegowyAI-update-check"})
    with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - stały adres https
        return str(json.load(response).get("tag_name") or "")


def available_update(current: str, *, now: datetime | None = None, fetch=_fetch_latest, path: Path | None = None):
    """Zwróć numer nowszego wydania albo None; sieć najwyżej raz na dobę, błędy sieci są ciche."""
    path = path or _cache_path()
    now = now or datetime.now(timezone.utc)
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        checked = datetime.fromisoformat(cached["checked_at"])
        if now - checked < CHECK_EVERY:
            return newer_version(current, cached.get("latest"))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        latest = fetch()
    except Exception:  # noqa: BLE001 - brak sieci albo limit GitHuba nie może psuć startu aplikacji
        return None
    try:
        write_atomic(path, json.dumps({"checked_at": now.isoformat(), "latest": latest}) + "\n")
    except OSError:
        pass
    return newer_version(current, latest)
