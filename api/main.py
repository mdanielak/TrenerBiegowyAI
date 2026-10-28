# -*- coding: utf-8 -*-
"""Lokalne API i dashboard Trenera Biegowego AI."""
from __future__ import annotations

import hashlib
import logging
import secrets
import tomllib
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ai.connection_test import check_connection  # Re-exported for tests/api
from services.actions import synchronize_data
from services.assets import build_manifest
from services.data_extract import read_snapshot_status
from services.jobs import JobStore
from services.recommendations import load_recommendation
from services.goal import GoalReport, get_goal_report
from services.ai_status import AI_STATUS_PATH, ai_status_view, load_status
from services.journal import JOURNAL_PATH
from services.stats import StatsReport, get_stats_report
from services.today import TodayReport, get_today_report
from services.week import WeekReport, get_week_report
from services.workout_reviews import load_review
from trainer.ai_settings import ENV_PATH
from trainer.logging_config import setup_logging
from trainer.preferences import get_weekly_availability
from trainer.profile_store import load_profile

from api.schemas import HealthResponse, ReadinessDetail, ReadinessResponse  # Re-exported
from api.views.common import _SIGNAL_META, _format_number, _format_sync_time, _plural  # Re-exported
from api.routers.actions import get_actions_router
from api.routers.assets import get_assets_router
from api.routers.dashboard import get_dashboard_router
from api.routers.plans import get_plans_router
from api.routers.settings import get_settings_router
from api.routers.goal import get_goal_router
from api.routers.journal import get_journal_router
from api.routers.stats import get_stats_router

# Nazwy dostępne jako api.main.* dla testów i skryptów (np. podmiana check_connection w testach).
__all__ = [
    "HealthResponse", "ReadinessDetail", "ReadinessResponse", "_SIGNAL_META", "_format_sync_time",
    "check_connection", "create_app",
]

logger = logging.getLogger(__name__)
_CSRF_COOKIE = "trainer_csrf"
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
_TEMPLATES.env.filters["num"] = _format_number
_TEMPLATES.env.filters["plural"] = _plural


def _static_version(relative: str) -> str:
    """Krótki skrót treści pliku statycznego; zmiana pliku wymusza jego ponowne pobranie."""
    try:
        content = (Path(__file__).resolve().parents[1] / "static" / relative).read_bytes()
    except OSError:
        return "0"
    return hashlib.sha256(content).hexdigest()[:10]


_TEMPLATES.env.globals["css_version"] = _static_version("css/styles.css")


def _app_version() -> str:
    """Wersja aplikacji z `pyproject.toml` — jedno źródło prawdy dla CLI i API."""
    try:
        with (Path(__file__).resolve().parents[1] / "pyproject.toml").open("rb") as handle:
            return tomllib.load(handle)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "unknown"


def load_plan_for_week(monday_iso: str) -> dict | None:
    """Wczytaj zapisany plan tygodnia zawierającego podany poniedziałek."""
    from services.plan import load_week_plan as loader

    try:
        anchor = datetime.fromisoformat(monday_iso)
    except ValueError:
        return None
    return loader(anchor)


def ai_settings_view(ai_env_path: Path) -> dict:
    """Publiczny widok konfiguracji AI; nigdy nie zwraca klucza."""
    from trainer.ai_settings import read_ai_settings as reader

    try:
        return reader(ai_env_path)
    except (OSError, UnicodeError):
        return {}


def create_app(
    *,
    report_provider: Callable[[], TodayReport] = get_today_report,
    week_report_provider: Callable[[], WeekReport] = get_week_report,
    stats_report_provider: Callable[[int], StatsReport] = get_stats_report,
    goal_report_provider: Callable[[], GoalReport] = get_goal_report,
    journal_path: Path | None = None,
    registry_provider: Callable[[], list] | None = None,
    ai_status_path: Path | None = None,
    sync_operation: Callable[[], None] = synchronize_data,
    profile_provider: Callable[[], dict] = load_profile,
    review_operation: Callable[..., dict] | None = None,
    review_loader: Callable[..., Optional[dict]] = load_review,
    job_store: JobStore | None = None,
    lock_directory=None,
    ai_env_path: Path = ENV_PATH,
    now_provider: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    plan_operation: Callable[..., dict] | None = None,
    plan_push_operation: Callable[..., dict] | None = None,
    recommendation_operation: Callable[..., dict] | None = None,
    recommendation_loader: Callable[..., Optional[dict]] = load_recommendation,
    plan_provider: Callable[[str], Optional[dict]] = load_plan_for_week,
    availability_provider: Callable[[], dict] = get_weekly_availability,
    ai_settings_provider: Callable[[], dict] | None = None,
    snapshot_provider: Callable[[], object] = read_snapshot_status,
) -> FastAPI:
    """Utwórz aplikację z wstrzykiwalnym, tylko do odczytu dostawcą raportu."""
    store = job_store or JobStore(Path("local/jobs"))
    journal_path = journal_path or JOURNAL_PATH
    ai_status_path = ai_status_path or AI_STATUS_PATH
    settings_view = ai_settings_provider or (lambda: ai_settings_view(ai_env_path))

    def ai_badge():
        try:
            settings = settings_view() or {}
        except (OSError, UnicodeError):
            settings = {}
        return ai_status_view(settings, load_status(ai_status_path))
    if registry_provider is None:
        from services.workout_registry import library

        def registry_provider():
            return library("active")
    scheduled_job_ids = set()
    asset_manifest = build_manifest()

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
        version=_app_version(),
        lifespan=lifespan,
    )

    static_dir = Path(__file__).resolve().parents[1] / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    def csrf_token(request: Request) -> str:
        return request.cookies.get(_CSRF_COOKIE) or secrets.token_urlsafe(32)

    def attach_csrf(response, token: str):
        if response.headers.get("set-cookie") is None:
            response.set_cookie(_CSRF_COOKIE, token, httponly=True, samesite="strict")
        return response

    def csrf_valid(request: Request, token: str) -> bool:
        cookie = request.cookies.get(_CSRF_COOKIE)
        source = request.headers.get("origin") or request.headers.get("referer")
        if not cookie or not token or not secrets.compare_digest(cookie, token) or not source:
            return False
        parsed = urlparse(source)
        return parsed.netloc == request.headers.get("host") and parsed.scheme in {"http", "https"}

    # Include modular sub-routers
    app.include_router(get_assets_router(asset_manifest))
    app.include_router(
        get_dashboard_router(
            report_provider=report_provider,
            week_report_provider=week_report_provider,
            profile_provider=profile_provider,
            review_loader=review_loader,
            recommendation_loader=recommendation_loader,
            store=store,
            now_provider=now_provider,
            templates=_TEMPLATES,
            attach_csrf=attach_csrf,
            csrf_token=csrf_token,
            app_version=app.version,
            journal_path=journal_path,
            ai_badge_provider=ai_badge,
        )
    )
    app.include_router(get_stats_router(stats_report_provider=stats_report_provider, templates=_TEMPLATES))
    app.include_router(get_goal_router(goal_report_provider=goal_report_provider, templates=_TEMPLATES))
    app.include_router(get_journal_router(journal_path=journal_path, templates=_TEMPLATES, attach_csrf=attach_csrf,
                                          csrf_token=csrf_token, csrf_valid=csrf_valid))
    app.include_router(
        get_plans_router(
            plan_provider=plan_provider,
            profile_provider=profile_provider,
            ai_settings_provider=ai_settings_provider or (lambda: ai_settings_view(ai_env_path)),
            availability_provider=availability_provider,
            store=store,
            now_provider=now_provider,
            templates=_TEMPLATES,
            attach_csrf=attach_csrf,
            csrf_token=csrf_token,
            snapshot_provider=snapshot_provider,
            registry_provider=registry_provider,
            ai_badge_provider=ai_badge,
        )
    )
    app.include_router(
        get_settings_router(
            profile_provider=profile_provider,
            ai_env_path=ai_env_path,
            lock_directory=lock_directory,
            templates=_TEMPLATES,
            attach_csrf=attach_csrf,
            csrf_token=csrf_token,
            csrf_valid=csrf_valid,
            ai_status_path=ai_status_path,
        )
    )
    app.include_router(
        get_actions_router(
            store=store,
            scheduled_job_ids=scheduled_job_ids,
            sync_operation=sync_operation,
            review_operation=review_operation,
            report_provider=report_provider,
            profile_provider=profile_provider,
            lock_directory=lock_directory,
            templates=_TEMPLATES,
            csrf_valid=csrf_valid,
            plan_operation=plan_operation,
            plan_push_operation=plan_push_operation,
            recommendation_operation=recommendation_operation,
            ai_settings_provider=ai_settings_provider or (lambda: ai_settings_view(ai_env_path)),
            now_provider=now_provider,
            plan_provider=plan_provider,
            registry_provider=registry_provider,
        )
    )

    return app


app = create_app()
