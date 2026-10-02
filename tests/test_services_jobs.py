"""Testy trwałego rejestru zadań wykonywanych w tle."""
from datetime import datetime, timedelta, timezone

import pytest

from services.jobs import JobConflictError, JobCooldownError, JobNotFoundError, JobStore


def at(hour: int) -> datetime:
    return datetime(2026, 10, 2, hour, tzinfo=timezone.utc)


def test_full_lifecycle_and_restart_persistence(tmp_path):
    store = JobStore(tmp_path / "jobs")
    accepted = store.submit("sync", {"range": "today"}, now=at(8))
    running = store.mark_running(accepted.id, now=at(9))
    succeeded = store.mark_succeeded(accepted.id, now=at(10))
    restored = JobStore(tmp_path / "jobs").get(accepted.id)
    assert [accepted.status, running.status, succeeded.status] == ["accepted", "running", "succeeded"]
    assert restored == succeeded


def test_failed_job_has_only_generic_error_message(tmp_path):
    store = JobStore(tmp_path)
    job = store.submit("sync", {}, now=at(8))
    failed = store.mark_failed(store.mark_running(job.id, now=at(9)).id, now=at(10))
    assert failed.error_message == "Operacja nie powiodła się."


def test_failed_job_rejects_message_outside_safe_set(tmp_path):
    store = JobStore(tmp_path)
    job = store.mark_running(store.submit("sync", {}, now=at(8)).id, now=at(9))
    failed = store.mark_failed(job.id, message="token=sekret", now=at(10))
    assert failed.error_message == "Operacja nie powiodła się."
    assert "sekret" not in (tmp_path / f"{job.id}.json").read_text(encoding="utf-8")


def test_get_unknown_identifier_is_clear(tmp_path):
    with pytest.raises(JobNotFoundError, match="Nie znaleziono"):
        JobStore(tmp_path).get("a" * 32)


def test_record_is_on_disk_before_caller_can_start_work(tmp_path):
    store = JobStore(tmp_path)
    job = store.submit("sync", {"source": "button"}, now=at(8))
    assert (tmp_path / f"{job.id}.json").exists()
    assert store.get(job.id).status == "accepted"


def test_identical_active_submission_reuses_job_and_different_arguments_conflict(tmp_path):
    store = JobStore(tmp_path)
    job = store.submit("sync", {"day": "today"}, now=at(8))
    assert store.submit("sync", {"day": "today"}, now=at(9)).id == job.id
    assert len(store.list_jobs().jobs) == 1
    with pytest.raises(JobConflictError):
        store.submit("sync", {"day": "yesterday"}, now=at(9))


def test_running_job_after_restart_becomes_unknown_and_is_not_retried(tmp_path):
    first = JobStore(tmp_path)
    job = first.mark_running(first.submit("sync", {}, now=at(8)).id, now=at(9))
    second = JobStore(tmp_path)
    changed = second.mark_abandoned_running_as_unknown(now=at(10))
    assert [item.id for item in changed] == [job.id]
    assert second.get(job.id).status == "unknown"
    assert second.submit("sync", {}, now=at(11)).id != job.id


def test_cooldown_uses_injected_time_without_sleep(tmp_path):
    store = JobStore(tmp_path)
    job = store.mark_running(store.submit("sync", {}, now=at(8)).id, now=at(8))
    store.mark_succeeded(job.id, now=at(9))
    with pytest.raises(JobCooldownError):
        store.submit("sync", {}, cooldown=timedelta(hours=2), now=at(10))
    assert store.submit("sync", {}, cooldown=timedelta(hours=2), now=at(11)).status == "accepted"


def test_corrupt_json_is_reported_without_breaking_listing(tmp_path):
    store = JobStore(tmp_path)
    store.submit("sync", {}, now=at(8))
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    result = store.list_jobs()
    assert len(result.jobs) == 1
    assert result.corrupted_files == [broken]


def test_operation_path_separator_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="niedozwolone"):
        JobStore(tmp_path).submit("../sync", {}, now=at(8))


def test_persisted_record_excludes_sensitive_argument_values(tmp_path):
    token = "token-super-secret-123"
    heart_rate = 171
    job = JobStore(tmp_path).submit("sync", {"token": token, "heart_rate": heart_rate}, now=at(8))
    saved = (tmp_path / f"{job.id}.json").read_text(encoding="utf-8")
    assert token not in saved
    assert str(heart_rate) not in saved


def test_write_failure_is_propagated(tmp_path, monkeypatch):
    store = JobStore(tmp_path)

    def fail_replace(source, destination):
        raise OSError("disk full")

    monkeypatch.setattr("services.jobs.os.replace", fail_replace)
    with pytest.raises(OSError, match="disk full"):
        store.submit("sync", {}, now=at(8))
