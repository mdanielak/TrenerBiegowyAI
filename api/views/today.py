# -*- coding: utf-8 -*-
"""Widok strony głównej: pierścień i wykres gotowości, sygnały, trening dnia, rekomendacja."""
from __future__ import annotations

import logging
import math
from datetime import date
from collections.abc import Callable
from typing import NoReturn, Optional, cast

from fastapi import HTTPException

from api.views.plan import _kind_icon
from services.workout_steps import workout_steps
from services.journal import PAIN_AREAS
from api.views.common import (
    _format_date,
    _format_number,
    _HRV_STATUSES,
    _READINESS_LABELS,
    _SIGNAL_META,
    _SIGNAL_STATE_LABELS,
    _WEEKDAYS_SHORT,
)
from services.plan_files import week_bounds
from services.today import TodayReport
from services.workout_scoring import planned_duration_min, score_execution

logger = logging.getLogger(__name__)

_SUGGESTIONS = {
    "follow_plan": "realizuj zaplanowany trening spokojnie",
    "rest": "postaw na odpoczynek lub bardzo lekki ruch",
    "medical_rest": "odpoczynek i rekonwalescencja",
}
_SIGNAL_STATE_CLASSES = {"OK": "ok", "WARN": "warn", "FAIL": "bad", "UNKNOWN": "none"}
_SIGNAL_ORDER = ("Sleep", "HRV", "RHR", "Stress")
_TREND_LABELS = {
    "up": "wyżej niż wczoraj",
    "down": "niżej niż wczoraj",
    "flat": "tak samo jak wczoraj",
}
_RING_RADIUS = 66
_RING_STROKE = 13
_RING_SIZE = 160
_CHART_WIDTH = 640
_CHART_HEIGHT = 170
_CHART_PAD_LEFT = 30
_CHART_PAD_RIGHT = 14
_CHART_PAD_TOP = 14
_CHART_PAD_BOTTOM = 28
_MATCH_NOTES = {
    "heuristic": "Wykonanie dopasowano po czasie i dystansie, bez pewnego identyfikatora.",
    "ambiguous": "Do tego treningu pasuje więcej niż jedna aktywność.",
}
_SCORE_ROWS = (
    ("zgodnosc_z_planem", "Zgodność z planem", "Jak blisko planu był czas i tętno."),
    ("dopasowanie_do_formy", "Dopasowanie do formy", "Czy intensywność pasowała do gotowości tego dnia."),
)
_SCORE_CONFIDENCE_LABELS = {"wysoka": "wysoka", "srednia": "średnia", "niska": "niska"}


def _ring_geometry(score, max_score) -> dict:
    """Policz wymiary pierścienia gotowości po stronie serwera (bez kodu w przeglądarce)."""
    circumference = 2 * math.pi * _RING_RADIUS
    fraction = 0.0
    if max_score:
        fraction = max(0.0, min(1.0, float(score) / float(max_score)))
    return {
        "size": _RING_SIZE,
        "center": _RING_SIZE / 2,
        "radius": _RING_RADIUS,
        "stroke": _RING_STROKE,
        "circumference": round(circumference, 2),
        "offset": round(circumference * (1.0 - fraction), 2),
    }


def _trend_view(trend) -> dict | None:
    """Przełóż trend dobowy na opis dla widoku. Kolor zawsze z towarzyszącym tekstem."""
    if not trend:
        return None
    direction = trend.get("direction")
    if direction is None:
        return None
    favorable = trend.get("favorable")
    return {
        "direction": direction,
        "label": _TREND_LABELS.get(direction, ""),
        "previous": trend.get("previous"),
        "tone": "flat" if favorable is None else ("favorable" if favorable else "unfavorable"),
    }


def _signal_cards(report) -> list:
    """Zbuduj kafelki sygnałów z tej samej oceny, która wyznaczyła wynik gotowości."""
    readiness_data = cast(dict, report.readiness) or {}
    details = {item["metric"]: item for item in readiness_data.get("details", [])}
    signals = report.signals or {}
    trends = getattr(report, "trends", None) or {}
    value_keys = {"Sleep": "sleep_score", "RHR": "rhr", "Stress": "stress_avg"}

    cards = []
    for metric in _SIGNAL_ORDER:
        meta = _SIGNAL_META[metric]
        status = details.get(metric, {}).get("status", "UNKNOWN")
        if metric == "HRV":
            raw = signals.get("hrv_status")
            value = _HRV_STATUSES.get(raw, raw) if raw is not None else None
        else:
            value = signals.get(value_keys[metric])
        trend_key = meta["trend_key"]
        cards.append({
            "label": meta["label"],
            "unit": meta["unit"],
            "icon": meta["icon"],
            "asset": meta["asset"],
            "value": value,
            "state_class": _SIGNAL_STATE_CLASSES.get(status, "none"),
            "state_label": _SIGNAL_STATE_LABELS.get(status, "brak danych"),
            "trend": _trend_view(trends.get(trend_key)) if trend_key else None,
        })
    return cards


def _readiness_chart(days) -> dict | None:
    """Policz geometrię wykresu gotowości tygodniowej. Całość powstaje na serwerze."""
    inner_width = _CHART_WIDTH - _CHART_PAD_LEFT - _CHART_PAD_RIGHT
    inner_height = _CHART_HEIGHT - _CHART_PAD_TOP - _CHART_PAD_BOTTOM
    baseline = _CHART_PAD_TOP + inner_height

    max_score = 10.0
    for day in days:
        data = day.readiness
        if data and data.get("max_score"):
            max_score = float(data["max_score"])
            break

    steps = max(len(days) - 1, 1)
    points = []
    for index, day in enumerate(days):
        data = day.readiness or {}
        score = data.get("score")
        point = {
            "x": round(_CHART_PAD_LEFT + inner_width * index / steps, 2),
            "label": _WEEKDAYS_SHORT[day.weekday_index],
            "score": score,
            "level": data.get("level"),
            "is_today": day.temporal_state == "today",
            "y": None,
        }
        if score is not None:
            fraction = max(0.0, min(1.0, float(score) / max_score)) if max_score else 0.0
            point["y"] = round(_CHART_PAD_TOP + (1.0 - fraction) * inner_height, 2)
        points.append(point)

    plotted = [point for point in points if point["y"] is not None]
    if not plotted:
        return None

    gridlines = [
        {
            "y": round(_CHART_PAD_TOP + (1.0 - value / max_score) * inner_height, 2) if max_score else baseline,
            "label": round(value) if float(value).is_integer() else round(value, 1),
        }
        for value in (0.0, max_score / 2, max_score)
    ]

    segments, segment = [], []
    for point in points:
        if point["y"] is None:
            if segment:
                segments.append(segment)
                segment = []
        else:
            segment.append(point)
    if segment:
        segments.append(segment)
    lines = [" ".join(f"{point['x']},{point['y']}" for point in part)
             for part in segments if len(part) > 1]
    areas = [f"M {part[0]['x']},{baseline} "
             + " ".join(f"L {point['x']},{point['y']}" for point in part)
             + f" L {part[-1]['x']},{baseline} Z"
             for part in segments if len(part) > 1]

    return {
        "width": _CHART_WIDTH,
        "height": _CHART_HEIGHT,
        "baseline": round(baseline, 2),
        "label_y": round(baseline + 18, 2),
        "axis_x": _CHART_PAD_LEFT - 8,
        "grid_start": _CHART_PAD_LEFT,
        "grid_end": _CHART_WIDTH - _CHART_PAD_RIGHT,
        "points": points,
        "lines": lines,
        "areas": areas,
        "max_score": max_score,
        "gridlines": gridlines,
        "measured_days": len(plotted),
    }


def _report_error(report: TodayReport) -> tuple[int, str, str]:
    """Zwróć publiczną, jednolitą odpowiedź dla niedostępnych danych."""
    if report.status == "profile_missing":
        return 404, "Brakuje lokalnego profilu.", "python -m trainer setup"
    if report.status == "snapshot_missing":
        return 404, "Brakuje lokalnego snapshotu danych.", "python -m trainer sync"
    if report.status == "snapshot_invalid":
        logger.error("Local data snapshot is invalid")
        return 503, "Lokalny snapshot danych jest niepoprawny.", "python -m trainer sync"
    raise ValueError(f"Nieznany stan raportu: {report.status}")


def _raise_report_error(report: TodayReport) -> NoReturn:
    status_code, message, command = _report_error(report)
    raise HTTPException(status_code=status_code, detail=f"{message} Uruchom: {command}")


def _coach_notes(report, name) -> Optional[dict]:
    """Opis i uwagi z planu AI, gdy trening na zegarku to ten sam trening z planu."""
    plan_workout = getattr(report, "plan_workout", None) or {}
    if not plan_workout or plan_workout.get("name") != name:
        return None
    if not (plan_workout.get("description") or plan_workout.get("notes")):
        return None
    return {"description": plan_workout.get("description"), "notes": plan_workout.get("notes"),
            "distance_km": plan_workout.get("distance_km")}


def _pause_view(report: TodayReport) -> Optional[dict]:
    """Przerwa trwająca dziś: wygrywa z treningiem, nawet gdy plan ułożono przed jej dodaniem."""
    pause = getattr(report, "active_pause", None)
    if not isinstance(pause, dict):
        return None
    start, end = str(pause.get("start_date", "")), str(pause.get("end_date", ""))
    try:
        monday, _ = week_bounds(date.fromisoformat(report.date))
    except (TypeError, ValueError):
        monday = None
    return {
        "reason": pause.get("reason") or "Przerwa",
        "dates": f"{_format_date(start)} – {_format_date(end)}" if start and end else "",
        "week": monday.isoformat() if monday else None,
    }


def _workout_status(execution: dict) -> tuple[str, str]:
    """Opisz wykonanie treningu słowem i klasą koloru."""
    if execution.get("happened") is True:
        return "Znaleziono wykonanie", "ok" if execution.get("certain") is True else "warn"
    if execution.get("match_method") == "ambiguous":
        return "Nie można jednoznacznie porównać", "warn"
    # Strona główna dotyczy dnia, który jeszcze trwa: brak aktywności to „do zrobienia”, nie zaniedbanie.
    return "Do zrobienia", "neutral"


def _workout_section(report: TodayReport, profile_provider: Callable[[], dict],
                     review_loader: Callable[..., Optional[dict]]) -> Optional[dict]:
    """Zbierz dane sekcji treningu: plan, wykonanie, lokalne punkty i komentarz."""
    execution = getattr(report, "execution", None)
    if execution is None:
        return None

    planned = report.planned or {}
    spec = planned.get("spec") or {}
    try:
        profile = profile_provider()
    except (FileNotFoundError, OSError, ValueError):
        profile = {}

    score = None
    if profile.get("hr_max") is not None:
        score = score_execution(
            planned=planned,
            execution=execution,
            readiness_score=(report.readiness or {}).get("score"),
            hr_zone_floors=profile.get("hr_zone_floors") or {},
            hr_max=profile.get("hr_max"),
        )

    review_key = execution.get("review_key")
    try:
        review = review_loader(review_key=review_key) if review_key else None
    except OSError:
        review = None

    band = (score or {}).get("zakres_docelowy")
    zone = (score or {}).get("strefa_docelowa")
    status_label, status_class = _workout_status(execution)
    paused = _pause_view(report) is not None and not execution.get("happened")
    if paused:
        status_label, status_class = "Przerwa", "warn"
    score_rows = [
        {"label": label, "hint": hint, "value": score[key]}
        for key, label, hint in _SCORE_ROWS if score is not None
    ]
    return {
        "execution": execution,
        "name": planned.get("name") or "Trening",
        "kind": spec.get("kind"),
        "icon": _kind_icon(spec.get("kind")),
        "steps": workout_steps(spec, profile.get("hr_zone_floors") or {}),
        "coach": _coach_notes(report, planned.get("name")),
        "others": list(getattr(report, "other_planned", None) or []),
        "planned_duration": planned_duration_min(spec),
        "target": f"Z{zone} ({band[0]}–{band[1]} bpm)" if zone is not None and band else None,
        "status_label": status_label,
        "status_class": status_class,
        "paused": paused,
        "match_note": _MATCH_NOTES.get(execution.get("match_method")),
        "planned_count": execution.get("planned_count"),
        "score": score,
        "score_rows": score_rows,
        "confidence_label": _SCORE_CONFIDENCE_LABELS.get(score["pewnosc"]) if score else None,
        "comment": (review or {}).get("comment"),
        "review_key": review_key,
    }


def _health_alert(report, journal_entries=()) -> Optional[dict]:
    """Baner na górze strony głównej, gdy organizm wyraźnie potrzebuje odpoczynku.

    Tylko twarde sygnały: gotowość „dziś lepiej odpuść”, alert HRV z kilku dni albo ból
    zgłoszony w dzienniku dziś lub wczoraj. Każdy powód jest zdaniem, nie samym kolorem.
    """
    reasons = []
    severe = False
    readiness = report.readiness or {}
    if readiness.get("level") == "not_ready":
        severe = True
        score = readiness.get("score")
        reasons.append(f"Gotowość {_format_number(score)} z {_format_number(readiness.get('max_score'))} — "
                       "organizm jeszcze się regeneruje." if score is not None else
                       "Ocena gotowości: dziś lepiej odpuścić trening.")
    alert = getattr(report, "hrv_alert", None)
    if alert:
        reasons.append(f"HRV niskie lub niezrównoważone od {alert.get('days')} dni z rzędu.")
    for entry in journal_entries or ():
        if entry.get("pain"):
            severe = True
            areas = ", ".join(PAIN_AREAS.get(area, area) for area in entry["pain"])
            reasons.append(f"W dzienniku zapisano ból: {areas} ({_format_date(entry['date'])}).")
            break
    if not reasons:
        return None
    return {
        "tone": "bad" if severe else "warn",
        "title": "Dziś lepiej odpuścić trening" if severe else "Uważaj dziś na intensywność",
        "reasons": reasons,
        "advice": ("Postaw na odpoczynek albo bardzo lekki ruch. Przy narastającym bólu lub nowych objawach "
                   "skonsultuj się ze specjalistą." if severe else
                   "Zostań przy spokojnym biegu w strefie Z1–Z2 i nie dokładaj akcentu."),
    }


def _recommendation_view(recommendation) -> Optional[dict]:
    """Zbuduj widok rekomendacji dziennej z odpowiedzi AI."""
    if not recommendation:
        return None
    readiness = recommendation.get("readiness")
    return {
        "readiness_label": _READINESS_LABELS.get(readiness, readiness),
        "recommendation": recommendation.get("recommendation"),
        "planned_workout": recommendation.get("planned_workout"),
        "adjustment_needed": recommendation.get("adjustment_needed"),
        "reasoning_summary": recommendation.get("reasoning_summary"),
        "warnings": list(recommendation.get("warnings") or []),
        "message": recommendation.get("message"),
    }
