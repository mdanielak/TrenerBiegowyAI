"""Testy wykonawcy synchronizacji bez uruchamiania prawdziwej integracji."""
from services.actions import SYNC_BUSY_MESSAGE, run_sync_job, synchronize_data
from services.jobs import JobStore


def test_run_sync_job_marks_success_after_injected_operation(tmp_path):
    store = JobStore(tmp_path)
    job = store.submit("sync", {})
    called = []

    result = run_sync_job(store=store, job_id=job.id, operation=lambda: called.append(True),
                          lock_directory=tmp_path)

    assert called == [True]
    assert result.status == "succeeded"


def test_run_sync_job_hides_operation_exception(tmp_path):
    store = JobStore(tmp_path)
    job = store.submit("sync", {})

    result = run_sync_job(store=store, job_id=job.id,
                          operation=lambda: (_ for _ in ()).throw(RuntimeError("sekret integracji")),
                          lock_directory=tmp_path)

    assert result.status == "failed"
    assert "sekret" not in (result.error_message or "")


def test_run_sync_job_records_busy_message(tmp_path, monkeypatch):
    store = JobStore(tmp_path)
    job = store.submit("sync", {})

    def busy(**kwargs):
        from services.locking import LockBusyError
        raise LockBusyError("zajęte")

    monkeypatch.setattr("services.actions.acquire_lock", busy)
    result = run_sync_job(store=store, job_id=job.id, operation=lambda: None, lock_directory=tmp_path)
    assert result.error_message == SYNC_BUSY_MESSAGE


def test_synchronize_data_delegates_to_shared_operation(monkeypatch):
    expected = {"sync_status": "full"}
    calls = []
    monkeypatch.setattr("services.data_extract.synchronize_and_save",
                        lambda *, fresh=False: calls.append(fresh) or expected)

    assert synchronize_data(fresh=True) is expected
    assert calls == [True]
