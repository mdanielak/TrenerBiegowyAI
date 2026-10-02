"""Wykonawcy mutujących operacji uruchamianych jako zadania w tle."""
from __future__ import annotations

from services.jobs import JobStore
from services.locking import LockBusyError, acquire_lock


SYNC_BUSY_MESSAGE = "Operacja już trwa. Spróbuj ponownie za chwilę."


def synchronize_data(*, fresh=False):
    """Wykonaj synchronizację i zapisz nowy lokalny snapshot.

    Argument ``fresh`` rozróżnia pełną synchronizację od zwykłej bez
    wywoływania komendy CLI, która ma własną blokadę.
    """
    from services.data_extract import synchronize_and_save

    return synchronize_and_save(fresh=fresh)


def run_sync_job(*, store: JobStore, job_id: str, operation=synchronize_data,
                 fresh=False, lock_directory=None):
    """Oznacz zadanie, wykonaj synchronizację pod blokadą i zapisz rezultat."""
    store.mark_running(job_id)
    try:
        with acquire_lock(name="sync", directory=lock_directory):
            if operation is synchronize_data:
                operation(fresh=fresh)
            else:
                operation()
    except LockBusyError:
        return store.mark_failed(job_id, message=SYNC_BUSY_MESSAGE)
    except Exception:
        return store.mark_failed(job_id)
    return store.mark_succeeded(job_id)
