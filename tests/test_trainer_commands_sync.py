"""Testy blokady dla komendy synchronizacji."""
from contextlib import contextmanager

import pytest

from services.locking import acquire_lock
from trainer.commands import sync as sync_command


def _lock_in(directory):
    """Zwróć blokadę produkcyjną skierowaną do katalogu testowego."""
    @contextmanager
    def lock(*, name):
        with acquire_lock(name=name, directory=directory):
            yield
    return lock


def test_busy_lock_returns_clean_message_and_nonzero_code(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sync_command, "acquire_lock", _lock_in(tmp_path))
    monkeypatch.setattr(sync_command, "setup_logging", lambda: None)
    with acquire_lock(name="sync", directory=tmp_path):
        assert sync_command.main() == 1
    captured = capsys.readouterr()
    assert captured.err == "Operacja już trwa. Spróbuj ponownie za chwilę.\n"
    assert "Traceback" not in captured.err


def test_success_runs_operation_once_and_releases_lock(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sync_command, "acquire_lock", _lock_in(tmp_path))
    monkeypatch.setattr(sync_command, "setup_logging", lambda: None)
    monkeypatch.setattr(sync_command, "synchronize_and_save",
                        lambda *, fresh=False: calls.append(("sync", fresh)) or
                        {"activities": [], "daily_health": []})
    monkeypatch.setattr(sync_command, "print_summary", lambda data: calls.append("summary"))

    assert sync_command.main() is None
    assert calls == [("sync", False), "summary"]
    with acquire_lock(name="sync", directory=tmp_path):
        pass


def test_operation_exception_releases_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_command, "acquire_lock", _lock_in(tmp_path))
    monkeypatch.setattr(sync_command, "setup_logging", lambda: None)
    monkeypatch.setattr(sync_command, "synchronize_and_save",
                        lambda *, fresh=False: (_ for _ in ()).throw(RuntimeError("awaria atrap")))

    with pytest.raises(RuntimeError, match="awaria atrap"):
        sync_command.main()
    with acquire_lock(name="sync", directory=tmp_path):
        pass
