# -*- coding: utf-8 -*-
"""Wspólne etykiety i formatowanie dat, czasu oraz gotowości dla widoków."""
from __future__ import annotations

import math
from datetime import date, datetime

_WEEKDAYS = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")
_READINESS_LABELS = {
    "ready": "możesz trenować",
    "ready_with_reserves": "trenuj z rezerwą",
    "not_ready": "dziś lepiej odpuść",
    "no_data": "brak pomiarów z nocy",
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
_WEEK_WARNING_LABELS = {
    "snapshot_stale": "Dane o aktywnościach mogą być nieaktualne.",
    "snapshot_activities_may_be_incomplete": "Lista aktywności może być niepełna, bo dane zapisano w starszym, węższym zakresie.",
}
_SIGNAL_STATE_LABELS = {"OK": "dobrze", "WARN": "uwaga", "FAIL": "słabo", "UNKNOWN": "brak danych"}
_SIGNAL_META = {
    # explain: objaśnienie „(?)” dla osoby, która nie zna terminów; progi zgodne z services/readiness.py.
    "Sleep": {"label": "Sen", "unit": "/100", "icon": "moon",
              "asset": "02_health_status/sleep.png", "trend_key": "sleep_score",
              "explain": "Ocena snu 0–100 liczona przez zegarek Garmin z długości snu, faz snu głębokiego i REM oraz "
                         "wybudzeń. Aplikacja przyjmuje: 90 i więcej — bardzo dobry sen, 70–89 — przeciętny, poniżej 70 "
                         "— słaby. Po słabej nocy organizm regeneruje się gorzej, więc lżejszy trening jest bezpieczniejszy."},
    "HRV": {"label": "Zmienność tętna", "unit": "", "icon": "pulse",
            "asset": "02_health_status/hrv.png", "trend_key": None,
            "explain": "Zmienność tętna (HRV) to drobne różnice w odstępach między kolejnymi uderzeniami serca, mierzone "
                       "w nocy. Wyższa zwykle znaczy, że organizm jest wypoczęty; niższa — że zmaga się ze zmęczeniem, "
                       "stresem albo infekcją. Zegarek porównuje ją z Twoim własnym zakresem z ostatnich tygodni: "
                       "„niskie” albo „niezrównoważone” znaczy, że wypada poza ten zakres — wtedy lepiej dziś biec spokojniej."},
    "RHR": {"label": "Tętno spoczynkowe", "unit": "bpm", "icon": "heart",
            "asset": "02_health_status/resting_hr.png", "trend_key": "rhr",
            "explain": "Tętno spoczynkowe to najniższe tętno w ciągu doby, w pełnym spoczynku. Każdy ma własną normę, "
                       "więc aplikacja porównuje dzisiejszy pomiar ze średnią z Twoich ostatnich czterech tygodni: do 2 uderzeń "
                       "więcej to norma, 3–5 — lekko podwyższone, więcej — podwyższone. Wyższe niż zwykle bywa sygnałem "
                       "zmęczenia, odwodnienia albo nadchodzącej infekcji."},
    "Stress": {"label": "Stres", "unit": "", "icon": "bolt",
               "asset": "02_health_status/stress.png", "trend_key": "stress_avg",
               "explain": "Średni poziom stresu w ciągu dnia w skali 0–100, liczony przez zegarek z tętna i HRV. Do 30 "
                          "— niski, 31–40 — umiarkowany, powyżej 40 — podwyższony. Stres w pracy czy słaby sen obciążają "
                          "organizm podobnie jak trening, dlatego też wpływają na ocenę."},
}
_WEEKDAYS_SHORT = ("pon", "wt", "śr", "czw", "pt", "sob", "ndz")
_READINESS_PILL_CLASSES = {"ready": "ok", "ready_with_reserves": "warn", "not_ready": "bad"}


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
