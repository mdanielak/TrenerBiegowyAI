# -*- coding: utf-8 -*-
"""Dashboard and readiness views router."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Optional, cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.data_extract import SnapshotStatus
from services.journal import entries_by_day
from services.wizard import needs_onboarding
from services.jobs import JobStore
from services.today import TodayReport
from api.schemas import HealthResponse, ReadinessResponse
from api.views.analysis import _CONFIDENCE_LABELS, _analysis_reason, _analysis_rows, _readiness_week
from api.views.common import (
    _HRV_STATUSES,
    _READINESS_LABELS,
    _WEEKDAYS,
    _WEEKDAYS_SHORT,
    _format_date,
    _format_score,
    _format_sync_time,
)
from api.views.jobs import _sync_banner
from api.views.plan import _plan_workout_view
from api.views.today import (
    CONVERSATION_DAYS,
    _SUGGESTIONS,
    _conversation_view,
    _raise_report_error,
    _report_error,
    _ring_geometry,
    _health_alert,
    _next_workout_view,
    _pause_view,
    _signal_cards,
    _workout_section,
)

logger = logging.getLogger(__name__)


def get_dashboard_router(
    *,
    report_provider: Callable[[], TodayReport],
    profile_provider: Callable[[], dict],
    review_loader: Callable[..., Optional[dict]],
    recommendation_loader: Callable[..., Optional[dict]],
    store: JobStore,
    recommendation_history: Callable[..., list] | None = None,
    now_provider: Callable[[], datetime],
    templates: Jinja2Templates,
    attach_csrf: Callable,
    csrf_token: Callable,
    app_version: str,
    journal_path,
    ai_badge_provider: Callable[[], dict] | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=app_version)

    @router.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        report = report_provider()
        if report.status == "profile_missing":
            # Pierwsze uruchomienie: zamiast polecenia z terminala — połączenie zegarka w przeglądarce.
            return RedirectResponse(url="/setup/garmin", status_code=303)
        if report.status != "ok":
            status_code, message, command = _report_error(report)
            return attach_csrf(
                templates.TemplateResponse(
                    request=request,
                    name="today.html",
                    context={
                        "error_message": message,
                        "error_command": None if report.status == "snapshot_missing" else command,
                        "error_sync": report.status in ("snapshot_missing", "snapshot_invalid"),
                        "csrf_token": csrf_token(request),
                        "sync_banner": {"refresh": False},
                        "active_nav": "today",
                    },
                    status_code=status_code,
                    headers={"Cache-Control": "no-store"},
                ),
                csrf_token(request),
            )

        try:
            profile = profile_provider()
        except (FileNotFoundError, OSError, ValueError):
            profile = None
        first_run = profile is not None and needs_onboarding(profile)
        zone_floors = (profile or {}).get("hr_zone_floors") or {}
        if first_run:
            return RedirectResponse(url="/wizard", status_code=303)

        readiness_data = cast(dict, report.readiness)
        token = csrf_token(request)
        now = now_provider()
        banner = _sync_banner(store, now)
        badge = ai_badge_provider() if ai_badge_provider is not None else None
        journal_by_day = entries_by_day(path=journal_path)
        try:
            recommendation = recommendation_loader(date=report.date)
            since = (date.fromisoformat(report.date) - timedelta(days=CONVERSATION_DAYS)).isoformat()
            history = recommendation_history(since=since) if recommendation_history is not None else []
        except (OSError, ValueError):
            recommendation, history = None, []
        conversation_today, conversation_days = _conversation_view(history, report.date, fallback=recommendation)
        # Trwająca albo nieudana odpowiedź trenera: bez tego po wysłaniu pytania strona milczała.
        coach_jobs = [job for job in store.list_jobs().jobs if job.operation == "recommendation"]
        latest_coach_job = max(coach_jobs, key=lambda job: job.created_at, default=None)
        coach_pending = latest_coach_job is not None and latest_coach_job.status in ("accepted", "running")
        last_answer_at = max((str(entry.get("created_at") or "") for entry in history if entry.get("date") == report.date),
                             default="")
        coach_failed = None
        if (latest_coach_job is not None and latest_coach_job.status in ("failed", "unknown")
                and latest_coach_job.created_at[:10] >= report.date and latest_coach_job.created_at > last_answer_at):
            coach_failed = (latest_coach_job.error_message if latest_coach_job.status == "failed"
                            else "Odpowiedź przerwało zamknięcie aplikacji.")
        return attach_csrf(
            templates.TemplateResponse(
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
                    "readiness_score": ("—" if readiness_data["level"] == "no_data"
                                        else _format_score(readiness_data["score"])),
                    "readiness_max_score": _format_score(readiness_data["max_score"]),
                    "readiness_label": _READINESS_LABELS.get(readiness_data["level"], readiness_data["level"]),
                    "csrf_token": token,
                    "sync_banner": banner,
                    "last_sync_time": _format_sync_time(getattr(report, "snapshot_timestamp", None), now),
                    "signal_cards": _signal_cards(report),
                    "ring": _ring_geometry(readiness_data["score"], readiness_data["max_score"]),
                    "workout": _workout_section(report, profile_provider, review_loader),
                    "pause": _pause_view(report),
                    "plan_workout": _plan_workout_view(getattr(report, "plan_workout", None), floors=zone_floors),
                    "next_workout": _next_workout_view(getattr(report, "next_workout", None), report.date),
                    "ai_recommendation": conversation_today[-1] if conversation_today else None,
                    "conversation_today": conversation_today,
                    "conversation_days": conversation_days,
                    "coach_pending": coach_pending,
                    "coach_failed": coach_failed,
                    "coach_busy": request.query_params.get("rec") == "busy",
                    "journal_missing": report.date not in journal_by_day,
                    "health_alert": _health_alert(report, [journal_by_day[day] for day in (report.date, report.yesterday_date)
                                                           if day in journal_by_day]),
                    "ai_ready": badge is not None and badge["state"] not in ("missing", "no_consent"),
                    "ai_off_notice": request.query_params.get("ai") == "off",
                    "active_nav": "today",
                },
                headers={"Cache-Control": "no-store"},
            ),
            token,
        )

    @router.get("/readiness", response_model=ReadinessResponse)
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

    @router.get("/week")
    def week():
        """Kalendarz został połączony z Planem; stare zakładki prowadzą na Plan."""
        return RedirectResponse(url="/plan", status_code=303)

    @router.get("/analysis", response_class=HTMLResponse)
    def analysis(request: Request):
        report = report_provider()
        if report.status != "ok":
            status_code, message, command = _report_error(report)
            return templates.TemplateResponse(
                request=request,
                name="analysis.html",
                context={
                    "error_message": message,
                    "error_command": command,
                    "active_nav": "analysis",
                },
                status_code=status_code,
                headers={"Cache-Control": "no-store"},
            )

        readiness_data = cast(dict, report.readiness)
        available = readiness_data.get("available_metrics") or []
        missing = readiness_data.get("missing_metrics") or []
        rows = _analysis_rows(readiness_data)
        return templates.TemplateResponse(
            request=request,
            name="analysis.html",
            context={
                "formatted_date": _format_date(report.date),
                "weekday": _WEEKDAYS[report.weekday_index],
                "is_stale": report.snapshot_status is SnapshotStatus.STALE,
                "level": readiness_data["level"],
                "readiness_score": ("—" if readiness_data["level"] == "no_data"
                                    else _format_score(readiness_data["score"])),
                "readiness_max_score": _format_score(readiness_data["max_score"]),
                "readiness_label": _READINESS_LABELS.get(readiness_data["level"], readiness_data["level"]),
                "ring": _ring_geometry(readiness_data["score"], readiness_data["max_score"]),
                "metric_rows": rows,
                "reason": _analysis_reason(rows),
                "week": _readiness_week(getattr(report, "readiness_week", None) or [], _WEEKDAYS_SHORT),
                "confidence_label": _CONFIDENCE_LABELS.get(str(readiness_data.get("confidence") or ""), "brak"),
                "metrics_available": len(available),
                "metrics_total": len(available) + len(missing),
                "active_nav": "analysis",
            },
            headers={"Cache-Control": "no-store"},
        )

    return router
