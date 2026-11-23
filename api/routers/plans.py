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
from services.plan_files import week_bounds
from services.actions import week_review_key
from services.week_summary import summarize_week
from services import plan_conflicts
from services.ai_notes import WEEK_NOTE_LIMIT, note_for_week
from trainer import preferences
from api.views.common import _WEEK_WARNING_LABELS, _format_date
from api.views.jobs import _plan_banner
from api.views.plan import _conflict_view, _format_generated_at, _archive_views, _plan_load_chart, _plan_view, _variant_views

logger = logging.getLogger(__name__)

PLAN_MESSAGES = {
    "accepted": "Plan czeka w kolejce, np. na koniec synchronizacji z Garminem. Strona odświeży się sama.",
    "running": "Trener układa plan {tydzien}.\nStrona odświeży się sama, gdy będzie gotowy.",
    "failed": "Nie udało się ułożyć planu. Spróbuj ponownie.",
    "succeeded": "Plan tygodnia jest ułożony.",
}
PLAN_PUSH_MESSAGES = {
    "running": "Trwa wysyłka planu na zegarek.",
    "failed": "Nie udało się wysłać planu na zegarek.",
    "succeeded": "Plan trafił na zegarek.",
}
PLAN_REMOVE_MESSAGES = {
    "running": "Trwa usuwanie treningu z zegarka.",
    "failed": "Nie udało się usunąć treningu z zegarka. Plan został bez zmian.",
    "succeeded": "Trening usunięty z planu i z zegarka.",
}
PLAN_EDIT_MESSAGES = {
    "running": "Trwa zmiana treningu: najpierw znika z zegarka, potem zmienia się w planie.",
    "failed": "Nie udało się zmienić treningu, bo nie dało się go usunąć z zegarka. Plan został bez zmian.",
    "succeeded": "Trening zmieniony i zdjęty z zegarka. Wyślij plan ponownie przyciskiem „Wyślij do Garmina”.",
}
WEEK_COOKIE = "plan_week"
WEEK_COOKIE_MAX_AGE = 3 * 24 * 3600  # po kilku dniach plan sam wraca do bieżącego tygodnia
_EMPTY_BANNER = {"message": None, "details_url": None, "refresh": False, "disabled": False}


def _max_quality_sessions() -> int:
    """Ten sam limit, który dostaje model i egzekwuje normalize_plan."""
    try:
        return int(preferences.load_preferences().get("max_quality_sessions_per_week", 1) or 0)
    except (OSError, ValueError, TypeError):
        return 0


def _week_summary(stored, data, today, profile_provider) -> dict | None:
    """Plan a wykonanie tygodnia; propozycja na kolejny tydzień z tego samego profilu, co układanie planu."""
    if not stored or not isinstance(data, dict):
        return None
    return summarize_week(stored, data, today, profile_provider)[0]


def plan_page_context(*, today, csrf_token="", plan_data=None, availability=None, ai_ready=False,
                      banner=None, push_banner=None, remove_banner=None, error_message=None, error_command=None,
                      error_countdown=None,
                      now=None, readiness_by_date=None, previous_week=None,
                      snapshot_stale=False, anchor=None, conflict=None, variants=None, activities=None) -> dict:
    """Zbuduj kontekst strony planu; ten sam zestaw używa router i obsługa błędów CSRF."""
    monday, sunday = week_bounds(anchor or today)
    plan = _plan_view(
        plan_data,
        today=today.date().isoformat(),
        availability=availability,
        readiness_by_date=readiness_by_date,
        previous_week=previous_week,
    )
    pause_conflicts = [day for day in plan.get("days", []) if day.get("date")
                       and not day["is_rest"] and day["date"] >= today.date().isoformat()
                       and preferences.get_active_pause(day["date"])]
    return {
        "active_nav": "plan",
        "csrf_token": csrf_token,
        "plan": plan,
        "pause_conflicts": pause_conflicts,
        "plan_banner": banner or _EMPTY_BANNER,
        "push_banner": push_banner or _EMPTY_BANNER,
        "remove_banner": remove_banner or _EMPTY_BANNER,
        "ai_ready": ai_ready,
        "week_start": monday.date().isoformat(),
        "week_end": sunday.date().isoformat(),
        "format_date": _format_date,
        "plan_generated_at": _format_generated_at(
            (plan_data or {}).get("generated_at"), now or datetime.now()
        ),
        "load_chart": _plan_load_chart(plan.get("days") or [], activities),
        "snapshot_stale": bool(snapshot_stale),
        "snapshot_warning": _WEEK_WARNING_LABELS["snapshot_stale"],
        "prev_week": (monday - timedelta(days=7)).date().isoformat(),
        "current_week": week_bounds(today)[0].date().isoformat(),
        "next_week": (monday + timedelta(days=7)).date().isoformat(),
        "error_message": error_message,
        "error_countdown": error_countdown,
        "error_command": error_command,
        "conflict": conflict,
        "variants": variants or [],
        "week_note_limit": WEEK_NOTE_LIMIT,
        "max_quality_sessions": _max_quality_sessions(),
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
    registry_provider: Callable[[], list] | None = None,
    variants_provider: Callable[[datetime], list] = plan_conflicts.list_variants,
    archive_provider: Callable[[datetime], list] = plan_conflicts.list_archived,
    review_loader: Callable[..., dict | None] | None = None,
    ai_badge_provider: Callable[[], dict] | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.get("/plan", response_class=HTMLResponse)
    def plan(request: Request):
        now = now_provider()
        today = now.astimezone() if now.tzinfo is not None else now
        requested = request.query_params.get("week")
        if not requested:
            # Wejście z menu bez tygodnia: wracamy do tygodnia, który był otwarty ostatnio.
            requested = request.cookies.get(WEEK_COOKIE)
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
            error_command = "setup"
        except Exception:
            logger.error("Could not read runner profile")
            error_message = "Nie można odczytać lokalnego profilu biegacza."
            error_command = "setup"

        snapshot = snapshot_provider()
        if snapshot.status is SnapshotStatus.MISSING:
            error_message = "Nie ma jeszcze danych z zegarka."
            error_command = "sync"
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

        conflict = None
        confirm = request.query_params.get("confirm")
        if confirm == "plan" and stored is not None:
            conflict = _conflict_view("plan", plan_conflicts.plan_conflict_days(stored))
        elif confirm == "push" and stored is not None and registry_provider is not None:
            try:
                entries = registry_provider()
            except OSError:
                entries = []
            days = plan_conflicts.garmin_conflict_days(stored, entries)
            conflict = _conflict_view("push", days) if days else None
        try:
            variants = _variant_views(stored, variants_provider(monday))
        except OSError:
            variants = []
        try:
            previous_plans = _archive_views(archive_provider(monday), now)
        except OSError:
            previous_plans = []

        # Zmiana i usunięcie treningu dzielą jedno miejsce na stronie: pokazujemy to, co się dzieje teraz.
        edit_banner = _plan_banner(store, now, "plan_edit", PLAN_EDIT_MESSAGES)
        remove_banner = edit_banner if edit_banner["message"] else _plan_banner(
            store, now, "plan_remove", PLAN_REMOVE_MESSAGES)
        token = csrf_token(request)
        context = plan_page_context(
            today=today,
            csrf_token=token,
            plan_data=stored,
            availability=availability,
            ai_ready=ai_ready,
            banner=_plan_banner(store, now, "plan", PLAN_MESSAGES),
            push_banner=_plan_banner(store, now, "plan_push", PLAN_PUSH_MESSAGES),
            remove_banner=remove_banner,
            error_message=error_message,
            error_command=error_command,
            now=now,
            readiness_by_date=readiness_by_date,
            previous_week=previous_week,
            snapshot_stale=snapshot.status is SnapshotStatus.STALE,
            activities=data.get("activities") if isinstance(data, dict) else None,
            anchor=monday,
            conflict=conflict,
            variants=variants,
        )
        context["previous_plans"] = previous_plans
        context["week_summary"] = _week_summary(stored, data, today, profile_provider)
        context["week_comment"] = None
        if context["week_summary"] and review_loader is not None:
            try:
                saved = review_loader(review_key=week_review_key(monday))
                context["week_comment"] = (saved or {}).get("comment")
            except (OSError, ValueError):
                pass
        try:
            context["week_note"] = note_for_week(monday)
        except OSError:
            context["week_note"] = ""
        context["note_saved"] = request.query_params.get("note") == "saved"
        response = attach_csrf(
            templates.TemplateResponse(
                request=request,
                name="plan.html",
                context=context,
                headers={"Cache-Control": "no-store"},
            ),
            token,
        )
        if monday.date() == week_bounds(today)[0].date():
            response.delete_cookie(WEEK_COOKIE)  # bieżący tydzień to ustawienie domyślne, nie coś do pamiętania
        else:
            response.set_cookie(WEEK_COOKIE, monday.date().isoformat(), max_age=WEEK_COOKIE_MAX_AGE,
                                httponly=True, samesite="lax")
        return response

    return router
