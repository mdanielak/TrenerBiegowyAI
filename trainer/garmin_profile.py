"""Normalizacja prywatnych danych profilu zwracanych przez Garmin Connect."""
from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)

_DAY_MAP = {
    "MONDAY": "mon", "TUESDAY": "tue", "WEDNESDAY": "wed", "THURSDAY": "thu",
    "FRIDAY": "fri", "SATURDAY": "sat", "SUNDAY": "sun",
}

# Zakresy fizjologiczne: Garmin przy braku pomiaru potrafi zwrócić 0 albo
# wartość skrajną, a taka liczba zatrułaby profil i całą ocenę gotowości.
_LIMITS = (
    ("height", "height", 100, 250),
    ("lactateThresholdHeartRate", "lactate_threshold_hr", 100, 220),
    ("vo2MaxRunning", "vo2max_running", 10, 95),
)


def _bounded(value, low: int, high: int) -> int | None:
    """Zwróć zaokrągloną liczbę tylko wtedy, gdy mieści się w zakresie."""
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def parse_hr_zones(response) -> tuple[dict[str, int], int] | None:
    """Zwróć komplet progów HR z odpowiedzi listowej lub słownikowej Garmin."""
    choices = response if isinstance(response, list) else [response] if isinstance(response, dict) else []
    entries = [item for item in choices if isinstance(item, dict)]
    selected = next((item for item in entries if item.get("sport") == "RUNNING"), None)
    selected = selected or next((item for item in entries if item.get("sport") == "DEFAULT"), None)
    selected = selected or (entries[0] if entries else None)
    if not selected:
        return None
    try:
        floors = {f"z{i}": int(selected[f"zone{i}Floor"]) for i in range(1, 6)}
        maximum = int(selected["maxHeartRateUsed"])
    except (KeyError, TypeError, ValueError):
        return None
    return floors, maximum


def _call(api, method, *args):
    try:
        return getattr(api, method)(*args)
    except Exception as exc:  # każdy endpoint jest niezależnie opcjonalny
        logger.debug("Nie udało się pobrać %s: %s", method, exc)
        return None


def fetch_snapshot(api) -> dict:
    """Pobierz dostępne dane niezależnie, bez propagowania błędu jednego endpointu."""
    result: dict = {}
    profile = _call(api, "get_user_profile") or {}
    user = profile.get("userData") if isinstance(profile, dict) else {}
    user = user if isinstance(user, dict) else {}
    birth = user.get("birthDate")
    if isinstance(birth, str):
        try:
            born = date.fromisoformat(birth)
            today = date.today()
            result["age"] = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        except ValueError:
            pass
    weight_grams = _bounded(user.get("weight"), 30_000, 250_000)
    if weight_grams is not None:
        result["weight"] = round(weight_grams / 1000)
    for source, target, low, high in _LIMITS:
        value = _bounded(user.get(source), low, high)
        if value is not None:
            result[target] = value
    summary = _call(api, "get_user_summary", date.today().isoformat()) or {}
    if isinstance(summary, dict):
        resting = _bounded(summary.get("lastSevenDaysAvgRestingHeartRate"), 25, 100)
        if resting is None:
            resting = _bounded(summary.get("restingHeartRate"), 25, 100)
        if resting is not None:
            result["hr_rest"] = resting
    parsed = parse_hr_zones(_call(api, "get_heart_rate_zones"))
    if parsed:
        result["hr_zone_floors"], result["hr_max"] = parsed
    for source, target in (("availableTrainingDays", "available_training_days"), ("preferredLongTrainingDays", "long_training_days")):
        raw = user.get(source)
        if isinstance(raw, list):
            result[target] = [mapped for item in raw if (mapped := _DAY_MAP.get(str(item).upper()))]
    return result
