# -*- coding: utf-8 -*-
"""Strona celu długoterminowego."""
from __future__ import annotations

from collections.abc import Callable

from datetime import date

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from api.views.goal import _goal_view
from services.goal import GoalReport
from services.strategy_builder import build_strategy_markdown, save_strategy

_ERRORS = {
    # Brak strategii to zwykły stan (strategia jest opcjonalna), a nie błąd strony.
    "strategy_missing": (200, "Nie masz jeszcze strategii długoterminowej.",
                         "strategy"),
    "snapshot_missing": (404, "Nie ma jeszcze danych z zegarka.", "sync"),
    "snapshot_invalid": (503, "Zapisane dane z zegarka są uszkodzone i trzeba je pobrać ponownie.", "sync"),
}


def get_goal_router(*, goal_report_provider: Callable[[], GoalReport], templates: Jinja2Templates,
                    profile_provider: Callable[[], dict] = dict, snapshot_provider: Callable[[], object] | None = None,
                    attach_csrf: Callable | None = None, csrf_token: Callable | None = None,
                    csrf_valid: Callable | None = None) -> APIRouter:
    router = APIRouter()

    def page(request: Request, context: dict, status_code: int = 200):
        """Strona celu z tokenem formularza „ułóż fazy”, gdy aplikacja go dostarcza."""
        token = csrf_token(request) if csrf_token is not None else ""
        strategy_notice = {"created": "Fazy przygotowań są ułożone z Twojego celu i ostatnich biegów.",
                           }.get(request.query_params.get("strategy") or "")
        response = templates.TemplateResponse(
            request=request, name="goal.html", status_code=status_code,
            context={"csrf_token": token, "can_build_strategy": csrf_valid is not None,
                     "strategy_notice": strategy_notice, **context},
            headers={"Cache-Control": "no-store"})
        return attach_csrf(response, token) if attach_csrf is not None else response

    @router.post("/goal/strategy")
    def build_strategy(request: Request, csrf_token: str = Form(default="")):
        """Ułóż fazy przygotowań z zapisanego celu; poprzednia strategia zostaje jako kopia obok."""
        if csrf_valid is None or not csrf_valid(request, csrf_token):
            return page(request, {"error_message": "Odśwież stronę i spróbuj ponownie.", "error_hint": None,
                                  "active_nav": "goal", "saved_goal": {}}, 403)
        try:
            profile = profile_provider()
        except (OSError, ValueError):
            profile = {}
        data = getattr(snapshot_provider(), "data", None) if snapshot_provider is not None else None
        try:
            save_strategy(build_strategy_markdown(profile=profile, activities=(data or {}).get("activities"),
                                                  today=date.today()))
        except ValueError as error:
            return page(request, {"error_message": str(error), "error_hint": None, "active_nav": "goal",
                                  "saved_goal": {key: profile.get(key) or "" for key in
                                                 ("target_race", "target_date", "target_time")}}, 400)
        except OSError:
            return page(request, {"error_message": "Nie można zapisać pliku strategii. Sprawdź uprawnienia do folderu aplikacji.",
                                  "error_hint": None, "active_nav": "goal", "saved_goal": {}}, 503)
        return RedirectResponse(url="/goal?strategy=created", status_code=303)

    @router.get("/goal", response_class=HTMLResponse)
    def goal_page(request: Request):
        report = goal_report_provider()
        try:
            profile = profile_provider()
        except (OSError, ValueError):
            profile = {}
        saved_goal = {key: profile.get(key) or '' for key in ('target_race', 'target_date', 'target_time')}
        strategy_mismatch = bool(
            saved_goal['target_date'] and report.phases
            and saved_goal['target_date'] != report.phases[-1].end.isoformat()
        )
        if report.status != "ok":
            status_code, message, hint = _ERRORS[report.status]
            return page(request, {"error_message": message, "error_hint": hint, "active_nav": "goal",
                                  "saved_goal": saved_goal,
                                  "wizard_done": request.query_params.get("wizard") == "done"}, status_code)
        return page(request, {"goal": _goal_view(report), "active_nav": "goal", "saved_goal": saved_goal,
                              "strategy_mismatch": strategy_mismatch,
                              "wizard_done": request.query_params.get("wizard") == "done"})

    return router
