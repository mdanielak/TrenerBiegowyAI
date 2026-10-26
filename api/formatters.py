# -*- coding: utf-8 -*-
"""Formatters and presentation models for Trener Biegowy AI web UI."""
from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from typing import List, NoReturn, Optional, cast

from fastapi import HTTPException
from pydantic import BaseModel

from services.today import TodayReport
from services.jobs import JobStore
from services.workout_scoring import planned_duration_min, score_execution

logger = logging.getLogger(__name__)

_WEEKDAYS = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")
_SUGGESTIONS = {
    "follow_plan": "realizuj zaplanowany trening spokojnie",
    "rest": "postaw na odpoczynek lub bardzo lekki ruch",
}
_READINESS_LABELS = {
    "ready": "gotowy do treningu",
    "ready_with_reserves": "gotowy, z rezerwą",
    "not_ready": "nie jesteś gotowy do treningu",
}
_HRV_STATUSES = {
    "BALANCED": "zrównoważone",
    "UNBALANCED": "niezrównoważone",
    "LOW": "niskie",
    "POOR": "słabe",
    "UNKNOWN": "brak oceny",
}
_MONTHS_GENITIVE = (
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
)
_WEEK_STATUS_LABELS = {
    "no_plan": "Brak zapisanego treningu",
    "activity_only": "Aktywności bez zapisanego treningu",
    "planned": "Zaplanowane",
    "matched": "Znaleziono wykonanie",
    "partially_matched": "Znaleziono wykonanie części treningów",
    "no_record": "Brak wykonania w lokalnych danych",
    "uncertain": "Nie można jednoznacznie porównać",
}
_WEEK_WARNING_LABELS = {
    "snapshot_stale": "Dane o aktywnościach mogą być nieaktualne. Uruchom `python -m trainer sync`.",
    "snapshot_activities_may_be_incomplete": "Lista aktywności może być niepełna, bo obejmuje tylko 50 ostatnich treningów.",
}
_SIGNAL_STATE_CLASSES = {"OK": "ok", "WARN": "warn", "FAIL": "bad", "UNKNOWN": "none"}
_SIGNAL_STATE_LABELS = {"OK": "dobrze", "WARN": "uwaga", "FAIL": "słabo", "UNKNOWN": "brak danych"}
_SIGNAL_ORDER = ("Sleep", "HRV", "RHR", "Stress")
_SIGNAL_META = {
    "Sleep": {"label": "Sen", "unit": "/100", "icon": "moon",
              "asset": "02_health_status/sleep.png", "trend_key": "sleep_score"},
    "HRV": {"label": "Zmienność tętna", "unit": "", "icon": "pulse",
            "asset": "02_health_status/hrv.png", "trend_key": None},
    "RHR": {"label": "Tętno spoczynkowe", "unit": "bpm", "icon": "heart",
            "asset": "02_health_status/resting_hr.png", "trend_key": "rhr"},
    "Stress": {"label": "Stres", "unit": "", "icon": "bolt",
               "asset": "02_health_status/stress.png", "trend_key": "stress_avg"},
}
_TREND_LABELS = {
    "up": "wyżej niż wczoraj",
    "down": "niżej niż wczoraj",
    "flat": "tak samo jak wczoraj",
}
_RING_RADIUS = 52
_RING_STROKE = 11
_RING_SIZE = 128
_WEEKDAYS_SHORT = ("pon", "wt", "śr", "czw", "pt", "sob", "ndz")
_READINESS_PILL_CLASSES = {"ready": "ok", "ready_with_reserves": "warn", "not_ready": "bad"}
_ANALYSIS_PILL_CLASSES = {"OK": "ok", "WARN": "warn", "FAIL": "bad", "UNKNOWN": "neutral"}
_CONFIDENCE_LABELS = {"high": "wysoka", "medium": "średnia", "low": "niska", "none": "brak"}
_PROFILE_RUNNER_FIELDS = (
    ("name", "Imię", ""),
    ("age", "Wiek", "lat"),
    ("weight_kg", "Waga", "kg"),
    ("height_cm", "Wzrost", "cm"),
    ("device", "Zegarek", ""),
)
_PROFILE_HEART_FIELDS = (
    ("hr_max", "Tętno maksymalne", "bpm"),
    ("hr_rest", "Tętno spoczynkowe", "bpm"),
    ("lactate_threshold_hr", "Tętno progowe (LTHR)", "bpm"),
    ("vo2max_running", "VO2max (bieg)", ""),
)
_PROFILE_GOAL_FIELDS = (
    ("target_race", "Zawody docelowe", ""),
    ("target_date", "Data celu", ""),
    ("target_time", "Czas docelowy", ""),
    ("target_hm", "Cel na półmaraton", ""),
    ("current_hm_record", "Obecny rekord półmaratonu", ""),
    ("training_frequency", "Liczba treningów w tygodniu", ""),
)
_CHART_WIDTH = 640
_CHART_HEIGHT = 170
_CHART_PAD_LEFT = 30
_CHART_PAD_RIGHT = 14
_CHART_PAD_TOP = 14
_CHART_PAD_BOTTOM = 28
SYNC_COOLDOWN = timedelta(seconds=60)
REVIEW_COOLDOWN = timedelta(seconds=30)
_CSRF_COOKIE = "trainer_csrf"


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadinessDetail(BaseModel):
    metric: str
    status: str
    message: str


class ReadinessResponse(BaseModel):
    score: float
    max_score: float
    raw_score: float
    available_max_score: float
    insufficient_data: bool
    missing_metrics: List[str]
    available_metrics: List[str]
    data_coverage: float
    confidence: str
    level: str
    rhr: Optional[float]
    hrv_status: Optional[str]
    hrv_last: Optional[float]
    hrv_baseline: Optional[str]
    sleep_score_val: Optional[float]
    sleep_total: Optional[float]
    stress: Optional[float]
    details: List[ReadinessDetail]
    warning: Optional[str] = None


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


def _format_minutes(value) -> str | None:
    """Zamień minuty na czas czytelny dla człowieka."""
    if value is None:
        return None
    total = int(round(float(value)))
    hours, minutes = divmod(total, 60)
    if hours and minutes:
        return f"{hours} h {minutes} min"
    if hours:
        return f"{hours} h"
    return f"{minutes} min"


def _readiness_pill(day_readiness) -> dict | None:
    """Opisz gotowość danego dnia tekstem i wariantem koloru."""
    if not day_readiness:
        return None
    level = day_readiness.get("level")
    return {
        "level": level,
        "label": _READINESS_LABELS.get(level, level),
        "variant": _READINESS_PILL_CLASSES.get(level, "neutral"),
        "score": day_readiness.get("score"),
        "max_score": day_readiness.get("max_score"),
    }


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

    polyline = area = None
    if len(plotted) > 1:
        polyline = " ".join(f"{point['x']},{point['y']}" for point in plotted)
        area = (
            f"M {plotted[0]['x']},{baseline} "
            + " ".join(f"L {point['x']},{point['y']}" for point in plotted)
            + f" L {plotted[-1]['x']},{baseline} Z"
        )

    return {
        "width": _CHART_WIDTH,
        "height": _CHART_HEIGHT,
        "baseline": round(baseline, 2),
        "label_y": round(baseline + 18, 2),
        "axis_x": _CHART_PAD_LEFT - 8,
        "grid_start": _CHART_PAD_LEFT,
        "grid_end": _CHART_WIDTH - _CHART_PAD_RIGHT,
        "points": points,
        "polyline": polyline,
        "area": area,
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


def _format_score(value: float) -> str:
    """Pokaż całkowitą gotowość bez zbędnego miejsca dziesiętnego."""
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


def _format_date(value: str) -> str:
    """Sformatuj datę raportu dla polskiego dashboardu."""
    parsed = date.fromisoformat(value)
    return f"{parsed.day} {_MONTHS_GENITIVE[parsed.month - 1]} {parsed.year}"


def _format_sync_time(value, now: datetime) -> str:
    """Pokaż czas snapshotu w lokalnej strefie, bez surowego formatu ISO."""
    if not isinstance(value, str) or not value:
        return "Nie wiadomo, kiedy ostatnio synchronizowano dane."
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            return "Nie wiadomo, kiedy ostatnio synchronizowano dane."
        local_timestamp = timestamp.astimezone()
        local_now = now.astimezone() if now.tzinfo is not None else now.astimezone()
    except (TypeError, ValueError, OverflowError):
        return "Nie wiadomo, kiedy ostatnio synchronizowano dane."
    days_ago = (local_now.date() - local_timestamp.date()).days
    clock = f"{local_timestamp.hour}:{local_timestamp.minute:02d}"
    if days_ago == 0:
        return f"Zsynchronizowano dziś o {clock}"
    if days_ago == 1:
        return f"Zsynchronizowano wczoraj o {clock}"
    if 2 <= days_ago <= 6:
        return f"Zsynchronizowano {days_ago} dni temu o {clock}"
    return f"Zsynchronizowano {local_timestamp.day} {_MONTHS_GENITIVE[local_timestamp.month - 1]} o {clock}"


def _job_timestamp(value: str | None) -> datetime | None:
    """Odczytaj czas rekordu zadania jako świadomy czas UTC."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone(timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sync_banner(store: JobStore, now: datetime) -> dict[str, str | bool | None]:
    """Wylicz stan paska wyłącznie z najnowszego zadania synchronizacji."""
    jobs = [job for job in store.list_jobs().jobs if job.operation == "sync"]
    if not jobs:
        return {"message": None, "details_url": None, "refresh": False, "disabled": False}
    job = jobs[0]
    if job.status in {"accepted", "running"}:
        return {"message": "Trwa synchronizacja danych. Może potrwać około dwóch minut. Strona odświeży się sama.",
                "details_url": None, "refresh": True, "disabled": True}
    completed_at = _job_timestamp(job.finished_at or job.created_at)
    current = now.astimezone(timezone.utc)
    recent = completed_at is not None and current - completed_at <= timedelta(minutes=10)
    if job.status == "failed" and recent:
        return {"message": "Ostatnia synchronizacja się nie udała.",
                "details_url": f"/jobs/{job.id}", "refresh": False, "disabled": False}
    if job.status == "unknown" and recent:
        return {"message": "Nie wiemy, czy ostatnia synchronizacja się dokończyła. Sprawdź dane, zanim spróbujesz ponownie.",
                "details_url": f"/jobs/{job.id}", "refresh": False, "disabled": False}
    if job.status == "succeeded" and completed_at is not None and current < completed_at + SYNC_COOLDOWN:
        return {"message": "Dane zsynchronizowano niedawno. Odczekaj chwilę przed kolejną próbą.",
                "details_url": None, "refresh": False, "disabled": False}
    return {"message": None, "details_url": None, "refresh": False, "disabled": False}


def _analysis_rows(readiness_data: dict) -> list[dict]:
    """Przełóż rozkład punktów gotowości na wiersze widoku. Status jest jedynym źródłem koloru."""
    rows = []
    for detail in readiness_data.get("details") or []:
        metric = detail.get("metric")
        status = detail.get("status")
        meta = _SIGNAL_META.get(metric, {})
        rows.append({
            "label": meta.get("label") or metric or "Sygnał",
            "icon": meta.get("icon"),
            "pill_class": _ANALYSIS_PILL_CLASSES.get(status, "neutral"),
            "status_label": _SIGNAL_STATE_LABELS.get(status, "brak danych"),
            "message": detail.get("message") or "",
        })
    return rows


def _analysis_measurements(readiness_data: dict) -> list[dict]:
    """Pokaż zmierzone wartości stojące za oceną. Brak pomiaru zostaje brakiem, nie zerem."""
    baseline = readiness_data.get("hrv_baseline")
    baseline_text = None
    if baseline is not None and "None" not in str(baseline):
        baseline_text = str(baseline).replace("-", "–")
    hrv_status = readiness_data.get("hrv_status")
    return [
        {"label": "Tętno spoczynkowe", "value": readiness_data.get("rhr"), "unit": "bpm", "icon": "heart"},
        {"label": "HRV ostatniej nocy", "value": readiness_data.get("hrv_last"), "unit": "", "icon": "pulse"},
        {"label": "HRV — zakres bazowy", "value": baseline_text, "unit": "", "icon": "pulse"},
        {"label": "HRV — ocena zegarka", "icon": "pulse",
         "value": _HRV_STATUSES.get(hrv_status) if hrv_status is not None else None, "unit": ""},
        {"label": "Sen — ocena", "value": readiness_data.get("sleep_score_val"), "unit": "/100", "icon": "moon"},
        {"label": "Sen — długość", "value": readiness_data.get("sleep_total"), "unit": "h", "icon": "moon"},
        {"label": "Stres — średnia dobowa", "value": readiness_data.get("stress"), "unit": "", "icon": "bolt"},
    ]


def _profile_rows(profile: dict, fields) -> list[dict]:
    """Zbuduj wiersze profilu tylko z zapisanych pól. Nic nie jest domyślane."""
    rows = []
    for key, label, unit in fields:
        value = profile.get(key)
        rows.append({
            "label": label,
            "value": None if value is None or value == "" else value,
            "unit": unit,
        })
    return rows


def _hr_zone_rows(profile: dict) -> list[dict]:
    """Pokaż strefy dokładnie tak, jak zapisał je profil — bez przeliczania granic."""
    zones = profile.get("hr_zones")
    rows = []
    if isinstance(zones, str) and zones.strip():
        for entry in zones.split(","):
            parts = entry.strip().split(" ", 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                rows.append({"name": parts[0], "range": parts[1].replace("-", "–")})
        if rows:
            return rows
    floors = profile.get("hr_zone_floors")
    if isinstance(floors, dict):
        for key in ("z1", "z2", "z3", "z4", "z5"):
            if floors.get(key) is not None:
                rows.append({"name": key.upper(), "range": f"od {floors[key]}"})
    return rows


_MATCH_NOTES = {
    "heuristic": "Wykonanie dopasowano po czasie i dystansie, bez pewnego identyfikatora.",
    "ambiguous": "Do tego treningu pasuje więcej niż jedna aktywność.",
}
_SCORE_ROWS = (
    ("zgodnosc_z_planem", "Zgodność z planem", "Jak blisko planu był czas i tętno."),
    ("dopasowanie_do_formy", "Dopasowanie do formy", "Czy intensywność pasowała do gotowości tego dnia."),
)
_SCORE_CONFIDENCE_LABELS = {"wysoka": "wysoka", "srednia": "średnia", "niska": "niska"}


def _workout_status(execution: dict) -> tuple[str, str]:
    """Opisz wykonanie treningu słowem i klasą koloru."""
    if execution.get("happened") is True:
        return "Znaleziono wykonanie", "ok" if execution.get("certain") is True else "warn"
    if execution.get("match_method") == "ambiguous":
        return "Nie można jednoznacznie porównać", "warn"
    return "Brak wykonania w lokalnych danych", "neutral"


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
    score_rows = [
        {"label": label, "hint": hint, "value": score[key]}
        for key, label, hint in _SCORE_ROWS if score is not None
    ]
    return {
        "execution": execution,
        "name": planned.get("name") or "Trening",
        "kind": spec.get("kind"),
        "planned_duration": planned_duration_min(spec),
        "target": f"Z{zone} ({band[0]}–{band[1]} bpm)" if zone is not None and band else None,
        "status_label": status_label,
        "status_class": status_class,
        "match_note": _MATCH_NOTES.get(execution.get("match_method")),
        "planned_count": execution.get("planned_count"),
        "score": score,
        "score_rows": score_rows,
        "confidence_label": _SCORE_CONFIDENCE_LABELS.get(score["pewnosc"]) if score else None,
        "comment": (review or {}).get("comment"),
        "review_key": review_key,
    }
