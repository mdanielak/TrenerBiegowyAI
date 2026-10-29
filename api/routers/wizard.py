# -*- coding: utf-8 -*-
"""Kreator celu i tygodnia: cztery kroki w zwykłych formularzach, bez JavaScriptu."""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from api.views.common import _format_date
from services import wizard

_CSRF_ERROR = "Odśwież stronę i spróbuj ponownie."
_FIELDS = (["distance", "distance_other", "event_name", "event_date", "target_time", "record", "frequency"]
           + [f"{prefix}_{day}" for day in wizard.DAYS for prefix in ("day", "min", "max")])


def get_wizard_router(
    *,
    profile_provider: Callable[[], dict],
    availability_provider: Callable[[], dict],
    update_profile: Callable[..., dict],
    set_availability: Callable[..., dict],
    templates: Jinja2Templates,
    attach_csrf: Callable,
    csrf_token: Callable,
    csrf_valid: Callable,
) -> APIRouter:
    router = APIRouter()

    def profile_or_none():
        try:
            return profile_provider()
        except (FileNotFoundError, OSError, ValueError):
            return None

    def render(request, *, step, values, error=None, status_code=200):
        token = csrf_token(request)
        profile = profile_or_none()
        context = {
            "active_nav": "settings",
            "csrf_token": token,
            "step": step,
            "step_number": wizard.STEPS.index(step) + 1,
            "steps": wizard.STEPS,
            "values": values,
            "fields": _FIELDS,
            "error": error,
            "profile_missing": profile is None,
            "first_run": wizard.needs_onboarding(profile) if profile is not None else True,
            "distances": wizard.DISTANCES,
            "days": wizard.DAYS,
            "day_labels": wizard.DAY_LABELS,
            "goal_label": wizard.goal_label(values),
            "event_date_label": _format_date(values["event_date"]) if values.get("event_date") else None,
            "today": date.today().isoformat(),
        }
        return attach_csrf(
            templates.TemplateResponse(request=request, name="wizard.html", context=context,
                                       status_code=status_code, headers={"Cache-Control": "no-store"}),
            token,
        )

    @router.get("/wizard", response_class=HTMLResponse)
    def start(request: Request):
        try:
            availability = availability_provider()
        except Exception:  # noqa: BLE001 - brak preferencji to puste dni
            availability = {}
        return render(request, step="goal", values=wizard.prefill(profile_or_none() or {}, availability))

    @router.post("/wizard", response_class=HTMLResponse)
    async def advance(request: Request):
        form = await request.form()
        values = {name: str(form.get(name) or "") for name in _FIELDS}
        step = form.get("step") if form.get("step") in wizard.STEPS else "goal"
        action = form.get("action")
        if not csrf_valid(request, str(form.get("csrf_token") or "")):
            return render(request, step=step, values=values, error=_CSRF_ERROR, status_code=403)

        if action == "skip":
            if profile_or_none() is not None:
                update_profile(onboarding_skipped_at=datetime.now().replace(microsecond=0).isoformat())
            return RedirectResponse(url="/", status_code=303)

        index = wizard.STEPS.index(step)
        if action == "back":
            return render(request, step=wizard.STEPS[max(index - 1, 0)], values=values)

        try:
            if action == "save":
                for each in wizard.STEPS:
                    values.update(wizard.validate_step(each, values, today=date.today()))
            else:
                values.update(wizard.validate_step(step, values, today=date.today()))
        except ValueError as error:
            failed = step if action != "save" else next(
                (each for each in wizard.STEPS if _fails(each, values)), step)
            return render(request, step=failed, values=values, error=str(error), status_code=400)

        if action == "save":
            if profile_or_none() is None:
                return render(request, step="summary", values=values, status_code=409,
                              error="Najpierw połącz zegarek poleceniem python -m trainer setup, potem zapisz cel.")
            wizard.save(values, update_profile=update_profile, set_availability=set_availability)
            return RedirectResponse(url="/goal?wizard=done", status_code=303)
        return render(request, step=wizard.STEPS[min(index + 1, len(wizard.STEPS) - 1)], values=values)

    return router


def _fails(step, values) -> bool:
    try:
        wizard.validate_step(step, dict(values), today=date.today())
    except ValueError:
        return True
    return False
