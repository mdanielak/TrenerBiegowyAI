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
from services.ai_status import ai_status_view, load_status, record_test
from services.locking import LockBusyError, acquire_lock
from trainer.ai_settings import (
    read_ai_settings,
    resolve_test_key,
    save_ai_settings,
    validate_ai_settings,
)
from api.views.profile import (
    _PROFILE_GOAL_FIELDS,
    _PROFILE_HEART_FIELDS,
    _PROFILE_RUNNER_FIELDS,
    _hr_zone_rows,
    _profile_rows,
)

logger = logging.getLogger(__name__)


# Gotowe ustawienia dla samouczka „Jak podłączyć AI”: tylko adres i model, nigdy klucz.
AI_PRESETS = {
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "model": "gemini-3.8-flash"},
    # Alias „latest” wskazuje najnowszy DeepSeek Flash, więc nazwa się nie zestarzeje.
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "~deepseek/deepseek-flash-latest"},
    "ollama": {"base_url": "http://localhost:11434/v1", "model": "llama3.1"},
}


def get_settings_router(
    *,
    profile_provider: Callable[[], dict],
    ai_env_path: Path,
    lock_directory: Path | None,
    templates: Jinja2Templates,
    attach_csrf: Callable,
    csrf_token: Callable,
    csrf_valid: Callable,
    ai_status_path=None,
    apply_settings=None,
) -> APIRouter:
    router = APIRouter()

    def _remember_test(*, ok, base_url, model, error=None):
        """Wynik testu dla plakietki AI; błąd zapisu nie psuje samego testu."""
        try:
            record_test(ok=ok, base_url=base_url, model=model, error=error, path=ai_status_path)
        except OSError:
            logger.warning("Could not store the AI connection test result")

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
            "ai_preset": request.query_params.get("preset") if request.method == "GET" else None,
            "ai_guide": request.query_params.get("guide") or request.query_params.get("preset") or "gemini",
        }
        try:
            context["ai_settings"] = read_ai_settings(ai_env_path)
            context["ai_status"] = ai_status_view(context["ai_settings"], load_status(ai_status_path))
            context["ai_check"] = request.query_params.get("check") if request.method == "GET" else None
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
        preset = AI_PRESETS.get(request.query_params.get("preset") or "")
        return ai_settings_page(request, form_values=dict(preset) if preset else None)

    @router.post("/settings/ai/check", response_class=HTMLResponse)
    def check_saved_connection(request: Request, csrf_token: str = Form(default="")):
        """Sprawdź zapisaną konfigurację jednym kliknięciem; wynik trafia do plakietki AI."""
        if not csrf_valid(request, csrf_token):
            return ai_settings_page(request, ai_error="Odśwież stronę i spróbuj ponownie.", status_code=403)
        try:
            saved = read_ai_settings(ai_env_path)
            base_url, model = validate_ai_settings(base_url=saved["base_url"] or "", model=saved["model"] or "",
                                                   api_key="", clear_key=False)
            key = resolve_test_key(ai_env_path, base_url=base_url, api_key="", clear_key=False)
            import api.main

            with acquire_lock(name="ai-connection-test", directory=lock_directory):
                try:
                    api.main.check_connection(base_url=base_url, model=model, api_key=key)
                except AIConnectionTestError as exc:
                    _remember_test(ok=False, base_url=base_url, model=model, error=str(exc))
                    return RedirectResponse(url="/settings/ai?check=fail#polaczenie", status_code=303)
                _remember_test(ok=True, base_url=base_url, model=model)
        except ValueError as exc:
            return ai_settings_page(request, ai_error=str(exc), status_code=400)
        except LockBusyError:
            return ai_settings_page(request, ai_error="Sprawdzanie już trwa. Poczekaj na wynik.", status_code=409)
        except (OSError, UnicodeError):
            return ai_settings_page(request, ai_error="Nie można odczytać konfiguracji.", status_code=503)
        return RedirectResponse(url="/settings/ai?check=ok#polaczenie", status_code=303)

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
                try:
                    api.main.check_connection(base_url=base_url, model=model, api_key=key)
                except AIConnectionTestError as exc:
                    _remember_test(ok=False, base_url=base_url, model=model, error=str(exc))
                    raise
                _remember_test(ok=True, base_url=base_url, model=model)
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
            if apply_settings is not None:
                apply_settings(ai_env_path)
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
