# -*- coding: utf-8 -*-
"""Action triggers and background job router."""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.actions import review_workout, run_review_job, run_sync_job
from services.jobs import JobConflictError, JobCooldownError, JobNotFoundError, JobStore
from services.locking import LockBusyError, acquire_lock
from api.formatters import REVIEW_COOLDOWN, SYNC_COOLDOWN

logger = logging.getLogger(__name__)


def get_actions_router(
    *,
    store: JobStore,
    scheduled_job_ids: set,
    sync_operation: Callable[[], None],
    review_operation: Callable[..., dict] | None,
    report_provider: Callable,
    profile_provider: Callable,
    lock_directory: Path | None,
    templates: Jinja2Templates,
    csrf_valid: Callable,
) -> APIRouter:
    router = APIRouter()

    def run_review(*, review_key: str):
        """Uruchom ocenę treningu na tym samym dostawcy raportu, co pulpit."""
        if review_operation is not None:
            return review_operation(review_key=review_key)
        return review_workout(
            review_key=review_key,
            report_provider=report_provider,
            profile_loader=profile_provider,
        )

    @router.post("/actions/sync")
    def submit_sync(request: Request, csrf_token: str = Form(default="")):
        if not csrf_valid(request, csrf_token):
            return templates.TemplateResponse(
                request=request,
                name="today.html",
                context={
                    "error_message": "Nie można potwierdzić, że żądanie pochodzi z tej strony. Odśwież stronę i spróbuj ponownie.",
                    "error_link": "/",
                    "sync_banner": {"refresh": False},
                },
                status_code=403,
                headers={"Cache-Control": "no-store"},
            )
        try:
            with acquire_lock(name="jobs", directory=lock_directory):
                job = store.submit("sync", {"fresh": False}, cooldown=SYNC_COOLDOWN)
                should_schedule = job.status == "accepted" and job.id not in scheduled_job_ids
                if should_schedule:
                    scheduled_job_ids.add(job.id)
        except LockBusyError:
            return RedirectResponse(url="/", status_code=303)
        except JobConflictError:
            return RedirectResponse(url="/", status_code=303)
        except JobCooldownError:
            return RedirectResponse(url="/", status_code=303)
        if should_schedule:
            def execute():
                try:
                    return run_sync_job(
                        store=store,
                        job_id=job.id,
                        operation=sync_operation,
                        fresh=False,
                        lock_directory=lock_directory,
                    )
                finally:
                    scheduled_job_ids.discard(job.id)

            request.app.state.job_executor.submit(execute)
        return RedirectResponse(url="/", status_code=303)

    @router.post("/actions/review")
    def submit_review(
        request: Request,
        csrf_token: str = Form(default=""),
        review_key: str = Form(default=""),
    ):
        if not csrf_valid(request, csrf_token) or not review_key:
            return templates.TemplateResponse(
                request=request,
                name="today.html",
                context={
                    "error_message": "Nie można potwierdzić, że żądanie pochodzi z tej strony. Odśwież stronę i spróbuj ponownie.",
                    "error_link": "/",
                    "sync_banner": {"refresh": False},
                    "active_nav": "today",
                },
                status_code=403,
                headers={"Cache-Control": "no-store"},
            )
        try:
            with acquire_lock(name="jobs", directory=lock_directory):
                job = store.submit("review", {"review_key": review_key}, cooldown=REVIEW_COOLDOWN)
                should_schedule = job.status == "accepted" and job.id not in scheduled_job_ids
                if should_schedule:
                    scheduled_job_ids.add(job.id)
        except (LockBusyError, JobConflictError, JobCooldownError):
            return RedirectResponse(url="/", status_code=303)
        if should_schedule:
            def execute():
                try:
                    return run_review_job(
                        store=store,
                        job_id=job.id,
                        review_key=review_key,
                        operation=run_review,
                        lock_directory=lock_directory,
                    )
                finally:
                    scheduled_job_ids.discard(job.id)

            request.app.state.job_executor.submit(execute)
        return RedirectResponse(url="/", status_code=303)

    @router.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_status(request: Request, job_id: str):
        try:
            job = store.get(job_id)
        except JobNotFoundError:
            raise HTTPException(404, "Nie znaleziono zadania.")
        labels = {
            "accepted": "Zadanie przyjęte, czeka na rozpoczęcie.",
            "running": "Trwa synchronizacja danych. Może potrwać około dwóch minut. Strona odświeży się sama.",
            "succeeded": "Gotowe. Dane są zaktualizowane.",
            "failed": "Nie udało się. Spróbuj ponownie.",
            "unknown": "Nie wiemy, czy operacja się dokończyła. Sprawdź dane, zanim spróbujesz ponownie.",
        }
        return templates.TemplateResponse(
            request=request,
            name="job.html",
            context={
                "job": job,
                "message": labels[job.status],
                "active_nav": "today",
            },
            headers={"Cache-Control": "no-store"},
        )

    return router
