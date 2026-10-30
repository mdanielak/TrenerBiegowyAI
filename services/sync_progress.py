# -*- coding: utf-8 -*-
"""Postęp synchronizacji: bieżący etap i szacunek z czasów poprzednich przebiegów.

GarminDB nie podaje procentów, więc pasek łączy dwie rzeczy: który etap trwa
(to wiemy na pewno) i ile zwykle trwa on na tym komputerze (to szacunek).
Pliki leżą w podkatalogu magazynu zadań, więc nie mylą się z rekordami zadań.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from trainer.files import write_atomic

STAGES = (
    ("garmin", "Łączenie z kontem Garmin"),
    ("today", "Pobieranie dzisiejszych danych"),
    ("history", "Pobieranie i import aktywności i pomiarów"),
    ("extract", "Przygotowanie danych do pulpitu"),
)
_STAGE_NAMES = [name for name, _ in STAGES]
# Udział etapu w pasku (suma 100) i czas przyjmowany, zanim poznamy czasy z tego komputera.
_WEIGHTS = {"garmin": 5, "today": 15, "history": 70, "extract": 10}
_DEFAULT_SECONDS = {"garmin": 5, "today": 20, "history": 90, "extract": 10}
_FULL_HISTORY_SECONDS = 1200
# Etap, który trwa dłużej niż zwykle, zatrzymuje się przed końcem swojej części paska.
_STAGE_CAP = 0.9
_DURATIONS_FILE = "durations.json"


def _directory(jobs_directory) -> Path:
    return Path(jobs_directory) / "progress"


def _now(clock) -> datetime:
    return clock() if clock is not None else datetime.now(timezone.utc)


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict) -> None:
    write_atomic(path, json.dumps(data, ensure_ascii=False))


class SyncProgress:
    """Zapisuje etapy jednej synchronizacji; błąd zapisu nigdy nie przerywa synchronizacji."""

    def __init__(self, jobs_directory, job_id: str, *, fresh: bool = False, clock=None) -> None:
        self.directory = _directory(jobs_directory)
        self.path = self.directory / f"{job_id}.json"
        self.mode = "full" if fresh else "incremental"
        self.clock = clock
        self.current: str | None = None
        self.started: datetime | None = None
        self.durations: dict[str, float] = {}

    def stage(self, name: str) -> None:
        """Zakończ poprzedni etap i zapisz, że zaczął się etap ``name``."""
        if name not in _WEIGHTS or name == self.current:
            return
        now = _now(self.clock)
        self._close_stage(now)
        self.current, self.started = name, now
        try:
            _write_json(self.path, {"mode": self.mode, "stage": name, "stage_started_at": now.isoformat()})
        except OSError:
            pass

    def finish(self, *, succeeded: bool) -> None:
        """Usuń postęp; po sukcesie zapamiętaj czasy etapów na następny raz."""
        self._close_stage(_now(self.clock))
        try:
            if succeeded and self.durations:
                path = self.directory / _DURATIONS_FILE
                history = _read_json(path)
                history[self.mode] = {**history.get(self.mode, {}), **self.durations}
                _write_json(path, history)
            self.path.unlink(missing_ok=True)
        except OSError:
            pass

    def _close_stage(self, now: datetime) -> None:
        if self.current is not None and self.started is not None:
            self.durations[self.current] = round(max((now - self.started).total_seconds(), 0.0), 1)


def _format_elapsed(seconds: float) -> str:
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes} min {rest} s" if minutes else f"{rest} s"


def progress_view(jobs_directory, job_id: str, now: datetime | None = None) -> dict | None:
    """Zwróć stan paska dla trwającej synchronizacji albo None, gdy etap jeszcze nieznany."""
    directory = _directory(jobs_directory)
    state = _read_json(directory / f"{job_id}.json")
    stage = state.get("stage")
    if stage not in _WEIGHTS:
        return None
    try:
        started = datetime.fromisoformat(state["stage_started_at"])
    except (KeyError, TypeError, ValueError):
        return None
    mode = "full" if state.get("mode") == "full" else "incremental"
    current = now or datetime.now(timezone.utc)
    elapsed = max((current - started).total_seconds(), 0.0)

    learned = _read_json(directory / _DURATIONS_FILE).get(mode) or {}
    default = _FULL_HISTORY_SECONDS if mode == "full" and stage == "history" else _DEFAULT_SECONDS[stage]
    expected = learned.get(stage) if isinstance(learned.get(stage), (int, float)) and learned.get(stage) > 0 else default

    index = _STAGE_NAMES.index(stage)
    done = sum(_WEIGHTS[name] for name in _STAGE_NAMES[:index])
    percent = done + _WEIGHTS[stage] * min(elapsed / expected, _STAGE_CAP)
    return {
        "percent": min(int(percent), 99),
        "step": index + 1,
        "steps": len(STAGES),
        "label": STAGES[index][1],
        "elapsed": _format_elapsed(elapsed),
        "elapsed_seconds": int(elapsed),
    }
