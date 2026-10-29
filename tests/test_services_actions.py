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
                        lambda *, fresh=False, progress=None: calls.append(fresh) or expected)

    assert synchronize_data(fresh=True) is expected
    assert calls == [True]


from types import SimpleNamespace

import pytest

from services.actions import (REVIEW_BUSY_MESSAGE, REVIEW_DISABLED_MESSAGE, review_workout,
                              run_review_job)
from trainer import config


def _report(*, happened=True, review_key="review-1"):
    return SimpleNamespace(
        planned={"name": "Spokojny bieg", "spec": {"duration_min": 30, "zone_number": 2}},
        readiness={"score": 6.0},
        execution={"happened": happened, "review_key": review_key, "duration_min": 30, "avg_hr": 130},
    )


def _profile():
    return {"hr_max": 180, "hr_zone_floors": {"z1": 96, "z2": 122, "z3": 137, "z4": 151, "z5": 166},
            "hr_zones": "Z1 96-121, Z2 122-136"}


def _enable_ai(monkeypatch):
    monkeypatch.setattr(config, "AI_DATA_EXPORT_ENABLED", True)
    monkeypatch.setattr(config, "AI_API_KEY", "test-key")


def test_review_workout_saves_score_and_comment(monkeypatch):
    _enable_ai(monkeypatch)
    saved = []

    result = review_workout(
        review_key="review-1", report_provider=_report, profile_loader=_profile,
        provider_factory=lambda: SimpleNamespace(chat=lambda *args, **kwargs: SimpleNamespace(komentarz="Komentarz")),
        save=lambda **kwargs: saved.append(kwargs),
    )

    assert result["comment"] == "Komentarz"
    assert saved == [{"review_key": "review-1", "score": result["score"], "comment": "Komentarz"}]


def test_review_workout_scores_and_calls_ai_when_training_did_not_happen(monkeypatch):
    _enable_ai(monkeypatch)
    providers = []

    result = review_workout(
        review_key="review-1", report_provider=lambda: _report(happened=False), profile_loader=_profile,
        provider_factory=lambda: providers.append(object()) or SimpleNamespace(
            chat=lambda *args, **kwargs: SimpleNamespace(komentarz="Komentarz")), save=lambda **kwargs: None,
    )

    assert result["score"]["zgodnosc_z_planem"] == 0
    assert len(providers) == 1


def test_review_workout_rejects_missing_execution():
    report = SimpleNamespace(planned={}, readiness={}, execution=None)

    with pytest.raises(ValueError, match="Brak zaplanowanego treningu na dziś."):
        review_workout(review_key="review-1", report_provider=lambda: report)


def test_review_workout_rejects_stale_review_key():
    with pytest.raises(ValueError, match="Ocena dotyczy innego treningu"):
        review_workout(review_key="stary", report_provider=_report)


def test_review_workout_rejects_disabled_ai_export(monkeypatch):
    monkeypatch.setattr(config, "AI_DATA_EXPORT_ENABLED", False)
    monkeypatch.setattr(config, "AI_API_KEY", "test-key")
    saved = []

    with pytest.raises(ValueError) as exc_info:
        review_workout(review_key="review-1", report_provider=_report, profile_loader=_profile,
                       save=lambda **kwargs: saved.append(kwargs))

    assert str(exc_info.value) == REVIEW_DISABLED_MESSAGE
    assert saved == []


def test_review_workout_rejects_missing_ai_key(monkeypatch):
    monkeypatch.setattr(config, "AI_DATA_EXPORT_ENABLED", True)
    monkeypatch.setattr(config, "AI_API_KEY", "")
    saved = []

    with pytest.raises(ValueError) as exc_info:
        review_workout(review_key="review-1", report_provider=_report, profile_loader=_profile,
                       save=lambda **kwargs: saved.append(kwargs))

    assert str(exc_info.value) == REVIEW_DISABLED_MESSAGE
    assert saved == []


class _Store:
    def __init__(self):
        self.calls = []

    def mark_running(self, job_id):
        self.calls.append(("running", job_id))

    def mark_failed(self, job_id, **kwargs):
        self.calls.append(("failed", job_id, kwargs))

    def mark_succeeded(self, job_id):
        self.calls.append(("succeeded", job_id))


def test_run_review_job_marks_success(tmp_path):
    store = _Store()

    run_review_job(store=store, job_id="job-1", review_key="review-1",
                   operation=lambda **kwargs: None, lock_directory=tmp_path)

    assert store.calls == [("running", "job-1"), ("succeeded", "job-1")]


def test_run_review_job_records_value_error(tmp_path):
    store = _Store()

    run_review_job(store=store, job_id="job-1", review_key="review-1",
                   operation=lambda **kwargs: (_ for _ in ()).throw(ValueError("Błąd użytkownika")),
                   lock_directory=tmp_path)

    assert store.calls == [("running", "job-1"), ("failed", "job-1", {"message": "Błąd użytkownika"})]


def test_run_review_job_hides_technical_error(tmp_path):
    store = _Store()

    run_review_job(store=store, job_id="job-1", review_key="review-1",
                   operation=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("szczegol techniczny")),
                   lock_directory=tmp_path)

    assert store.calls == [("running", "job-1"), ("failed", "job-1", {})]


def test_run_review_job_records_busy_message(tmp_path, monkeypatch):
    from services.locking import LockBusyError

    store = _Store()
    monkeypatch.setattr("services.actions.acquire_lock", lambda **kwargs: (_ for _ in ()).throw(LockBusyError("zajęte")))

    run_review_job(store=store, job_id="job-1", review_key="review-1",
                   operation=lambda **kwargs: None, lock_directory=tmp_path)

    assert store.calls == [("running", "job-1"), ("failed", "job-1", {"message": REVIEW_BUSY_MESSAGE})]
