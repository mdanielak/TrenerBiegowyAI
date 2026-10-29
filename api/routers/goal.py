# -*- coding: utf-8 -*-
"""Strona celu długoterminowego."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api.views.goal import _goal_view
from services.goal import GoalReport

_ERRORS = {
    "strategy_missing": (404, "Nie masz jeszcze strategii długoterminowej.",
                         "strategy"),
    "snapshot_missing": (404, "Brakuje lokalnego snapshotu danych.", "python -m trainer sync"),
    "snapshot_invalid": (503, "Lokalny snapshot danych jest niepoprawny.", "python -m trainer sync"),
}


def get_goal_router(*, goal_report_provider: Callable[[], GoalReport], templates: Jinja2Templates, profile_provider: Callable[[], dict] = dict) -> APIRouter:
    router = APIRouter()

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
            return templates.TemplateResponse(
                request=request,
                name="goal.html",
                context={"error_message": message, "error_hint": hint, "active_nav": "goal", "saved_goal": saved_goal},
                status_code=status_code,
                headers={"Cache-Control": "no-store"},
            )
        return templates.TemplateResponse(
            request=request,
            name="goal.html",
            context={"goal": _goal_view(report), "active_nav": "goal", "saved_goal": saved_goal,
                     "strategy_mismatch": strategy_mismatch, "wizard_done": request.query_params.get("wizard") == "done"},
            headers={"Cache-Control": "no-store"},
        )

    return router
