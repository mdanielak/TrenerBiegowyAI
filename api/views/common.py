# -*- coding: utf-8 -*-
"""Wspólne etykiety i formatowanie dat, czasu oraz gotowości dla widoków."""
from __future__ import annotations

import math
from datetime import date, datetime

_WEEKDAYS = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")
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
    "planned_pause": "Planowana przerwa (rekonwalescencja)",
    "activity_only": "Aktywności bez zapisanego treningu",
    "planned": "Zaplanowane",
    "matched": "Znaleziono wykonanie",
    "partially_matched": "Znaleziono wykonanie części treningów",
    "no_record": "Brak wykonania w lokalnych danych",
    "uncertain": "Nie można jednoznacznie porównać",
}
_WEEK_WARNING_LABELS = {
    "snapshot_stale": "Dane o aktywnościach mogą być nieaktualne.",
    "snapshot_activities_may_be_incomplete": "Lista aktywności może być niepełna, bo obejmuje tylko 50 ostatnich treningów.",
}
_SIGNAL_STATE_LABELS = {"OK": "dobrze", "WARN": "uwaga", "FAIL": "słabo", "UNKNOWN": "brak danych"}
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
_WEEKDAYS_SHORT = ("pon", "wt", "śr", "czw", "pt", "sob", "ndz")
_READINESS_PILL_CLASSES = {"ready": "ok", "ready_with_reserves": "warn", "not_ready": "bad"}


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


def _format_number(value, decimals: int = 1):
    """Pokaż liczbę po polsku: przecinek dziesiętny, bez zbędnego ',0'. Tekst zostaje bez zmian."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    if isinstance(value, float) and not math.isfinite(value):
        return value
    rounded = round(float(value), decimals)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.{decimals}f}".rstrip("0").replace(".", ",")


def _plural(count, one: str, few: str, many: str) -> str:
    """Dobierz polską formę rzeczownika do liczby: 1 trening, 2 treningi, 5 treningów."""
    try:
        number = abs(int(count))
    except (TypeError, ValueError):
        return many
    if number == 1:
        return one
    if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
        return few
    return many


def _format_score(value: float) -> str:
    """Pokaż całkowitą gotowość bez zbędnego miejsca dziesiętnego."""
    return _format_number(float(value))


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
