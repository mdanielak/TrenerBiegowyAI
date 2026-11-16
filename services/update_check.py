# -*- coding: utf-8 -*-
"""Sprawdzenie, czy na GitHubie jest nowsze wydanie aplikacji.

Najwyżej jedno zapytanie na godzinę o numer najnowszego wydania (to samo źródło, z którego korzysta
update.bat): przy starcie aplikacji i potem co godzinę, póki działa. Nie wysyła żadnych danych
biegacza; wynik leży w local/update-check.json.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trainer.config import SETTINGS
from trainer.files import write_atomic

RELEASE_URL = "https://api.github.com/repos/mdanielak/TrenerBiegowyAI/releases/latest"
# GitHub bez logowania pozwala na 60 zapytań na godzinę z jednego adresu; jedno to zapas z nawiązką.
CHECK_EVERY = timedelta(hours=1)
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def _cache_path() -> Path:
    return SETTINGS.local_dir / "update-check.json"


def _parse(version) -> tuple[int, int, int] | None:
    match = _VERSION.match(str(version or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def update_command(platform: str | None = None) -> str:
    """Plik, którym osoba aktualizuje aplikację na swoim systemie."""
    return "update.bat" if (platform or sys.platform).startswith("win") else "./update.sh"


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
    """Zwróć numer nowszego wydania albo None; sieć najwyżej raz na godzinę, błędy sieci są ciche."""
    path = path or _cache_path()
    now = now or datetime.now(timezone.utc)
    known = None
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        known = cached.get("latest")
        if now - datetime.fromisoformat(cached["checked_at"]) < CHECK_EVERY:
            return newer_version(current, known)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    try:
        latest = fetch()
    except Exception:  # noqa: BLE001 - brak sieci albo limit GitHuba nie może psuć startu aplikacji
        # Chwilowy brak sieci nie chowa informacji o wersji, którą już znamy.
        return newer_version(current, known)
    try:
        write_atomic(path, json.dumps({"checked_at": now.isoformat(), "latest": latest}) + "\n")
    except OSError:
        pass
    return newer_version(current, latest)


def watch_for_updates(current: str, publish, stop, *, check=available_update) -> None:
    """Sprawdzaj przy starcie i co CHECK_EVERY, aż `stop` (threading.Event) da znać o zamknięciu."""
    while True:
        try:
            publish(check(current))
        except Exception:  # noqa: BLE001 - wątek w tle nie może zginąć po cichu na zawsze
            pass
        if stop.wait(CHECK_EVERY.total_seconds()):
            return
