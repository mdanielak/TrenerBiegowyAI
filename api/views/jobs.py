# -*- coding: utf-8 -*-
"""Paski stanu zadań w tle i odstępy między kolejnymi uruchomieniami."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.jobs import JobStore

SYNC_COOLDOWN = timedelta(seconds=60)
REVIEW_COOLDOWN = timedelta(seconds=30)
PLAN_COOLDOWN = timedelta(minutes=5)
PLAN_PUSH_COOLDOWN = timedelta(minutes=1)
RECOMMENDATION_COOLDOWN = timedelta(minutes=10)


def _job_timestamp(value: str | None) -> datetime | None:
    """Odczytaj czas rekordu zadania jako świadomy czas UTC."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone(timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sync_banner(store: JobStore, now: datetime) -> dict[str, str | bool | None]:
    """Wylicz stan paska wyłącznie z najnowszego zadania synchronizacji."""
    jobs = [job for job in store.list_jobs().jobs if job.operation == "sync"]
    if not jobs:
        return {"message": None, "details_url": None, "refresh": False, "disabled": False}
    job = jobs[0]
    if job.status in {"accepted", "running"}:
        return {"message": "Trwa synchronizacja danych. Może potrwać około dwóch minut. Strona odświeży się sama.",
                "details_url": None, "refresh": True, "disabled": True}
    completed_at = _job_timestamp(job.finished_at or job.created_at)
    current = now.astimezone(timezone.utc)
    recent = completed_at is not None and current - completed_at <= timedelta(minutes=10)
    if job.status == "failed" and recent:
        return {"message": "Ostatnia synchronizacja się nie udała.",
                "details_url": f"/jobs/{job.id}", "refresh": False, "disabled": False}
    if job.status == "unknown" and recent:
        return {"message": "Nie wiemy, czy ostatnia synchronizacja się dokończyła. Sprawdź dane, zanim spróbujesz ponownie.",
                "details_url": f"/jobs/{job.id}", "refresh": False, "disabled": False}
    if job.status == "succeeded" and completed_at is not None and current < completed_at + SYNC_COOLDOWN:
        return {"message": "Dane zsynchronizowano niedawno. Odczekaj chwilę przed kolejną próbą.",
                "details_url": None, "refresh": False, "disabled": False}
    return {"message": None, "details_url": None, "refresh": False, "disabled": False}


def _plan_banner(store: JobStore, now: datetime, operation: str, messages: dict) -> dict:
    """Wylicz stan paska planu wyłącznie z najnowszego zadania danej operacji."""
    jobs = [job for job in store.list_jobs().jobs if job.operation == operation]
    if not jobs:
        return {"message": None, "details_url": None, "refresh": False, "disabled": False}
    job = jobs[0]
    if job.status in {"accepted", "running"}:
        return {"message": messages.get("running"), "details_url": None, "refresh": True, "disabled": True}
    completed_at = _job_timestamp(job.finished_at or job.created_at)
    current = now.astimezone(timezone.utc)
    recent = completed_at is not None and current - completed_at <= timedelta(minutes=10)
    if job.status == "failed" and recent:
        return {"message": messages.get("failed"), "details_url": f"/jobs/{job.id}",
                "refresh": False, "disabled": False}
    if job.status == "succeeded" and recent:
        return {"message": messages.get("succeeded"), "details_url": None,
                "refresh": False, "disabled": False}
    return {"message": None, "details_url": None, "refresh": False, "disabled": False}
