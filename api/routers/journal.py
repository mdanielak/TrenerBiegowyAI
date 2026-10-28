# -*- coding: utf-8 -*-
"""Dziennik samopoczucia: formularz bez JavaScriptu i lista ostatnich dni."""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from api.views.common import _format_date
from services.journal import BACKDATE_DAYS, FEELINGS, PAIN_AREAS, add_entry, recent_entries, validate_entry

_CSRF_ERROR = "Odśwież stronę i spróbuj ponownie."


def get_journal_router(
    *,
    journal_path: Path,
    templates: Jinja2Templates,
    attach_csrf: Callable,
    csrf_token: Callable,
    csrf_valid: Callable,
) -> APIRouter:
    router = APIRouter()

    def page(request: Request, *, error=None, form=None, status_code=200):
        token = csrf_token(request)
        today = date.today()
        entries = recent_entries(today=today, path=journal_path)
        today_entry = next((entry for entry in entries if entry["date"] == today.isoformat()), None)
        context = {
            "active_nav": "journal",
            "csrf_token": token,
            "error_message": error,
            "saved": request.method == "GET" and request.query_params.get("saved") == "1",
            "today": today.isoformat(),
            "earliest": (today - timedelta(days=BACKDATE_DAYS)).isoformat(),
            "feelings": FEELINGS,
            "pain_areas": PAIN_AREAS,
            "form": form or today_entry or {"date": today.isoformat(), "feeling": "good", "pain": []},
            "entries": [dict(entry, date_label=_format_date(entry["date"]),
                             feeling_label=FEELINGS.get(entry.get("feeling"), "—"),
                             pain_labels=[PAIN_AREAS.get(area, area) for area in entry.get("pain") or []])
                        for entry in entries],
        }
        return attach_csrf(
            templates.TemplateResponse(request=request, name="journal.html", context=context,
                                       status_code=status_code, headers={"Cache-Control": "no-store"}),
            token,
        )

    @router.get("/journal", response_class=HTMLResponse)
    def journal(request: Request):
        return page(request)

    @router.post("/journal", response_class=HTMLResponse)
    def save_journal(
        request: Request,
        csrf_token: str = Form(default=""),
        day: str = Form(default="", alias="date"),
        feeling: str = Form(default=""),
        rpe: str = Form(default=""),
        pain: list[str] = Form(default=[]),
        pain_note: str = Form(default=""),
        note: str = Form(default=""),
    ):
        form = {"date": day, "feeling": feeling, "rpe": rpe, "pain": pain, "pain_note": pain_note, "note": note}
        if not csrf_valid(request, csrf_token):
            return page(request, error=_CSRF_ERROR, form=form, status_code=403)
        try:
            entry = validate_entry(day=day, feeling=feeling, rpe=rpe, pain_areas=pain,
                                   pain_note=pain_note, note=note, today=date.today())
        except ValueError as error:
            return page(request, error=str(error), form=form, status_code=400)
        add_entry(entry, path=journal_path)
        return RedirectResponse(url="/journal?saved=1", status_code=303)

    return router
