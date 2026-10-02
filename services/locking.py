# -*- coding: utf-8 -*-
"""Międzyprocesowe blokady operacji mutujących lokalne dane."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import Lock

from trainer.config import SETTINGS

try:
    import msvcrt
except ImportError:  # pragma: no cover - gałąź dla systemów POSIX
    msvcrt = None

try:
    import fcntl
except ImportError:  # pragma: no cover - gałąź dla Windows
    fcntl = None


class LockBusyError(RuntimeError):
    """Zasób jest właśnie używany przez inną operację."""


_PROCESS_GUARD = Lock()
_HELD_PATHS: set[Path] = set()


def _lock_path(name, directory):
    """Zwróć bezpieczną ścieżkę blokady o nadanej nazwie."""
    if not isinstance(name, str) or not name or any(char in name for char in '\\/:*?"<>|'):
        raise ValueError("Nazwa blokady musi być niepustą prostą nazwą.")
    base = Path(directory) if directory is not None else SETTINGS.local_dir
    return base / f".{name}.lock"


def _acquire(handle):
    """Załóż nieblokującą blokadę systemu operacyjnego na jeden bajt pliku."""
    handle.seek(0)
    if msvcrt is not None:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise LockBusyError("Operacja już trwa.") from exc
        return
    if fcntl is not None:
        try:
            getattr(fcntl, 'flock')(
                handle.fileno(), getattr(fcntl, 'LOCK_EX') | getattr(fcntl, 'LOCK_NB'))
        except OSError as exc:
            raise LockBusyError("Operacja już trwa.") from exc
        return
    raise RuntimeError("Ten system nie udostępnia obsługiwanej blokady pliku.")


def _release(handle):
    """Zwolnij blokadę systemową."""
    handle.seek(0)
    if msvcrt is not None:
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    elif fcntl is not None:
        getattr(fcntl, 'flock')(handle.fileno(), getattr(fcntl, 'LOCK_UN'))


@contextmanager
def acquire_lock(*, name, directory=None):
    """Zajmij nazwaną blokadę między procesami na czas bloku ``with``.

    Blokada jest nieblokująca i zwalnia się także przy wyjątku lub śmierci
    procesu dzięki mechanizmowi systemu operacyjnego. Powtórne wejście w tym
    samym procesie jest celowo odrzucane jako zajęte, aby zachowanie było takie
    samo jak przy konkurencji między procesami. Nie chroni ona przed procesem,
    który świadomie nie używa tego samego mechanizmu blokady.
    """
    path = _lock_path(name, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved = path.resolve()
    with _PROCESS_GUARD:
        if resolved in _HELD_PATHS:
            raise LockBusyError("Operacja już trwa.")
        _HELD_PATHS.add(resolved)
    handle = None
    acquired = False
    try:
        handle = path.open('a+b')
        if path.stat().st_size == 0:
            handle.write(b'0')
            handle.flush()
        _acquire(handle)
        acquired = True
        yield
    finally:
        if acquired and handle is not None:
            _release(handle)
        if handle is not None:
            handle.close()
        with _PROCESS_GUARD:
            _HELD_PATHS.discard(resolved)
