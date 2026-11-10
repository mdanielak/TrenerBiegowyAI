# -*- coding: utf-8 -*-
"""Action triggers and background job router."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from functools import partial
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.actions import (
    edit_plan_workout,
    generate_daily_recommendation,
    generate_week_plan,
    push_plan_to_garmin,
    remove_plan_workout,
    review_workout,
    run_plan_job,
    run_plan_push_job,
    run_recommendation_job,
    run_review_job,
    run_sync_job,
)
from services.jobs import WEEK_NOTE_FULL_MESSAGE, JobConflictError, JobCooldownError, JobNotFoundError, JobStore
from services.locking import LockBusyError, acquire_lock
from services.sync_progress import progress_view
from api.views.jobs import (
    PLAN_COOLDOWN,
    PLAN_PUSH_COOLDOWN,
    REVIEW_COOLDOWN,
    SYNC_COOLDOWN,
)
from api.routers.plans import plan_page_context
from services import plan_conflicts
from services.ai_notes import MESSAGE_LIMIT, append_week_note, clean, set_week_note
from services.plan_files import week_bounds

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
    plan_provider: Callable[[str], dict | None] | None = None,
    registry_provider: Callable[[], list] | None = None,
) -> APIRouter:
    router = APIRouter()

    def run_plan(*, week_start: str, on_conflict=None):
        """Ułóż plan tygodnia na tym samym dostawcy danych, co pulpit."""
        decision = {"on_conflict": on_conflict} if on_conflict else {}
        if plan_operation is not None:
            return plan_operation(week_start=week_start, **decision)
        return generate_week_plan(week_start=week_start or None, **decision)

    def run_plan_push(*, week_start: str, on_conflict=None):
        """Wyślij zapisany plan na zegarek."""
        decision = {"on_conflict": on_conflict} if on_conflict else {}
        if plan_push_operation is not None:
            return plan_push_operation(week_start=week_start or None, **decision)
        return push_plan_to_garmin(week_start=week_start or None, **decision)

    def week_monday(week_start: str) -> datetime:
        try:
            anchor = datetime.fromisoformat(week_start[:10]) if week_start else today()
        except ValueError:
            anchor = today()
        return week_bounds(anchor.replace(tzinfo=None))[0]

    def stored_plan(week_start: str):
        if plan_provider is None:
            return None
        try:
            return plan_provider(week_monday(week_start).date().isoformat())
        except (OSError, ValueError):
            return None

    def has_conflict(kind: str, week_start: str) -> bool:
        """Czy akcja nadpisałaby istniejący plan albo treningi na zegarku."""
        plan = stored_plan(week_start)
        if kind == "plan":
            return plan is not None
        if plan is None or registry_provider is None:
            return False
        try:
            entries = registry_provider()
        except OSError:
            entries = []
        return bool(plan_conflicts.garmin_conflict_days(plan, entries))

    def plan_url(week_start: str, confirm: str | None = None) -> str:
        params = [f"week={week_monday(week_start).date().isoformat()}"]
        if confirm:
            params.append(f"confirm={confirm}")
        return "/plan?" + "&".join(params)

    def decide(kind: str, week_start: str, on_conflict: str):
        """Zwróć (decyzja, przekierowanie); przekierowanie oznacza, że zadania nie zakładamy."""
        decision = (on_conflict or "").strip()
        if decision == "cancel":
            return None, RedirectResponse(url=plan_url(week_start), status_code=303)
        if decision and decision not in plan_conflicts.ON_CONFLICT:
            return None, RedirectResponse(url=plan_url(week_start), status_code=303)
        if not decision and has_conflict(kind, week_start):
            return None, RedirectResponse(url=plan_url(week_start, confirm=kind), status_code=303)
        return decision or None, None

    def run_recommendation(message=None, scope=None):
        """Policz rekomendację AI na dziś; jednorazowa wiadomość biegacza jest opcjonalna."""
        extra = {"message": message} if message else {}
        if scope:
            extra["scope"] = scope
        if recommendation_operation is not None:
            return recommendation_operation(**extra)
        return generate_daily_recommendation(**extra)

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

    def start_job(request: Request, operation: str, arguments: dict, runner, *, cooldown=None, prepare=None):
        """Załóż zadanie i puść je w tle; None, gdy takie już trwa albo trzeba jeszcze poczekać.

        `runner(job_id)` wykonuje pracę; `prepare(job)` działa przed startem nowego zadania
        i zwracając False odwołuje jego uruchomienie.
        """
        try:
            with acquire_lock(name="jobs", directory=lock_directory):
                job = store.submit(operation, arguments, cooldown=cooldown)
                fresh = job.status == "accepted" and job.id not in scheduled_job_ids
                if fresh:
                    scheduled_job_ids.add(job.id)
        except (LockBusyError, JobConflictError, JobCooldownError):
            return None
        if fresh and prepare is not None and prepare(job) is False:
            scheduled_job_ids.discard(job.id)
            return job
        if fresh:
            def execute():
                try:
                    return runner(job.id)
                finally:
                    scheduled_job_ids.discard(job.id)

            request.app.state.job_executor.submit(execute)
        return job

    def today_error(request: Request):
        """Strona główna z informacją, że żądanie nie przyszło z tej aplikacji."""
        return templates.TemplateResponse(
            request=request,
            name="today.html",
            context={"error_message": CSRF_ERROR_MESSAGE, "error_link": "/",
                     "sync_banner": {"refresh": False}, "active_nav": "today"},
            status_code=403,
            headers={"Cache-Control": "no-store"},
        )

    def plan_error(request: Request, message: str = CSRF_ERROR_MESSAGE, *, status_code=403, **extra):
        """Strona planu z komunikatem błędu."""
        return templates.TemplateResponse(
            request=request,
            name="plan.html",
            context=plan_page_context(today=today(), error_message=message, now=datetime.now(), **extra),
            status_code=status_code,
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/actions/sync")
    def submit_sync(request: Request, csrf_token: str = Form(default=""), fresh: str = Form(default="")):
        if not csrf_valid(request, csrf_token):
            return today_error(request)
        full = fresh == "1"
        job = start_job(
            request, "sync", {"fresh": full}, cooldown=SYNC_COOLDOWN,
            runner=lambda job_id: run_sync_job(store=store, job_id=job_id, operation=sync_operation,
                                               fresh=full, lock_directory=lock_directory))
        # Pełne pobranie trwa długo: pokaż stronę postępu zamiast pulpitu bez danych.
        return RedirectResponse(url=f"/jobs/{job.id}" if job and full else "/", status_code=303)

    @router.post("/actions/review")
    def submit_review(
        request: Request,
        csrf_token: str = Form(default=""),
        review_key: str = Form(default=""),
    ):
        if not csrf_valid(request, csrf_token) or not review_key:
            return today_error(request)
        start_job(
            request, "review", {"review_key": review_key}, cooldown=REVIEW_COOLDOWN,
            runner=lambda job_id: run_review_job(store=store, job_id=job_id, review_key=review_key,
                                                 operation=run_review, lock_directory=lock_directory))
        return RedirectResponse(url="/", status_code=303)

    @router.post("/actions/plan")
    def submit_plan(
        request: Request,
        csrf_token: str = Form(default=""),
        week_start: str = Form(default=""),
        on_conflict: str = Form(default=""),
    ):
        if not csrf_valid(request, csrf_token):
            return plan_error(request)
        if not ai_ready():
            return plan_error(request, "Generowanie planu wymaga włączenia wysyłania danych do AI.",
                              status_code=400, error_command="setup")
        if any(job.operation == "sync" and job.status in {"accepted", "running"} for job in store.list_jobs().jobs):
            # Plan ma powstać na świeżych danych; przycisk jest wtedy wyłączony, to bezpiecznik dla starej karty.
            return RedirectResponse(url=plan_url(week_start), status_code=303)
        decision, redirect = decide("plan", week_start, on_conflict)
        if redirect is not None:
            return redirect
        start_job(
            request, "plan", {"week_start": week_start, "on_conflict": decision}, cooldown=PLAN_COOLDOWN,
            runner=lambda job_id: run_plan_job(store=store, job_id=job_id, operation=run_plan, week_start=week_start,
                                               lock_directory=lock_directory, on_conflict=decision))
        return RedirectResponse(url="/plan", status_code=303)

    @router.post("/actions/plan/push")
    def submit_plan_push(
        request: Request,
        csrf_token: str = Form(default=""),
        week_start: str = Form(default=""),
        on_conflict: str = Form(default=""),
    ):
        if not csrf_valid(request, csrf_token):
            return plan_error(request)
        decision, redirect = decide("push", week_start, on_conflict)
        if redirect is not None:
            return redirect
        start_job(
            request, "plan_push", {"week_start": week_start, "on_conflict": decision}, cooldown=PLAN_PUSH_COOLDOWN,
            runner=lambda job_id: run_plan_push_job(store=store, job_id=job_id, operation=run_plan_push,
                                                    week_start=week_start, lock_directory=lock_directory,
                                                    on_conflict=decision))
        return RedirectResponse(url="/plan", status_code=303)

    @router.post("/actions/plan/remove")
    def remove_plan_day(
        request: Request,
        csrf_token: str = Form(default=""),
        week_start: str = Form(default=""),
        date: str = Form(default=""),
        scope: str = Form(default="plan"),
    ):
        """Usuń trening dnia z planu; z zegarkiem w tle, bo to logowanie do Garmina."""
        if not csrf_valid(request, csrf_token):
            return plan_error(request)
        monday = week_monday(week_start)
        if scope == "garmin":
            operation = partial(remove_plan_workout, day=date, from_garmin=True, today=today())
            start_job(
                request, "plan_remove", {"week_start": week_start, "date": date},
                runner=lambda job_id: run_plan_push_job(store=store, job_id=job_id, operation=operation,
                                                        week_start=monday.date().isoformat(),
                                                        lock_directory=lock_directory))
            return RedirectResponse(url=plan_url(week_start), status_code=303)
        try:
            with acquire_lock(name="plan", directory=lock_directory):
                remove_plan_workout(week_start=monday.date().isoformat(), day=date, today=today())
        except LockBusyError:
            pass
        except ValueError as error:
            return plan_error(request, str(error), status_code=400, anchor=monday)
        return RedirectResponse(url=plan_url(week_start), status_code=303)

    @router.post("/actions/plan/edit")
    def edit_plan_day(
        request: Request,
        csrf_token: str = Form(default=""),
        week_start: str = Form(default=""),
        date: str = Form(default=""),
        action: str = Form(default=""),
        target: str = Form(default=""),
    ):
        """Przenieś, skróć albo złagodź jeden trening; gdy jest na zegarku — w tle, bo to logowanie do Garmina."""
        if not csrf_valid(request, csrf_token):
            return plan_error(request)
        monday = week_monday(week_start)
        operation = partial(edit_plan_workout, day=date, action=action, target=target or None, today=today())
        touched = {date, target} if action == "move" else {date}
        on_watch = any(w.get("garmin_workout_id") for w in (stored_plan(week_start) or {}).get("workouts") or []
                       if w.get("date") in touched)
        if on_watch:
            start_job(
                request, "plan_edit", {"week_start": week_start, "date": date, "action": action, "target": target},
                runner=lambda job_id: run_plan_push_job(store=store, job_id=job_id, operation=operation,
                                                        week_start=monday.date().isoformat(),
                                                        lock_directory=lock_directory))
            return RedirectResponse(url=plan_url(week_start), status_code=303)
        try:
            with acquire_lock(name="plan", directory=lock_directory):
                operation(week_start=monday.date().isoformat())
        except LockBusyError:
            pass
        except ValueError as error:
            return plan_error(request, str(error), status_code=400, anchor=monday)
        return RedirectResponse(url=plan_url(week_start), status_code=303)

    @router.post("/actions/plan/variant")
    def plan_variant(
        request: Request,
        csrf_token: str = Form(default=""),
        week_start: str = Form(default=""),
        variant: str = Form(default=""),
        decision: str = Form(default=""),
    ):
        """Użyj drugiej wersji planu albo odłóż ją do archiwum; nic nie jest kasowane."""
        if not csrf_valid(request, csrf_token):
            return plan_error(request)
        monday = week_monday(week_start)
        try:
            with acquire_lock(name="plan", directory=lock_directory):
                if decision == "activate":
                    plan_conflicts.activate_variant(monday, variant)
                elif decision == "archive":
                    plan_conflicts.archive_variant(monday, variant)
                else:
                    raise ValueError("Nieznana decyzja.")
        except LockBusyError:
            pass
        except ValueError as error:
            return plan_error(request, str(error), status_code=400, anchor=monday)
        return RedirectResponse(url=plan_url(week_start), status_code=303)

    @router.post("/actions/plan/note")
    def save_plan_note(
        request: Request,
        csrf_token: str = Form(default=""),
        week_start: str = Form(default=""),
        note: str = Form(default=""),
        clear: str = Form(default=""),
    ):
        """Wiadomość do trenera na tydzień; pusty tekst albo „Usuń wiadomość” ją czyści."""
        if not csrf_valid(request, csrf_token):
            return plan_error(request)
        set_week_note(week_monday(week_start), "" if clear else note)
        return RedirectResponse(url=plan_url(week_start) + "&note=saved#wiadomosc", status_code=303)

    @router.post("/actions/recommendation")
    def submit_recommendation(
        request: Request,
        csrf_token: str = Form(default=""),
        message: str = Form(default=""),
        scope: str = Form(default="today"),
    ):
        if not csrf_valid(request, csrf_token):
            return today_error(request)
        if not ai_ready():
            return RedirectResponse(url="/?ai=off", status_code=303)
        week_scope = scope == "week" and bool(clean(message, MESSAGE_LIMIT))

        def save_week_note(job):
            """„Dotyczy całego tygodnia”: najpierw dopisanie do wiadomości tygodnia, potem odpowiedź trenera."""
            if not week_scope:
                return True
            try:
                append_week_note(today().date(), message)
            except ValueError:
                store.mark_running(job.id)
                store.mark_failed(job.id, message=WEEK_NOTE_FULL_MESSAGE)
                return False
            return True

        # Rozmowa: każde pytanie to nowe zadanie (bez blokady czasowej); równolegle trwa najwyżej jedno.
        job = start_job(
            request, "recommendation", {"date": today().date().isoformat(), "message": message, "scope": scope},
            prepare=save_week_note,
            runner=lambda job_id: run_recommendation_job(
                store=store, job_id=job_id, operation=run_recommendation, lock_directory=lock_directory,
                message=clean(message, MESSAGE_LIMIT) or None, scope="week" if week_scope else None))
        if job is None:
            # Trener odpowiada jeszcze na poprzednie pytanie — zostajemy na stronie głównej z jasną informacją.
            return RedirectResponse(url="/?rec=busy#rozmowa", status_code=303)
        return RedirectResponse(url="/#rozmowa", status_code=303)

    @router.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_status(request: Request, job_id: str):
        try:
            job = store.get(job_id)
        except JobNotFoundError:
            raise HTTPException(404, "Nie znaleziono zadania.")
        labels = {
            "accepted": "Zadanie przyjęte, za chwilę się zacznie.",
            "running": "Trwa. Strona aktualizuje się automatycznie.",
            "succeeded": "Gotowe. Dane są zaktualizowane.",
            "failed": "Nie udało się. Spróbuj ponownie.",
            "unknown": "Nie wiemy, czy operacja się dokończyła. Sprawdź dane, zanim spróbujesz ponownie.",
        }
        return templates.TemplateResponse(
            request=request,
            name="job.html",
            context={
                "job": job,
                "title": {"sync": "Synchronizacja danych", "plan": "Układanie planu",
                          "plan_push": "Wysyłka planu na zegarek", "plan_remove": "Usuwanie treningu z zegarka",
                          "plan_edit": "Zmiana treningu",
                          "review": "Ocena treningu", "recommendation": "Rekomendacja na dziś",
                          }.get(job.operation, "Zadanie w tle"),
                "message": labels[job.status],
                "progress": (progress_view(store.directory, job.id)
                             if job.operation == "sync" and job.status in {"accepted", "running"} else None),
                "status_label": {"accepted": "w kolejce", "running": "trwa", "succeeded": "gotowe",
                                 "failed": "błąd", "unknown": "nieznany"}.get(job.status, job.status),
                "active_nav": "today",
            },
            headers={"Cache-Control": "no-store"},
        )

    return router
