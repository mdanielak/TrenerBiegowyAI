# -*- coding: utf-8 -*-
"""Połączenie z Garminem w przeglądarce: e-mail i hasło, kod MFA, import profilu."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services import garmin_setup
from trainer import garmin_auth

_CSRF_ERROR = "Odśwież stronę i spróbuj ponownie."


def get_garmin_setup_router(
    *,
    has_token: Callable[[], bool],
    profile_provider: Callable[[], dict],
    snapshot_provider: Callable[[], object],
    env_path=None,
    templates: Jinja2Templates,
    attach_csrf: Callable,
    csrf_token: Callable,
    csrf_valid: Callable,
) -> APIRouter:
    router = APIRouter()

    def render(request, *, stage, error=None, email="", pending="", status_code=200):
        from services.data_extract import SnapshotStatus

        token = csrf_token(request)
        try:
            profile = profile_provider() or {}
        except (FileNotFoundError, OSError, ValueError):
            profile = {}
        try:
            snapshot_missing = snapshot_provider().status is SnapshotStatus.MISSING
        except Exception:  # noqa: BLE001
            snapshot_missing = True
        context = {
            "active_nav": "settings",
            "csrf_token": token,
            "stage": stage,
            "error": error,
            "email": email,
            "pending": pending,
            "profile": profile,
            "snapshot_missing": snapshot_missing,
            "confirm_disconnect": request.query_params.get("disconnect") == "confirm",
            "removed": [item for item in (request.query_params.get("removed") or "").split("|") if item],
            "token_location": str(garmin_auth.token_path()),
        }
        return attach_csrf(
            templates.TemplateResponse(request=request, name="garmin_setup.html", context=context,
                                       status_code=status_code, headers={"Cache-Control": "no-store"}),
            token,
        )

    @router.get("/setup/garmin", response_class=HTMLResponse)
    def page(request: Request):
        connected = has_token() and request.query_params.get("change") != "1"
        return render(request, stage="connected" if connected else "login")

    @router.post("/setup/garmin/disconnect", response_class=HTMLResponse)
    def disconnect(request: Request, csrf_token: str = Form(default="")):
        """Usuń token i dane logowania; dane treningowe zostają na komputerze."""
        if not csrf_valid(request, csrf_token):
            return render(request, stage="connected", error=_CSRF_ERROR, status_code=403)
        try:
            removed = garmin_auth.disconnect(env_path=env_path)
        except OSError:
            return render(request, stage="connected", status_code=500,
                          error="Nie udało się usunąć danych logowania. Zamknij inne okna aplikacji i spróbuj ponownie.")
        from urllib.parse import quote

        return RedirectResponse(url="/setup/garmin?disconnected=1&removed=" + quote("|".join(removed)),
                                status_code=303)

    @router.post("/setup/garmin/profile", response_class=HTMLResponse)
    def refresh_profile(request: Request, csrf_token: str = Form(default="")):
        """Pobierz profil i strefy tętna z zapisanego tokenu, bez ponownego logowania."""
        if not csrf_valid(request, csrf_token):
            return render(request, stage="connected", error=_CSRF_ERROR, status_code=403)
        try:
            garmin_setup.import_profile(email=None)
        except Exception:  # noqa: BLE001 - komunikat bez szczegółów integracji
            return RedirectResponse(url="/setup/garmin?profile=failed", status_code=303)
        return RedirectResponse(url="/setup/garmin?profile=refreshed", status_code=303)

    @router.post("/setup/garmin", response_class=HTMLResponse)
    def login(request: Request, csrf_token: str = Form(default=""), email: str = Form(default=""),
              password: str = Form(default="")):
        if not csrf_valid(request, csrf_token):
            return render(request, stage="login", email=email, error=_CSRF_ERROR, status_code=403)
        try:
            outcome, pending = garmin_setup.start_login(email, password)
        except garmin_setup.GarminSetupError as error:
            return render(request, stage="login", email=email, error=str(error), status_code=400)
        if outcome == "mfa":
            return render(request, stage="mfa", email=email, pending=pending)
        return _imported(request, email)

    @router.post("/setup/garmin/mfa", response_class=HTMLResponse)
    def mfa(request: Request, csrf_token: str = Form(default=""), pending: str = Form(default=""),
            code: str = Form(default=""), email: str = Form(default="")):
        if not csrf_valid(request, csrf_token):
            return render(request, stage="mfa", email=email, pending=pending, error=_CSRF_ERROR, status_code=403)
        try:
            account = garmin_setup.complete_mfa(pending, code)
        except garmin_setup.GarminSetupError as error:
            stage = "login" if "wygasło" in str(error) else "mfa"
            return render(request, stage=stage, email=email, pending=pending, error=str(error), status_code=400)
        return _imported(request, account)

    def _imported(request, email):
        try:
            garmin_setup.import_profile(email=email)
        except Exception:  # noqa: BLE001 - token jest zapisany; profil uzupełni się przy kolejnej próbie
            return RedirectResponse(url="/setup/garmin?profile=failed", status_code=303)
        return RedirectResponse(url="/setup/garmin?connected=1", status_code=303)

    return router
