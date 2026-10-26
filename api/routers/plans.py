"""Plan tygodniowy: strona /plan."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from services.data_extract import SnapshotStatus, read_snapshot_status
from services.plan import previous_week_load
from services.readiness import readiness_for_day
from services.training_plan import week_bounds
from api.formatters import (
    _WEEK_WARNING_LABELS,
    _format_date,
    _format_generated_at,
    _plan_banner,
    _plan_load_chart,
    _plan_view,
)

logger = logging.getLogger(__name__)

PLAN_MESSAGES = {
    "running": "Trwa układanie planu na ten tydzień. Strona odświeży się sama.",
    "failed": "Nie udało się ułożyć planu. Spróbuj ponownie.",
    "succeeded": "Plan na ten tydzień jest gotowy.",
}
PLAN_PUSH_MESSAGES = {
    "running": "Trwa wysyłka planu na zegarek. Strona odświeży się sama.",
    "failed": "Nie udało się wysłać planu na zegarek.",
    "succeeded": "Plan trafił na zegarek.",
}
_EMPTY_BANNER = {"message": None, "details_url": None, "refresh": False, "disabled": False}


def plan_page_context(*, today, csrf_token="", plan_data=None, availability=None, ai_ready=False,
                      banner=None, push_banner=None, error_message=None, error_command=None,
                      now=None, readiness_by_date=None, previous_week=None,
                      snapshot_stale=False, anchor=None) -> dict:
    """Zbuduj kontekst strony planu; ten sam zestaw używa router i obsługa błędów CSRF."""
    monday, sunday = week_bounds(anchor or today)
    plan = _plan_view(
        plan_data,
        today=today.date().isoformat(),
        availability=availability,
        readiness_by_date=readiness_by_date,
        previous_week=previous_week,
    )
    return {
        "active_nav": "plan",
        "csrf_token": csrf_token,
        "plan": plan,
        "plan_banner": banner or _EMPTY_BANNER,
        "push_banner": push_banner or _EMPTY_BANNER,
        "ai_ready": ai_ready,
        "week_start": monday.date().isoformat(),
        "week_end": sunday.date().isoformat(),
        "format_date": _format_date,
        "plan_generated_at": _format_generated_at(
            (plan_data or {}).get("generated_at"), now or datetime.now()
        ),
        "load_chart": _plan_load_chart(plan.get("days") or []),
        "snapshot_stale": bool(snapshot_stale),
        "snapshot_warning": _WEEK_WARNING_LABELS["snapshot_stale"],
        "prev_week": (monday - timedelta(days=7)).date().isoformat(),
        "current_week": week_bounds(today)[0].date().isoformat(),
        "next_week": (monday + timedelta(days=7)).date().isoformat(),
        "error_message": error_message,
        "error_command": error_command,
    }


def get_plans_router(
    *,
    plan_provider: Callable[[str], dict | None],
    profile_provider: Callable[[], dict],
    ai_settings_provider: Callable[[], dict],
    availability_provider: Callable[[], dict],
    store,
    now_provider: Callable[[], datetime],
    templates: Jinja2Templates,
    attach_csrf: Callable,
    csrf_token: Callable,
    snapshot_provider: Callable[[], object] = read_snapshot_status,
) -> APIRouter:
    router = APIRouter()

    @router.get("/plan", response_class=HTMLResponse)
    def plan(request: Request):
        now = now_provider()
        today = now.astimezone() if now.tzinfo is not None else now
        requested = request.query_params.get("week")
        try:
            anchor = datetime.fromisoformat(requested[:10]) if requested else today
        except ValueError:
            anchor = today

        monday, _ = week_bounds(anchor)
        try:
            stored = plan_provider(monday.date().isoformat())
        except (OSError, ValueError):
            logger.error("Could not read the training plan")
            stored = None

        error_message = None
        error_command = None
        try:
            profile_provider()
        except FileNotFoundError:
            error_message = "Brakuje lokalnego profilu biegacza."
            error_command = "python -m trainer setup"
        except Exception:
            logger.error("Could not read runner profile")
            error_message = "Nie można odczytać lokalnego profilu biegacza."
            error_command = "python -m trainer setup"

        snapshot = snapshot_provider()
        if snapshot.status is SnapshotStatus.MISSING:
            error_message = "Brakuje lokalnego snapshotu danych."
            error_command = "python -m trainer sync"
        data = snapshot.data or {}

        readiness_by_date = {}
        for offset in range(7):
            day_text = (monday + timedelta(days=offset)).date().isoformat()
            try:
                breakdown = readiness_for_day(data, day_text)
            except (KeyError, TypeError, ValueError):
                continue
            if breakdown:
                readiness_by_date[day_text] = breakdown

        previous_week = previous_week_load(data, monday) if data else None

        try:
            availability = availability_provider()
        except Exception:
            availability = {}

        try:
            ai_settings = ai_settings_provider() or {}
        except (OSError, UnicodeError):
            ai_settings = {}
        ai_ready = bool(ai_settings.get("key_present") and ai_settings.get("export_enabled"))

        token = csrf_token(request)
        context = plan_page_context(
            today=today,
            csrf_token=token,
            plan_data=stored,
            availability=availability,
            ai_ready=ai_ready,
            banner=_plan_banner(store, now, "plan", PLAN_MESSAGES),
            push_banner=_plan_banner(store, now, "plan_push", PLAN_PUSH_MESSAGES),
            error_message=error_message,
            error_command=error_command,
            now=now,
            readiness_by_date=readiness_by_date,
            previous_week=previous_week,
            snapshot_stale=snapshot.status is SnapshotStatus.STALE,
            anchor=monday,
        )
        return attach_csrf(
            templates.TemplateResponse(
                request=request,
                name="plan.html",
                context=context,
                headers={"Cache-Control": "no-store"},
            ),
            token,
        )

    return router
