# -*- coding: utf-8 -*-
"""Sprawdzanie nowej wersji: często dość, by wydanie dotarło w kilka godzin, rzadko dość dla GitHuba."""
import json
from datetime import datetime, timedelta, timezone

from services.update_check import CHECK_EVERY, available_update, watch_for_updates

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def _cache(path, latest, ago):
    path.write_text(json.dumps({"checked_at": (NOW - ago).isoformat(), "latest": latest}), encoding="utf-8")


def _offline():
    raise OSError("brak sieci")


def test_checks_at_most_once_an_hour():
    assert CHECK_EVERY == timedelta(hours=1)


def test_a_fresh_cache_answers_without_the_network(tmp_path):
    path = tmp_path / "update-check.json"
    _cache(path, "v0.9.0", ago=timedelta(minutes=30))
    assert available_update("0.8.4", now=NOW, fetch=lambda: "v9.9.9", path=path) == "0.9.0"


def test_a_cache_older_than_an_hour_asks_github_again(tmp_path):
    # Tak było u autora: rano zapamiętane 0.8.2, a wydanie 0.8.4 pojawiło się kilka godzin później.
    path = tmp_path / "update-check.json"
    _cache(path, "v0.8.2", ago=timedelta(hours=2))
    assert available_update("0.8.2", now=NOW, fetch=lambda: "v0.8.4", path=path) == "0.8.4"
    assert json.loads(path.read_text(encoding="utf-8"))["latest"] == "v0.8.4"


def test_no_internet_keeps_the_last_known_answer(tmp_path):
    path = tmp_path / "update-check.json"
    _cache(path, "v0.9.0", ago=timedelta(hours=5))
    assert available_update("0.8.4", now=NOW, fetch=_offline, path=path) == "0.9.0"
    assert available_update("0.8.4", now=NOW, fetch=_offline, path=tmp_path / "brak.json") is None


def test_the_installed_version_newer_than_the_cache_needs_nothing(tmp_path):
    path = tmp_path / "update-check.json"
    _cache(path, "v0.8.2", ago=timedelta(minutes=5))
    assert available_update("0.8.4", now=NOW, fetch=lambda: "v0.8.4", path=path) is None


class _Stop:
    """Udawane zdarzenie zatrzymania: po zadanej liczbie przerw aplikacja się zamyka."""

    def __init__(self, waits):
        self.waits, self.timeouts = waits, []

    def wait(self, timeout):
        self.timeouts.append(timeout)
        self.waits -= 1
        return self.waits < 0


def test_a_running_app_checks_again_every_hour_until_it_closes():
    shown, answers = [], iter([None, None, "0.9.0"])
    stop = _Stop(waits=2)
    watch_for_updates("0.8.4", shown.append, stop, check=lambda current: next(answers))
    assert shown == [None, None, "0.9.0"]
    assert stop.timeouts == [3600, 3600, 3600]


def test_the_watcher_survives_an_unexpected_error():
    shown, calls = [], []

    def flaky(current):
        calls.append(current)
        if len(calls) == 1:
            raise RuntimeError("nieoczekiwany błąd")
        return "0.9.0"

    watch_for_updates("0.8.4", shown.append, _Stop(waits=1), check=flaky)
    assert shown == ["0.9.0"] and len(calls) == 2

