# -*- coding: utf-8 -*-
"""Lokalne API i dashboard Trenera Biegowego AI."""
from __future__ import annotations

import logging
import secrets
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
from services.jobs import JobStore
from services.today import TodayReport, get_today_report
from services.week import WeekReport, get_week_report
from services.workout_reviews import load_review
from trainer.ai_settings import ENV_PATH
from trainer.logging_config import setup_logging
from trainer.profile_store import load_profile

from api.formatters import (  # Re-exported
    HealthResponse,
    ReadinessDetail,
    ReadinessResponse,
    _CSRF_COOKIE,
    _SIGNAL_META,
    _format_sync_time,
)
from api.routers.actions import get_actions_router
from api.routers.assets import get_assets_router
from api.routers.dashboard import get_dashboard_router
from api.routers.settings import get_settings_router

logger = logging.getLogger(__name__)
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


def create_app(
    *,
    report_provider: Callable[[], TodayReport] = get_today_report,
    week_report_provider: Callable[[], WeekReport] = get_week_report,
    sync_operation: Callable[[], None] = synchronize_data,
    profile_provider: Callable[[], dict] = load_profile,
    review_operation: Callable[..., dict] | None = None,
    review_loader: Callable[..., Optional[dict]] = load_review,
    job_store: JobStore | None = None,
    lock_directory=None,
    ai_env_path: Path = ENV_PATH,
    now_provider: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> FastAPI:
    """Utwórz aplikację z wstrzykiwalnym, tylko do odczytu dostawcą raportu."""
    store = job_store or JobStore(Path("local/jobs"))
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
        version="0.1.0",
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
            store=store,
            now_provider=now_provider,
            templates=_TEMPLATES,
            attach_csrf=attach_csrf,
            csrf_token=csrf_token,
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
        )
    )

    return app


app = create_app()
