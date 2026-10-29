# -*- coding: utf-8 -*-
"""Strona statystyk wielotygodniowych."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api.views.stats import _stats_view
from api.views.common import _format_date
from services.data_extract import SnapshotStatus
from services.stats import WEEK_OPTIONS, StatsReport, normalize_weeks

_ERRORS = {
    "snapshot_missing": (404, "Brakuje lokalnego snapshotu danych.", "python -m trainer sync"),
    "snapshot_invalid": (503, "Lokalny snapshot danych jest niepoprawny.", "python -m trainer sync"),
}


def get_stats_router(
    *,
    stats_report_provider: Callable[[int], StatsReport],
    templates: Jinja2Templates,
) -> APIRouter:
    router = APIRouter()

    @router.get("/stats", response_class=HTMLResponse)
    def stats_page(request: Request, weeks: str = ""):
        report = stats_report_provider(normalize_weeks(weeks))
        if report.status != "ok":
            status_code, message, command = _ERRORS[report.status]
            return templates.TemplateResponse(
                request=request,
                name="stats.html",
                context={"error_message": message, "error_command": command, "active_nav": "stats"},
                status_code=status_code,
                headers={"Cache-Control": "no-store"},
            )
        return templates.TemplateResponse(
            request=request,
            name="stats.html",
            context={
                "stats": _stats_view(report),
                "format_date": _format_date,
                "week_options": WEEK_OPTIONS,
                "is_stale": report.snapshot_status is SnapshotStatus.STALE,
                "active_nav": "stats",
            },
            headers={"Cache-Control": "no-store"},
        )

    return router
