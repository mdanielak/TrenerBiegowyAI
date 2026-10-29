# -*- coding: utf-8 -*-
"""Kreator celu i tygodnia: pierwsze uruchomienie i późniejsza zmiana celu.

Zapisuje do istniejących pól profilu (czytanych przez AI i stronę Cel) oraz do
dostępności dni w preferencjach. Pola fizjologiczne profilu zostają nietknięte.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from services.form_errors import FieldError

DISTANCES = {
    "5k": "5 km",
    "10k": "10 km",
    "hm": "półmaraton",
    "marathon": "maraton",
    "other": "inny dystans",
    "fitness": "bez zawodów — ogólna forma",
}
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_LABELS = dict(zip(DAYS, ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")))
STEPS = ("goal", "times", "week", "summary")
NAME_LIMIT = 80
_TIME = re.compile(r"^(?:(\d{1,2}):)?([0-5]?\d):([0-5]\d)$")


def needs_onboarding(profile: dict | None) -> bool:
    """Pierwsze uruchomienie: profil bez żadnego celu i bez wcześniejszej decyzji w kreatorze."""
    profile = profile or {}
    if profile.get("onboarding_completed_at") or profile.get("onboarding_skipped_at"):
        return False
    return not (profile.get("target_race") or profile.get("target_date") or profile.get("target_time"))


def _distance_key(race: str) -> str:
    text = str(race or "").lower()
    for key, label in DISTANCES.items():
        if key != "other" and label.split(" —")[0] in text:
            return key
    return "other" if text else "hm"


def prefill(profile: dict, availability: dict) -> dict:
    """Wartości startowe kreatora z obecnego profilu i dostępności."""
    profile = profile or {}
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", str(profile.get("target_date") or ""))
    frequency = re.search(r"\d", str(profile.get("training_frequency") or ""))
    distance = profile.get("target_distance") or _distance_key(profile.get("target_race"))
    values = {
        "distance": distance,
        "distance_other": profile.get("target_distance_other") or (
            profile.get("target_race") if distance == "other" else ""),
        "event_name": profile.get("target_event") or "",
        "event_date": date_match.group(0) if date_match else "",
        "target_time": profile.get("target_time") or "",
        "record": profile.get("current_hm_record") or "",
        "frequency": frequency.group(0) if frequency else "4",
    }
    for day in DAYS:
        slot = (availability or {}).get(day) or {}
        values[f"day_{day}"] = "on" if slot.get("available") else ""
        values[f"min_{day}"] = str(slot.get("min_minutes") or 30)
        values[f"max_{day}"] = str(slot.get("max_minutes") or 60)
    return values


def _clean(text, limit=NAME_LIMIT) -> str:
    return " ".join(str(text or "").split())[:limit]


def normalize_time(text) -> str:
    """Czas jako 'G:MM:SS' albo 'MM:SS' (np. '1:49:00', '49:30'); pusty tekst zostaje pusty."""
    text = str(text or "").strip()
    if not text:
        return ""
    match = _TIME.match(text)
    if not match:
        raise ValueError("Czas wpisz jako G:MM:SS (np. 1:49:00) albo MM:SS (np. 49:30).")
    hours, minutes, seconds = match.groups()
    return f"{int(hours)}:{int(minutes):02d}:{seconds}" if hours else f"{int(minutes)}:{seconds}"


def validate_step(step: str, values: dict, *, today: date) -> dict:
    """Sprawdź pola jednego kroku i zwróć ich oczyszczone wartości."""
    if step == "goal":
        distance = values.get("distance")
        if distance not in DISTANCES:
            raise FieldError("Wybierz cel.", "distance")
        cleaned = {"distance": distance, "distance_other": _clean(values.get("distance_other")),
                   "event_name": _clean(values.get("event_name")), "event_date": ""}
        if distance == "other" and not cleaned["distance_other"]:
            raise FieldError("Wpisz, jaki to dystans.", "distance_other")
        raw_date = str(values.get("event_date") or "").strip()
        if raw_date:
            try:
                event = date.fromisoformat(raw_date)
            except ValueError:
                raise FieldError("Podaj datę w formacie RRRR-MM-DD.", "event_date") from None
            if event < today:
                raise FieldError("Data wydarzenia nie może być w przeszłości.", "event_date")
            if event > today + timedelta(days=3 * 366):
                raise FieldError("Data wydarzenia może być najwyżej 3 lata naprzód.", "event_date")
            cleaned["event_date"] = event.isoformat()
        elif distance != "fitness":
            raise FieldError("Podaj datę wydarzenia — nawet orientacyjną, później ją zmienisz.", "event_date")
        return cleaned
    if step == "times":
        cleaned = {}
        for field in ("target_time", "record"):
            try:
                cleaned[field] = normalize_time(values.get(field))
            except ValueError as error:
                raise FieldError(str(error), field) from None
        return cleaned
    if step == "week":
        try:
            frequency = int(values.get("frequency") or 0)
        except ValueError:
            frequency = 0
        if not 1 <= frequency <= 7:
            raise FieldError("Liczba treningów w tygodniu to od 1 do 7.", "frequency")
        cleaned = {"frequency": str(frequency)}
        chosen = 0
        for day in DAYS:
            on = values.get(f"day_{day}") == "on"
            chosen += on
            try:
                low, high = int(values.get(f"min_{day}") or 0), int(values.get(f"max_{day}") or 0)
            except ValueError:
                raise FieldError(f"Minuty dla dnia {DAY_LABELS[day]} muszą być liczbą.", f"min_{day}") from None
            if on and not (10 <= low <= high <= 300):
                raise FieldError(f"Dla dnia {DAY_LABELS[day]} podaj minuty od 10 do 300, „od” nie większe niż „do”.", f"min_{day}")
            cleaned.update({f"day_{day}": "on" if on else "", f"min_{day}": str(low), f"max_{day}": str(high)})
        if chosen < frequency:
            raise FieldError(f"Zaznacz co najmniej {frequency} dni, w które możesz trenować.", "day_mon")
        return cleaned
    return {}


def goal_label(values: dict) -> str:
    distance = values.get("distance")
    return values.get("distance_other") if distance == "other" else DISTANCES.get(distance, "")


def save(values: dict, *, update_profile, set_availability, now=None) -> None:
    """Zapisz cel do profilu i dni do preferencji (funkcje zapisu wstrzyknięte)."""
    race = goal_label(values)
    if values.get("event_name"):
        race = f"{race} — {values['event_name']}"
    fitness = values.get("distance") == "fitness"
    frequency = int(values["frequency"])
    word = "trening" if frequency == 1 else ("treningi" if frequency in (2, 3, 4) else "treningów")
    update_profile(
        target_distance=values["distance"],
        target_distance_other=values.get("distance_other") or "",
        target_event=values.get("event_name") or "",
        target_race=race,
        target_date=values.get("event_date") or "",
        target_time=values.get("target_time") or "",
        # Pola zgodne wstecz: AI i strona Cel czytają te nazwy.
        target_hm=" ".join(part for part in (race, values.get("target_time") or "") if part) if not fitness else race,
        current_hm_record=values.get("record") or "",
        training_frequency=f"{frequency} {word} w tygodniu",
        onboarding_completed_at=(now or datetime.now()).replace(microsecond=0).isoformat(),
    )
    for day in DAYS:
        on = values.get(f"day_{day}") == "on"
        set_availability(day, on, int(values[f"min_{day}"]) if on else 0, int(values[f"max_{day}"]) if on else 0)
