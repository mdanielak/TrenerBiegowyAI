# -*- coding: utf-8 -*-
"""Dashboard and readiness views router."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Optional, cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from services.data_extract import SnapshotStatus
from services.jobs import JobStore
from services.today import TodayReport
from services.week import WeekReport
from api.schemas import HealthResponse, ReadinessResponse
from api.views.analysis import _CONFIDENCE_LABELS, _analysis_measurements, _analysis_rows
from api.views.common import (
    _HRV_STATUSES,
    _READINESS_LABELS,
    _WEEK_STATUS_LABELS,
    _WEEK_WARNING_LABELS,
    _WEEKDAYS,
    _WEEKDAYS_SHORT,
    _format_date,
    _format_minutes,
    _format_score,
    _format_sync_time,
    _readiness_pill,
)
from api.views.jobs import _sync_banner
from api.views.plan import _plan_workout_view
from api.views.today import (
    _SUGGESTIONS,
    _raise_report_error,
    _readiness_chart,
    _recommendation_view,
    _report_error,
    _ring_geometry,
    _signal_cards,
    _workout_section,
)

logger = logging.getLogger(__name__)


def get_dashboard_router(
    *,
    report_provider: Callable[[], TodayReport],
    week_report_provider: Callable[[], WeekReport],
    profile_provider: Callable[[], dict],
    review_loader: Callable[..., Optional[dict]],
    recommendation_loader: Callable[..., Optional[dict]],
    store: JobStore,
    now_provider: Callable[[], datetime],
    templates: Jinja2Templates,
    attach_csrf: Callable,
    csrf_token: Callable,
    app_version: str,
) -> APIRouter:
    router = APIRouter()

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=app_version)

    @router.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        report = report_provider()
        if report.status != "ok":
            status_code, message, command = _report_error(report)
            return attach_csrf(
                templates.TemplateResponse(
                    request=request,
                    name="today.html",
                    context={
                        "error_message": message,
                        "error_command": command,
                        "sync_banner": {"refresh": False},
                        "active_nav": "today",
                    },
                    status_code=status_code,
                    headers={"Cache-Control": "no-store"},
                ),
                csrf_token(request),
            )

        readiness_data = cast(dict, report.readiness)
        token = csrf_token(request)
        now = now_provider()
        banner = _sync_banner(store, now)
        try:
            recommendation = recommendation_loader(date=report.date)
        except OSError:
            recommendation = None
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
                    "readiness_score": _format_score(readiness_data["score"]),
                    "readiness_max_score": _format_score(readiness_data["max_score"]),
                    "readiness_label": _READINESS_LABELS.get(readiness_data["level"], readiness_data["level"]),
                    "csrf_token": token,
                    "sync_banner": banner,
                    "last_sync_time": _format_sync_time(getattr(report, "snapshot_timestamp", None), now),
                    "signal_cards": _signal_cards(report),
                    "ring": _ring_geometry(readiness_data["score"], readiness_data["max_score"]),
                    "workout": _workout_section(report, profile_provider, review_loader),
                    "plan_workout": _plan_workout_view(getattr(report, "plan_workout", None)),
                    "ai_recommendation": _recommendation_view(recommendation),
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

    @router.get("/week", response_class=HTMLResponse)
    def week(request: Request):
        try:
            report = week_report_provider()
        except FileNotFoundError:
            return templates.TemplateResponse(
                request=request,
                name="week.html",
                context={
                    "error_message": "Brakuje lokalnych danych raportu.",
                    "error_command": "python -m trainer sync",
                    "active_nav": "week",
                },
                status_code=404,
                headers={"Cache-Control": "no-store"},
            )
        except Exception:
            logger.error("Could not build weekly report")
            return templates.TemplateResponse(
                request=request,
                name="week.html",
                context={
                    "error_message": "Nie można odczytać lokalnych danych raportu.",
                    "error_command": "python -m trainer sync",
                    "active_nav": "week",
                },
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )
        return templates.TemplateResponse(
            request=request,
            name="week.html",
            context={
                "report": report,
                "weekdays": _WEEKDAYS,
                "day_status_labels": _WEEK_STATUS_LABELS,
                "warning_labels": _WEEK_WARNING_LABELS,
                "format_date": _format_date,
                "format_minutes": _format_minutes,
                "readiness_pill": _readiness_pill,
                "weekdays_short": _WEEKDAYS_SHORT,
                "chart": _readiness_chart(report.days),
                "active_nav": "week",
            },
            headers={"Cache-Control": "no-store"},
        )

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
        return templates.TemplateResponse(
            request=request,
            name="analysis.html",
            context={
                "formatted_date": _format_date(report.date),
                "weekday": _WEEKDAYS[report.weekday_index],
                "is_stale": report.snapshot_status is SnapshotStatus.STALE,
                "level": readiness_data["level"],
                "readiness_score": _format_score(readiness_data["score"]),
                "readiness_max_score": _format_score(readiness_data["max_score"]),
                "readiness_label": _READINESS_LABELS.get(readiness_data["level"], readiness_data["level"]),
                "metric_rows": _analysis_rows(readiness_data),
                "measurements": _analysis_measurements(readiness_data),
                "confidence_label": _CONFIDENCE_LABELS.get(str(readiness_data.get("confidence") or ""), "brak"),
                "metrics_available": len(available),
                "metrics_total": len(available) + len(missing),
                "raw_score": _format_score(float(readiness_data.get("raw_score") or 0)),
                "available_max_score": _format_score(float(readiness_data.get("available_max_score") or 0)),
                "active_nav": "analysis",
            },
            headers={"Cache-Control": "no-store"},
        )

    return router
