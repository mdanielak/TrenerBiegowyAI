# -*- coding: utf-8 -*-
"""Action triggers and background job router."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.actions import (
    generate_daily_recommendation,
    generate_week_plan,
    push_plan_to_garmin,
    review_workout,
    run_plan_job,
    run_plan_push_job,
    run_recommendation_job,
    run_review_job,
    run_sync_job,
)
from services.jobs import JobConflictError, JobCooldownError, JobNotFoundError, JobStore
from services.locking import LockBusyError, acquire_lock
from api.formatters import (
    PLAN_COOLDOWN,
    PLAN_PUSH_COOLDOWN,
    RECOMMENDATION_COOLDOWN,
    REVIEW_COOLDOWN,
    SYNC_COOLDOWN,
)
from api.routers.plans import plan_page_context

logger = logging.getLogger(__name__)

CSRF_ERROR_MESSAGE = ("Nie można potwierdzić, że żądanie pochodzi z tej strony. "
                      "Odśwież stronę i spróbuj ponownie.")


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
    plan_operation: Callable[..., dict] | None = None,
    plan_push_operation: Callable[..., dict] | None = None,
    recommendation_operation: Callable[..., dict] | None = None,
    ai_settings_provider: Callable[[], dict] | None = None,
    now_provider: Callable[[], datetime] | None = None,
) -> APIRouter:
    router = APIRouter()

    def run_plan(*, week_start: str):
        """Ułóż plan tygodnia na tym samym dostawcy danych, co pulpit."""
        if plan_operation is not None:
            return plan_operation(week_start=week_start)
        return generate_week_plan(week_start=week_start or None)

    def run_plan_push(*, week_start: str):
        """Wyślij zapisany plan na zegarek."""
        if plan_push_operation is not None:
            return plan_push_operation(week_start=week_start or None)
        return push_plan_to_garmin(week_start=week_start or None)

    def run_recommendation():
        """Policz rekomendację AI na dziś."""
        if recommendation_operation is not None:
            return recommendation_operation()
        return generate_daily_recommendation()

    def today() -> datetime:
        """Aktualna data w strefie lokalnej."""
        current = now_provider() if now_provider is not None else datetime.now()
        return current.astimezone() if current.tzinfo is not None else current

    def ai_ready() -> bool:
        """Czy dane mogą trafić do AI: klucz i jawna zgoda muszą być obecne."""
        if ai_settings_provider is None:
            return False
        try:
            settings = ai_settings_provider() or {}
        except (OSError, UnicodeError):
            return False
        return bool(settings.get("key_present") and settings.get("export_enabled"))

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

    @router.post("/actions/plan")
    def submit_plan(
        request: Request,
        csrf_token: str = Form(default=""),
        week_start: str = Form(default=""),
    ):
        if not csrf_valid(request, csrf_token):
            return templates.TemplateResponse(
                request=request,
                name="plan.html",
                context=plan_page_context(
                    today=today(),
                    error_message=CSRF_ERROR_MESSAGE,
                    now=datetime.now(),
                ),
                status_code=403,
                headers={"Cache-Control": "no-store"},
            )
        if not ai_ready():
            return templates.TemplateResponse(
                request=request,
                name="plan.html",
                context=plan_page_context(
                    today=today(),
                    error_message="Generowanie planu wymaga włączenia wysyłania danych do AI.",
                    error_command="python -m trainer setup",
                    now=datetime.now(),
                ),
                status_code=400,
                headers={"Cache-Control": "no-store"},
            )
        try:
            with acquire_lock(name="jobs", directory=lock_directory):
                job = store.submit("plan", {"week_start": week_start}, cooldown=PLAN_COOLDOWN)
                should_schedule = job.status == "accepted" and job.id not in scheduled_job_ids
                if should_schedule:
                    scheduled_job_ids.add(job.id)
        except (LockBusyError, JobConflictError, JobCooldownError):
            return RedirectResponse(url="/plan", status_code=303)
        if should_schedule:
            def execute():
                try:
                    return run_plan_job(
                        store=store,
                        job_id=job.id,
                        operation=run_plan,
                        week_start=week_start,
                        lock_directory=lock_directory,
                    )
                finally:
                    scheduled_job_ids.discard(job.id)

            request.app.state.job_executor.submit(execute)
        return RedirectResponse(url="/plan", status_code=303)

    @router.post("/actions/plan/push")
    def submit_plan_push(
        request: Request,
        csrf_token: str = Form(default=""),
        week_start: str = Form(default=""),
    ):
        if not csrf_valid(request, csrf_token):
            return templates.TemplateResponse(
                request=request,
                name="plan.html",
                context=plan_page_context(
                    today=today(),
                    error_message=CSRF_ERROR_MESSAGE,
                    now=datetime.now(),
                ),
                status_code=403,
                headers={"Cache-Control": "no-store"},
            )
        try:
            with acquire_lock(name="jobs", directory=lock_directory):
                job = store.submit("plan_push", {"week_start": week_start}, cooldown=PLAN_PUSH_COOLDOWN)
                should_schedule = job.status == "accepted" and job.id not in scheduled_job_ids
                if should_schedule:
                    scheduled_job_ids.add(job.id)
        except (LockBusyError, JobConflictError, JobCooldownError):
            return RedirectResponse(url="/plan", status_code=303)
        if should_schedule:
            def execute():
                try:
                    return run_plan_push_job(
                        store=store,
                        job_id=job.id,
                        operation=run_plan_push,
                        week_start=week_start,
                        lock_directory=lock_directory,
                    )
                finally:
                    scheduled_job_ids.discard(job.id)

            request.app.state.job_executor.submit(execute)
        return RedirectResponse(url="/plan", status_code=303)

    @router.post("/actions/recommendation")
    def submit_recommendation(
        request: Request,
        csrf_token: str = Form(default=""),
    ):
        if not csrf_valid(request, csrf_token):
            return templates.TemplateResponse(
                request=request,
                name="today.html",
                context={
                    "error_message": CSRF_ERROR_MESSAGE,
                    "error_link": "/",
                    "sync_banner": {"refresh": False},
                    "active_nav": "today",
                },
                status_code=403,
                headers={"Cache-Control": "no-store"},
            )
        try:
            with acquire_lock(name="jobs", directory=lock_directory):
                job = store.submit(
                    "recommendation", {"date": today().date().isoformat()},
                    cooldown=RECOMMENDATION_COOLDOWN,
                )
                should_schedule = job.status == "accepted" and job.id not in scheduled_job_ids
                if should_schedule:
                    scheduled_job_ids.add(job.id)
        except (LockBusyError, JobConflictError, JobCooldownError):
            return RedirectResponse(url="/plan", status_code=303)
        if should_schedule:
            def execute():
                try:
                    return run_recommendation_job(
                        store=store,
                        job_id=job.id,
                        operation=run_recommendation,
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
