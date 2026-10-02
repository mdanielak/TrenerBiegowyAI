# -*- coding: utf-8 -*-
"""Lokalne API i dashboard Trenera Biegowego AI."""
from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import List, NoReturn, Optional, cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from services.data_extract import SnapshotStatus
from services.today import TodayReport, get_today_report
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


def create_app(*, report_provider: Callable[[], TodayReport] = get_today_report) -> FastAPI:
    """Utwórz aplikację z wstrzykiwalnym, tylko do odczytu dostawcą raportu."""

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        setup_logging(level=logging.INFO)
        logger.info("Trener Biegowy AI API starting")
        yield

    app = FastAPI(
        title="Trener Biegowy AI",
        description="Local running training dashboard",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        report = report_provider()
        if report.status != "ok":
            status_code, message, command = _report_error(report)
            return _TEMPLATES.TemplateResponse(
                request=request,
                name="today.html",
                context={"error_message": message, "error_command": command},
                status_code=status_code,
                headers={"Cache-Control": "no-store"},
            )

        readiness_data = cast(dict, report.readiness)
        return _TEMPLATES.TemplateResponse(
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
            },
            headers={"Cache-Control": "no-store"},
        )

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

    return app


app = create_app()
