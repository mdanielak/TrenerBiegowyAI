# -*- coding: utf-8 -*-
"""Widok planu tygodniowego: dni, sumy, wykres obciążenia i trening z planu na dziś."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from api.views.common import _MONTHS_GENITIVE, _WEEKDAYS, _WEEKDAYS_SHORT, _readiness_pill

_PLAN_KIND_LABELS = {
    "easy": "Bieg łatwy",
    "recovery": "Regeneracja",
    "long": "Długi bieg",
    "tempo": "Tempo",
    "threshold": "Próg",
    "intervals": "Interwały",
    "rest": "Odpoczynek",
}
_PLAN_KIND_PILL = {
    "easy": "ok",
    "recovery": "ok",
    "long": "ok",
    "tempo": "warn",
    "threshold": "warn",
    "intervals": "warn",
    "rest": "neutral",
}
_PLAN_KIND_ICONS = {kind: f"/assets/03_activity/kind_{kind}.png"
                    for kind in ("easy", "recovery", "long", "tempo", "threshold", "intervals", "rest")}
# Rodzaje z rejestru Garmina (builder treningu) w rodzajach planu.
_REGISTRY_KINDS = {"easy_run": "easy", "easy_run_zoned": "easy", "hr_zone_run": "easy", "strides": "easy",
                   "long_run": "long", "tempo_run": "tempo", "threshold_intervals": "threshold"}


def _kind_icon(kind) -> str:
    """Ikona rodzaju treningu z planu albo z rejestru; nieznany rodzaj to bieg łatwy."""
    kind = _REGISTRY_KINDS.get(kind, kind)
    return _PLAN_KIND_ICONS.get(kind, _PLAN_KIND_ICONS["easy"])
_PLAN_QUALITY_KINDS = ("tempo", "threshold", "intervals")
_PLAN_DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_PLAN_LOAD_WIDTH = 638
_PLAN_LOAD_HEIGHT = 146
_PLAN_LOAD_BASELINE = 120
_PLAN_LOAD_BAR_WIDTH = 74
_PLAN_LOAD_GAP = 20
_PLAN_LOAD_BAR_MAX = 96


def _plan_day_index(day_key) -> int:
    """Numer dnia tygodnia z klucza planu (mon..sun)."""
    try:
        return _PLAN_DAY_KEYS.index(day_key)
    except ValueError:
        return 0


def _plan_view(plan, *, today, availability=None, readiness_by_date=None, previous_week=None) -> dict:
    """Zbuduj widok planu tygodnia: dni, sumy i etykiety rodzajów treningu."""
    if not plan:
        return {}

    today_text = today.isoformat() if hasattr(today, "isoformat") else str(today or "")
    readiness_days = readiness_by_date or {}

    days = []
    sessions = 0
    quality_sessions = 0
    long_runs = 0
    total_distance = None
    total_duration = None
    measured_days = 0

    for workout in plan.get("workouts") or []:
        kind = workout.get("type") or "rest"
        is_rest = kind == "rest"
        minutes = workout.get("duration_min")
        distance = workout.get("distance_km")
        if not is_rest:
            sessions += 1
            if kind in _PLAN_QUALITY_KINDS:
                quality_sessions += 1
            if kind == "long":
                long_runs += 1
            if minutes is not None:
                total_duration = (total_duration or 0) + int(minutes)
            if distance is not None:
                total_distance = round((total_distance or 0) + float(distance), 1)

        day_key = workout.get("day")
        index = _plan_day_index(day_key)
        slot = (availability or {}).get(day_key) or {}
        day_date = workout.get("date")
        day_text = str(day_date) if day_date else ""
        readiness = _readiness_pill(readiness_days.get(day_date))
        if readiness is not None:
            measured_days += 1
        days.append({
            "date": day_date,
            "day": day_key,
            "weekday": _WEEKDAYS[index],
            "weekday_short": _WEEKDAYS_SHORT[index],
            "kind": kind,
            "kind_label": _PLAN_KIND_LABELS.get(kind, kind),
            "kind_pill": _PLAN_KIND_PILL.get(kind, "neutral"),
            "icon": _PLAN_KIND_ICONS.get(kind),
            "name": workout.get("name"),
            "description": workout.get("description"),
            "duration_min": minutes,
            "distance_km": distance,
            "hr_zone": workout.get("hr_zone"),
            "hr_target": workout.get("hr_target"),
            "pace_target": workout.get("pace_target"),
            "notes": workout.get("notes"),
            "is_rest": is_rest,
            "is_today": day_text == today_text,
            "is_past": bool(day_text) and day_text < today_text,
            "readiness": readiness,
            "garmin_upload": bool(workout.get("garmin_upload")),
            "garmin_workout_id": workout.get("garmin_workout_id"),
            "available": bool(slot.get("available")),
            "min_minutes": slot.get("min_minutes"),
            "max_minutes": slot.get("max_minutes"),
        })

    return {
        "start_date": plan.get("start_date"),
        "end_date": plan.get("end_date"),
        "focus": plan.get("focus"),
        "summary": plan.get("summary"),
        "generated_at": plan.get("generated_at"),
        "days": days,
        "measured_days": measured_days,
        "previous": previous_week or None,
        "totals": {
            "sessions": sessions,
            "distance_km": total_distance,
            "duration_min": total_duration,
            "quality_sessions": quality_sessions,
            "long_runs": long_runs,
        },
    }


def _plan_load_chart(days) -> dict | None:
    """Geometria słupków zaplanowanego czasu: minuty na dzień."""
    minutes = []
    for day in days or []:
        try:
            minutes.append(int(day.get("duration_min") or 0))
        except (TypeError, ValueError):
            minutes.append(0)

    peak = max(minutes) if minutes else 0
    if peak <= 0:
        return None

    bars = []
    for index, day in enumerate(days or []):
        value = minutes[index]
        height = round(_PLAN_LOAD_BAR_MAX * value / peak) if value else 0
        bars.append({
            "x": index * (_PLAN_LOAD_BAR_WIDTH + _PLAN_LOAD_GAP),
            "width": _PLAN_LOAD_BAR_WIDTH,
            "height": height,
            "y": _PLAN_LOAD_BASELINE - height,
            "label": day.get("weekday_short"),
            "minutes": value,
            "is_rest": bool(day.get("is_rest")),
        })

    return {
        "width": _PLAN_LOAD_WIDTH,
        "height": _PLAN_LOAD_HEIGHT,
        "baseline": _PLAN_LOAD_BASELINE,
        "label_y": _PLAN_LOAD_BASELINE + 18,
        "bars": bars,
    }


def _format_generated_at(value, now: datetime) -> str | None:
    """Pokaż czas ułożenia planu po polsku, np. '26 października 2026 o 15:24'."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=getattr(now, "tzinfo", None) or timezone.utc)
    local = parsed.astimezone()
    return f"{local.day} {_MONTHS_GENITIVE[local.month - 1]} {local.year} o {local:%H:%M}"


def _plan_workout_view(plan_workout, floors=None) -> Optional[dict]:
    """Płaski widok treningu z planu AI na dziś, z krokami jak na zegarku."""
    from services.workout_steps import spec_from_plan, workout_steps

    if not plan_workout:
        return None
    kind = plan_workout.get("type") or "rest"
    return {
        "name": plan_workout.get("name"),
        "kind_label": _PLAN_KIND_LABELS.get(kind, kind),
        "duration_min": plan_workout.get("duration_min"),
        "distance_km": plan_workout.get("distance_km"),
        "hr_zone": plan_workout.get("hr_zone"),
        "pace_target": plan_workout.get("pace_target"),
        "notes": plan_workout.get("notes"),
        "garmin_upload": bool(plan_workout.get("garmin_upload")),
        "is_rest": kind == "rest",
        "icon": _kind_icon(kind),
        "steps": workout_steps(spec_from_plan(plan_workout), floors) if kind != "rest" else [],
        "description": plan_workout.get("description"),
    }


_CONFLICT_COPY = {
    "plan": {
        "title": "Na ten tydzień jest już plan",
        "action": "/actions/plan",
        "buttons": (("overwrite", "Nadpisz plan", ""), ("add", "Zapisz jako drugą wersję", "btn-secondary"),
                    ("cancel", "Anuluj", "btn-secondary")),
        "note": ("Nadpisany plan trafi do archiwum, nie zostanie usunięty. Treningi już wysłane zostaną "
                 "na zegarku; przy wysyłce nowego planu zapytam, czy je zastąpić."),
    },
    "push": {
        "title": "Na te dni są już treningi na zegarku",
        "action": "/actions/plan/push",
        "buttons": (("overwrite", "Zastąp na zegarku", ""), ("add", "Dodaj obok", "btn-secondary"),
                    ("cancel", "Anuluj", "btn-secondary")),
        "note": ("Zastąpione treningi zostaną usunięte z Garmina, ale zostają w lokalnym rejestrze "
                 "i da się je odtworzyć. Treningi dodane ręcznie w Garmin Connect nie są tu widoczne."),
    },
}


def _conflict_view(kind, days) -> dict | None:
    """Panel potwierdzenia: lista kolidujących dni i trzy decyzje."""
    copy = _CONFLICT_COPY[kind]
    rows = []
    for day in days or []:
        if kind == "plan":
            detail = f"{day['name']}" + (f", {day['minutes']} min" if day.get("minutes") else "")
            rows.append({"label": day["label"], "detail": detail, "on_watch": day.get("on_watch")})
        else:
            existing = ", ".join(item["name"] for item in day["existing"])
            rows.append({"label": day["label"], "detail": f"na zegarku: {existing}; nowy: {day['name']}",
                         "on_watch": True})
    return {"kind": kind, "title": copy["title"], "action": copy["action"], "buttons": copy["buttons"],
            "note": copy["note"], "rows": rows}


def _variant_views(current, variants) -> list[dict]:
    """Druga wersja planu obok obecnej, dzień po dniu."""
    current_by_date = {w.get("date"): w for w in (current or {}).get("workouts") or []}
    views = []
    for name, plan in variants or []:
        rows = []
        for workout in plan.get("workouts") or []:
            before = current_by_date.get(workout.get("date")) or {}
            rows.append({
                "weekday": _WEEKDAYS_SHORT[_plan_day_index(workout.get("day"))],
                "current": _workout_label(before) if before else "—",
                "variant": _workout_label(workout),
                "changed": _workout_label(before) != _workout_label(workout),
            })
        views.append({"name": name, "focus": plan.get("focus"), "generated_at": plan.get("generated_at"),
                      "rows": rows})
    return views


def _workout_label(workout) -> str:
    kind = workout.get("type") or "rest"
    if kind == "rest":
        return "Odpoczynek"
    minutes = workout.get("duration_min")
    return f"{workout.get('name') or _PLAN_KIND_LABELS.get(kind, kind)}" + (f" · {minutes} min" if minutes else "")
