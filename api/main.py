# -*- coding: utf-8 -*-
"""Lokalne API i dashboard Trenera Biegowego AI."""
from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, NoReturn, Optional, cast
from urllib.parse import urlparse

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from services.data_extract import SnapshotStatus
from services.actions import run_sync_job, synchronize_data
from services.jobs import JobConflictError, JobCooldownError, JobNotFoundError, JobStore
from services.locking import LockBusyError, acquire_lock
from services.today import TodayReport, get_today_report
from services.week import WeekReport, get_week_report
from trainer.logging_config import setup_logging


logger = logging.getLogger(__name__)
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
_WEEKDAYS = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")
_SUGGESTIONS = {
    "follow_plan": "realizuj zaplanowany trening spokojnie",
    "rest": "postaw na odpoczynek lub bardzo lekki ruch",
}
_READINESS_LABELS = {
    "ready": "gotowy do treningu",
    "ready_with_reserves": "gotowy, z rezerwą",
    "not_ready": "nie jesteś gotowy do treningu",
}
_HRV_STATUSES = {
    "BALANCED": "zrównoważone",
    "UNBALANCED": "niezrównoważone",
    "LOW": "niskie",
    "POOR": "słabe",
    "UNKNOWN": "brak oceny",
}
_MONTHS_GENITIVE = (
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
)
_WEEK_STATUS_LABELS = {
    "no_plan": "Brak zapisanego treningu",
    "activity_only": "Aktywności bez zapisanego treningu",
    "planned": "Zaplanowane",
    "matched": "Znaleziono wykonanie",
    "partially_matched": "Znaleziono wykonanie części treningów",
    "no_record": "Brak wykonania w lokalnych danych",
    "uncertain": "Nie można jednoznacznie porównać",
}
_WEEK_WARNING_LABELS = {
    "snapshot_stale": "Dane o aktywnościach mogą być nieaktualne. Uruchom `python -m trainer sync`.",
    "snapshot_activities_may_be_incomplete": "Lista aktywności może być niepełna, bo obejmuje tylko 50 ostatnich treningów.",
}
SYNC_COOLDOWN = timedelta(seconds=60)
_CSRF_COOKIE = "trainer_csrf"


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadinessDetail(BaseModel):
    metric: str
    status: str
    message: str


class ReadinessResponse(BaseModel):
    score: float
    max_score: float
    raw_score: float
    available_max_score: float
    insufficient_data: bool
    missing_metrics: List[str]
    available_metrics: List[str]
    data_coverage: float
    confidence: str
    level: str
    rhr: Optional[float]
    hrv_status: Optional[str]
    hrv_last: Optional[float]
    hrv_baseline: Optional[str]
    sleep_score_val: Optional[float]
    sleep_total: Optional[float]
    stress: Optional[float]
    details: List[ReadinessDetail]
    warning: Optional[str] = None


def _report_error(report: TodayReport) -> tuple[int, str, str]:
    """Zwróć publiczną, jednolitą odpowiedź dla niedostępnych danych."""
    if report.status == "profile_missing":
        return 404, "Brakuje lokalnego profilu.", "python -m trainer setup"
    if report.status == "snapshot_missing":
        return 404, "Brakuje lokalnego snapshotu danych.", "python -m trainer sync"
    if report.status == "snapshot_invalid":
        logger.error("Local data snapshot is invalid")
        return 503, "Lokalny snapshot danych jest niepoprawny.", "python -m trainer sync"
    raise ValueError(f"Nieznany stan raportu: {report.status}")


def _raise_report_error(report: TodayReport) -> NoReturn:
    status_code, message, command = _report_error(report)
    raise HTTPException(status_code=status_code, detail=f"{message} Uruchom: {command}")


def _format_score(value: float) -> str:
    """Pokaż całkowitą gotowość bez zbędnego miejsca dziesiętnego."""
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


def _format_date(value: str) -> str:
    """Sformatuj datę raportu dla polskiego dashboardu."""
    parsed = date.fromisoformat(value)
    return f"{parsed.day} {_MONTHS_GENITIVE[parsed.month - 1]} {parsed.year}"


def _format_sync_time(value, now: datetime) -> str:
    """Pokaż czas snapshotu w lokalnej strefie, bez surowego formatu ISO."""
    if not isinstance(value, str) or not value:
        return "Nie wiadomo, kiedy ostatnio synchronizowano dane."
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            return "Nie wiadomo, kiedy ostatnio synchronizowano dane."
        local_timestamp = timestamp.astimezone()
        local_now = now.astimezone() if now.tzinfo is not None else now.astimezone()
    except (TypeError, ValueError, OverflowError):
        return "Nie wiadomo, kiedy ostatnio synchronizowano dane."
    days_ago = (local_now.date() - local_timestamp.date()).days
    clock = f"{local_timestamp.hour}:{local_timestamp.minute:02d}"
    if days_ago == 0:
        return f"Zsynchronizowano dziś o {clock}"
    if days_ago == 1:
        return f"Zsynchronizowano wczoraj o {clock}"
    if 2 <= days_ago <= 6:
        return f"Zsynchronizowano {days_ago} dni temu o {clock}"
    return f"Zsynchronizowano {local_timestamp.day} {_MONTHS_GENITIVE[local_timestamp.month - 1]} o {clock}"


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


def create_app(*, report_provider: Callable[[], TodayReport] = get_today_report,
               week_report_provider: Callable[[], WeekReport] = get_week_report,
                sync_operation: Callable[[], None] = synchronize_data,
                job_store: JobStore | None = None, lock_directory=None,
                now_provider: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> FastAPI:
    """Utwórz aplikację z wstrzykiwalnym, tylko do odczytu dostawcą raportu."""

    store = job_store or JobStore(Path("local/jobs"))
    scheduled_job_ids = set()

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        from concurrent.futures import ThreadPoolExecutor

        setup_logging(level=logging.INFO)
        logger.info("Trener Biegowy AI API starting")
        store.mark_abandoned_running_as_unknown()
        app_instance.state.job_executor = ThreadPoolExecutor(max_workers=1)
        try:
            yield
        finally:
            app_instance.state.job_executor.shutdown(wait=True)

    app = FastAPI(
        title="Trener Biegowy AI",
        description="Local running training dashboard",
        version="0.1.0",
        lifespan=lifespan,
    )

    def csrf_token(request: Request):
        return request.cookies.get(_CSRF_COOKIE) or secrets.token_urlsafe(32)

    def attach_csrf(response, token):
        if response.headers.get("set-cookie") is None:
            response.set_cookie(_CSRF_COOKIE, token, httponly=True, samesite="strict")
        return response

    def csrf_valid(request: Request, token: str):
        cookie = request.cookies.get(_CSRF_COOKIE)
        source = request.headers.get("origin") or request.headers.get("referer")
        if not cookie or not token or not secrets.compare_digest(cookie, token) or not source:
            return False
        parsed = urlparse(source)
        return parsed.netloc == request.headers.get("host") and parsed.scheme in {"http", "https"}

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        report = report_provider()
        if report.status != "ok":
            status_code, message, command = _report_error(report)
            return attach_csrf(_TEMPLATES.TemplateResponse(
                request=request,
                name="today.html",
                context={"error_message": message, "error_command": command,
                         "sync_banner": {"refresh": False}},
                status_code=status_code,
                headers={"Cache-Control": "no-store"},
            ), csrf_token(request))

        readiness_data = cast(dict, report.readiness)
        token = csrf_token(request)
        now = now_provider()
        banner = _sync_banner(store, now)
        return attach_csrf(_TEMPLATES.TemplateResponse(
            request=request,
            name="today.html",
            context={
                "report": report,
                "formatted_date": _format_date(report.date),
                "weekday": _WEEKDAYS[report.weekday_index],
                "is_stale": report.snapshot_status is SnapshotStatus.STALE,
                "suggestion": _SUGGESTIONS[report.suggestion].capitalize(),
                "hrv_status": (
                    _HRV_STATUSES.get(report.signals["hrv_status"], report.signals["hrv_status"])
                    if report.signals["hrv_status"] is not None else None
                ),
                "readiness_score": _format_score(readiness_data["score"]),
                "readiness_max_score": _format_score(readiness_data["max_score"]),
                "readiness_label": _READINESS_LABELS.get(readiness_data["level"], readiness_data["level"]),
                "csrf_token": token,
                "sync_banner": banner,
                "last_sync_time": _format_sync_time(getattr(report, "snapshot_timestamp", None), now),
            },
            headers={"Cache-Control": "no-store"},
        ), token)

    @app.get("/readiness", response_model=ReadinessResponse)
    def readiness() -> ReadinessResponse:
        report = report_provider()
        if report.status != "ok":
            _raise_report_error(report)
        readiness_data = cast(dict, report.readiness)
        warning = (
            "Dane snapshotu są nieaktualne. Uruchom: python -m trainer sync"
            if report.snapshot_status is SnapshotStatus.STALE else None
        )
        return ReadinessResponse(**readiness_data, warning=warning)

    @app.get("/week", response_class=HTMLResponse)
    def week(request: Request):
        try:
            report = week_report_provider()
        except FileNotFoundError:
            return _TEMPLATES.TemplateResponse(
                request=request, name="week.html",
                context={"error_message": "Brakuje lokalnych danych raportu.",
                         "error_command": "python -m trainer sync"},
                status_code=404, headers={"Cache-Control": "no-store"},
            )
        except Exception:
            logger.error("Could not build weekly report")
            return _TEMPLATES.TemplateResponse(
                request=request, name="week.html",
                context={"error_message": "Nie można odczytać lokalnych danych raportu.",
                         "error_command": "python -m trainer sync"},
                status_code=503, headers={"Cache-Control": "no-store"},
            )
        return _TEMPLATES.TemplateResponse(
            request=request, name="week.html",
            context={
                "report": report,
                "weekdays": _WEEKDAYS,
                "day_status_labels": _WEEK_STATUS_LABELS,
                "warning_labels": _WEEK_WARNING_LABELS,
                "format_date": _format_date,
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/actions/sync")
    def submit_sync(request: Request, csrf_token: str = Form(default="")):
        if not csrf_valid(request, csrf_token):
            return _TEMPLATES.TemplateResponse(
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
                    return run_sync_job(store=store, job_id=job.id, operation=sync_operation,
                                        fresh=False, lock_directory=lock_directory)
                finally:
                    scheduled_job_ids.discard(job.id)
            request.app.state.job_executor.submit(execute)
        return RedirectResponse(url="/", status_code=303)

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
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
        return _TEMPLATES.TemplateResponse(request=request, name="job.html",
                                           context={"job": job, "message": labels[job.status]},
                                           headers={"Cache-Control": "no-store"})

    return app


app = create_app()
