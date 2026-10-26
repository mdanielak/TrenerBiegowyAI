# -*- coding: utf-8 -*-
"""Settings and AI configuration router."""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ai.connection_test import AIConnectionTestError
from services.locking import LockBusyError, acquire_lock
from trainer.ai_settings import (
    read_ai_settings,
    resolve_test_key,
    save_ai_settings,
    validate_ai_settings,
)
from api.formatters import (
    _PROFILE_GOAL_FIELDS,
    _PROFILE_HEART_FIELDS,
    _PROFILE_RUNNER_FIELDS,
    _hr_zone_rows,
    _profile_rows,
)

logger = logging.getLogger(__name__)


def get_settings_router(
    *,
    profile_provider: Callable[[], dict],
    ai_env_path: Path,
    lock_directory: Path | None,
    templates: Jinja2Templates,
    attach_csrf: Callable,
    csrf_token: Callable,
    csrf_valid: Callable,
) -> APIRouter:
    router = APIRouter()

    def ai_settings_page(
        request: Request,
        *,
        ai_error=None,
        status_code=200,
        form_values=None,
        test_success=False,
        key_discarded=False,
    ):
        token = csrf_token(request)
        context = {
            "active_nav": "settings",
            "csrf_token": token,
            "ai_error": ai_error,
            "ai_test_success": test_success,
            "ai_key_discarded": key_discarded,
            "ai_env_path": str(ai_env_path.resolve()),
            "ai_saved": request.method == "GET" and request.query_params.get("saved") == "1",
        }
        try:
            context["ai_settings"] = read_ai_settings(ai_env_path)
            if form_values is not None:
                context["ai_settings"].update(form_values)
        except (OSError, UnicodeError):
            context["ai_error"] = "Nie można odczytać pliku .env. Sprawdź uprawnienia i kodowanie UTF-8."
            status_code = 503
        return attach_csrf(
            templates.TemplateResponse(
                request=request,
                name="settings_ai.html",
                context=context,
                status_code=status_code,
                headers={"Cache-Control": "no-store"},
            ),
            token,
        )

    def settings_page(request: Request, *, status_code=200):
        token = csrf_token(request)
        context = {"active_nav": "settings"}
        try:
            profile = profile_provider()
        except FileNotFoundError:
            context.update(
                error_message="Nie znaleziono lokalnego profilu biegacza.",
                error_command="python -m trainer setup",
            )
            if status_code == 200:
                status_code = 404
        except Exception:
            logger.error("Could not read runner profile")
            context.update(
                error_message="Nie można odczytać lokalnego profilu biegacza.",
                error_command="python -m trainer setup",
            )
            if status_code == 200:
                status_code = 503
        else:
            context.update(
                runner_rows=_profile_rows(profile, _PROFILE_RUNNER_FIELDS),
                heart_rows=_profile_rows(profile, _PROFILE_HEART_FIELDS),
                goal_rows=_profile_rows(profile, _PROFILE_GOAL_FIELDS),
                zone_rows=_hr_zone_rows(profile),
                zones_source=profile.get("hr_zones_source") or None,
            )
        return attach_csrf(
            templates.TemplateResponse(
                request=request,
                name="settings.html",
                context=context,
                status_code=status_code,
                headers={"Cache-Control": "no-store"},
            ),
            token,
        )

    @router.get("/settings", response_class=HTMLResponse)
    def settings(request: Request):
        return settings_page(request)

    @router.get("/settings/ai", response_class=HTMLResponse)
    def ai_settings(request: Request):
        return ai_settings_page(request)

    @router.post("/settings/ai/test", response_class=HTMLResponse)
    def test_ai_connection(
        request: Request,
        csrf_token: str = Form(default=""),
        base_url: str = Form(default=""),
        model: str = Form(default=""),
        api_key: str = Form(default=""),
        export_enabled: str = Form(default=""),
        clear_key: str = Form(default=""),
    ):
        if not csrf_valid(request, csrf_token):
            return ai_settings_page(
                request, ai_error="Odśwież stronę i spróbuj ponownie.", status_code=403
            )
        form_values = {
            "base_url": base_url,
            "model": model,
            "export_enabled": export_enabled == "true",
            "clear_key": clear_key == "true",
        }
        result = {"form_values": form_values, "key_discarded": bool(api_key)}
        try:
            base_url, model = validate_ai_settings(
                base_url=base_url, model=model, api_key=api_key, clear_key=clear_key == "true"
            )
            key = resolve_test_key(
                ai_env_path, base_url=base_url, api_key=api_key, clear_key=clear_key == "true"
            )
            # Dynamic lookup from api.main ensures test monkeypatches apply
            import api.main

            with acquire_lock(name="ai-connection-test", directory=lock_directory):
                api.main.check_connection(base_url=base_url, model=model, api_key=key)
        except ValueError as exc:
            return ai_settings_page(request, ai_error=str(exc), status_code=400, **result)
        except AIConnectionTestError as exc:
            return ai_settings_page(request, ai_error=str(exc), status_code=502, **result)
        except LockBusyError:
            return ai_settings_page(
                request, ai_error="Test już trwa. Poczekaj na wynik.", status_code=409, **result
            )
        except (OSError, UnicodeError):
            return ai_settings_page(
                request,
                ai_error="Nie można odczytać konfiguracji lub utworzyć blokady testu.",
                status_code=503,
                **result,
            )
        return ai_settings_page(request, test_success=True, **result)

    @router.post("/settings/ai", response_class=HTMLResponse)
    def update_ai_settings(
        request: Request,
        csrf_token: str = Form(default=""),
        base_url: str = Form(default=""),
        model: str = Form(default=""),
        api_key: str = Form(default=""),
        export_enabled: str = Form(default=""),
        clear_key: str = Form(default=""),
    ):
        if not csrf_valid(request, csrf_token):
            return ai_settings_page(
                request, ai_error="Odśwież stronę i spróbuj ponownie.", status_code=403
            )
        try:
            with acquire_lock(name="env.ai-settings", directory=ai_env_path.parent):
                save_ai_settings(
                    ai_env_path,
                    base_url=base_url,
                    model=model,
                    api_key=api_key,
                    export_enabled=export_enabled == "true",
                    clear_key=clear_key == "true",
                )
        except ValueError as exc:
            return ai_settings_page(request, ai_error=str(exc), status_code=400)
        except LockBusyError:
            return ai_settings_page(request, ai_error="Zapis już trwa. Spróbuj ponownie.", status_code=409)
        except (OSError, UnicodeError):
            return ai_settings_page(
                request,
                ai_error="Nie można zapisać pliku .env. Sprawdź uprawnienia i kodowanie UTF-8.",
                status_code=503,
            )
        return RedirectResponse(
            url="/settings/ai?saved=1", status_code=303, headers={"Cache-Control": "no-store"}
        )

    return router
