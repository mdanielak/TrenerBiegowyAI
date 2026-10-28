# -*- coding: utf-8 -*-
"""Deterministyczne reguły tygodniowego planu treningowego.

Silnik AI jest niedokładny, więc twarde reguły tygodnia — dostępność dni,
przerwy, limity treningów jakościowych, format tempa — egzekwuje ten moduł.
Nie wykonuje on I/O poza zapisem planu i nie zna providera AI.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone

from services import plan_files
from services.readiness import readiness_for_day
from services.plan_files import week_bounds


PLAN_KINDS = ("easy", "recovery", "long", "tempo", "threshold", "intervals", "rest")
QUALITY_KINDS = ("tempo", "threshold", "intervals")
AEROBIC_KINDS = ("easy", "recovery", "long")

_DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_WEEKDAY_NAMES = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")
_PACE_RE = re.compile(r"^(\d{1,2}):([0-5]\d)$")
_PACE_SPLIT_RE = re.compile(r"[-–]")

_NAME_LIMIT = 60
_DESCRIPTION_LIMIT = 300
_NOTES_LIMIT = 200
_TEXT_LIMIT = 300
_SUMMARY_LIMIT = 600


def _pace_seconds(value) -> int | None:
    """Zamień 'M:SS' na liczbę sekund; format niepoprawny zwraca None."""
    if not isinstance(value, str):
        return None
    match = _PACE_RE.match(value.strip())
    if match is None:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _format_pace(seconds: int) -> str:
    """Zamień liczbę sekund na 'M:SS'."""
    return f"{seconds // 60}:{seconds % 60:02d}"


def parse_pace_target(value) -> tuple[int, int] | None:
    """Rozłóż tempo docelowe na parę (szybsze, wolniejsze) w sekundach."""
    if not isinstance(value, str):
        return None
    parts = [part.strip() for part in _PACE_SPLIT_RE.split(value) if part.strip()]
    if not parts or len(parts) > 2:
        return None
    seconds = []
    for part in parts:
        parsed = _pace_seconds(part)
        if parsed is None:
            return None
        seconds.append(parsed)
    if len(seconds) == 1:
        return seconds[0], seconds[0]
    return min(seconds), max(seconds)


def normalize_pace_target(value) -> str | None:
    """Ujednolic tempo docelowe do 'M:SS' albo 'M:SS-M:SS' (szybsza granica first)."""
    parsed = parse_pace_target(value)
    if parsed is None:
        return None
    faster, slower = parsed
    if faster == slower:
        return _format_pace(faster)
    return f"{_format_pace(faster)}-{_format_pace(slower)}"


def zone_number(value) -> int | None:
    """Odczytaj numer strefy z tekstu 'Z2' albo z liczby."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 1 <= value <= 5 else None
    if isinstance(value, str):
        text = value.strip().upper()
        if text.startswith("Z"):
            text = text[1:]
        try:
            number = int(text)
        except ValueError:
            return None
        return number if 1 <= number <= 5 else None
    return None


def hr_band(zone_number_value, floors) -> str | None:
    """Zbuduj tekst zakresu tętna ze progów stref ('122-136 bpm', '173+ bpm')."""
    if not isinstance(floors, dict):
        return None
    zone = zone_number(zone_number_value)
    if zone is None:
        return None
    low = floors.get(f"z{zone}")
    if low is None:
        return None
    try:
        low_value = int(low)
    except (TypeError, ValueError):
        return None
    if zone == 5:
        return f"{low_value}+ bpm"
    high = floors.get(f"z{zone + 1}")
    if high is None:
        return f"od {low_value} bpm"
    try:
        high_value = int(high)
    except (TypeError, ValueError):
        return None
    return f"{low_value}-{high_value - 1} bpm"


def as_datetime(value):
    """Przyjmij datę jako tekst RRRR-MM-DD albo obiekt datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ValueError("Nieprawidłowa data tygodnia. Użyj formatu RRRR-MM-DD.") from exc


def _field(source, name, default=None):
    """Odczytaj pole z obiektu Pydantic albo ze słownika."""
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _readiness_for(data, day):
    """Gotowość dnia; może jej nie być, gdy zegarek nie zebrał pomiarów."""
    try:
        return readiness_for_day(data, day)
    except (KeyError, TypeError, ValueError):
        return None


# Trendy dla AI: średnia z 7 dni wobec 12 tygodni, bez surowych serii.
_TREND_METRICS = ("readiness", "rhr", "hrv", "sleep")


def _plan_trends(data, today) -> dict:
    """Zwięzłe trendy ze statystyk i kilometry z czterech ostatnich pełnych tygodni."""
    from services.data_extract import SnapshotReadResult, SnapshotStatus
    from services.stats import build_stats_report, trend_direction

    report = build_stats_report(snapshot=SnapshotReadResult(status=SnapshotStatus.FRESH, data=data),
                                today=today, weeks=12)
    if report.status != "ok":
        return {}
    metrics = {key: {"recent": report.metrics[key].recent_average, "average": report.metrics[key].average,
                     "direction": trend_direction(report.metrics[key])} for key in _TREND_METRICS}
    completed = [week.distance_km for week in report.weekly if not week.is_current]
    return {"metrics": metrics, "weekly_km": completed[-4:]}


def build_plan_context(*, snapshot_data, profile, preferences, today=None, week_start=None,
                        snapshot_status=None, snapshot_timestamp=None) -> dict:
    """Zbuduj kontekst planu: profil, dostępność, przerwy, obciążenie i gotowość."""
    from ai.context import _compute_weekly_load, build_training_context
    from trainer.preferences import get_active_pause, get_weekly_availability

    current = as_datetime(today) or datetime.now()
    anchor = as_datetime(week_start) or current
    monday, sunday = week_bounds(anchor)
    data = snapshot_data or {}
    preferences = preferences or {}

    availability = get_weekly_availability()
    days = []
    for index in range(7):
        day_date = monday + timedelta(days=index)
        day_key = _DAY_KEYS[index]
        slot = availability.get(day_key) or {}
        day_text = day_date.date().isoformat()
        pause = get_active_pause(day_text)
        readiness = _readiness_for(data, day_text)
        days.append({
            "date": day_text,
            "day": day_key,
            "weekday": _WEEKDAY_NAMES[index],
            "available": bool(slot.get("available")),
            "min_minutes": int(slot.get("min_minutes") or 0),
            "max_minutes": int(slot.get("max_minutes") or 0),
            "pause_reason": (pause or {}).get("reason") if pause else None,
            "readiness_score": (readiness or {}).get("score"),
            "readiness_level": (readiness or {}).get("level"),
        })

    history = []
    for offset in range(7, -1, -1):
        day_text = (current - timedelta(days=offset)).date().isoformat()
        readiness = _readiness_for(data, day_text)
        history.append({
            "date": day_text,
            "score": (readiness or {}).get("score"),
            "level": (readiness or {}).get("level"),
        })

    training = build_training_context(data, plan=None, today=current)
    previous_week = _compute_weekly_load(data, current - timedelta(days=7))

    return {
        "week_start": monday.date().isoformat(),
        "week_end": sunday.date().isoformat(),
        "week_days": days,
        "max_quality_sessions": int(preferences.get("max_quality_sessions_per_week", 1) or 0),
        "hr_zone_floors": (profile or {}).get("hr_zone_floors"),
        "profile": profile or {},
        "goal": training.get("goal") or {},
        "recent_activities": training.get("recent_activities") or [],
        "weekly_load": training.get("weekly_load") or {},
        "previous_weekly_load": previous_week,
        "readiness_history": history,
        "health_metrics": training.get("health_metrics") or {},
        "hrv_alert": training.get("hrv_alert"),
        "trends": _plan_trends(data, current.date()),
        "journal": training.get("journal"),
        "snapshot_status": snapshot_status,
        "snapshot_timestamp": snapshot_timestamp or (data.get("timestamp") if isinstance(data, dict) else None),
    }


def _clip_duration(duration, min_minutes, max_minutes):
    """Przytnij czas sesji do okna dostępności dnia."""
    if duration is None:
        return None, False
    high = int(max_minutes or 0)
    if high <= 0:
        return duration, False
    low = max(int(min_minutes or 0), 1)
    if low <= duration <= high:
        return duration, False
    return max(low, min(duration, high)), True


def _trim(text, limit):
    """Skróć tekst do limitu znaków na granicy słowa, z wielokropkiem na końcu."""
    if text is None:
        return ""
    value = str(text).strip()
    if len(value) <= limit:
        return value
    cut = value[:limit - 1]
    if " " in cut:
        cut = cut[:cut.rindex(" ")]
    return cut.rstrip(" ,;:—-") + "…"


def _default_week_days(context):
    """Zbuduj tygodń bez informacji o dostępności, gdy kontekst ich nie zawiera."""
    start = context.get("week_start")
    if not start:
        return []
    monday, _ = week_bounds(datetime.fromisoformat(str(start)[:10]))
    return [{
        "date": (monday + timedelta(days=index)).isoformat(),
        "day": _DAY_KEYS[index],
        "weekday": _WEEKDAY_NAMES[index],
        "available": True,
        "min_minutes": 0,
        "max_minutes": 0,
        "pause_reason": None,
        "readiness_score": None,
        "readiness_level": None,
    } for index in range(7)]


def _empty_workout():
    """Pusty zapis treningu przed wypełnieniem regułami."""
    return {
        "kind": "rest",
        "name": "Odpoczynek",
        "description": "",
        "duration_min": None,
        "distance_km": None,
        "hr_zone": None,
        "pace_target": None,
        "repetitions": None,
        "work_seconds": None,
        "rest_seconds": None,
        "notes": "",
    }


def _normalize_day(day, workout, floors):
    """Zastosuj reguły dnia i zwróć finalny zapis treningu."""
    available = bool(day.get("available"))
    pause_reason = day.get("pause_reason")
    min_minutes = int(day.get("min_minutes") or 0)
    max_minutes = int(day.get("max_minutes") or 0)
    notes = []

    entry = _empty_workout()
    forced_rest = (not available) or bool(pause_reason)

    if forced_rest:
        entry["kind"] = "rest"
        entry["name"] = "Odpoczynek"
        entry["description"] = pause_reason or "Dzień bez zadeklarowanej dostępności."
    elif workout is None:
        entry["kind"] = "rest"
        entry["name"] = "Odpoczynek"
    else:
        kind = _field(workout, "kind") or ""
        entry["kind"] = kind if kind in PLAN_KINDS else "easy"
        if kind not in PLAN_KINDS:
            notes.append("Zmieniono na bieg łatwy (nieznany rodzaj treningu).")
        entry["name"] = _trim(_field(workout, "name"), _NAME_LIMIT) or "Trening"
        entry["description"] = _trim(_field(workout, "description"), _DESCRIPTION_LIMIT)
        entry["duration_min"] = _field(workout, "duration_min")
        entry["distance_km"] = _field(workout, "distance_km")
        entry["hr_zone"] = _field(workout, "hr_zone")
        entry["pace_target"] = _field(workout, "pace_target")
        entry["repetitions"] = _field(workout, "repetitions")
        entry["work_seconds"] = _field(workout, "work_seconds")
        entry["rest_seconds"] = _field(workout, "rest_seconds")
        entry["notes"] = _trim(_field(workout, "notes"), _NOTES_LIMIT)

    kind = entry["kind"]

    if kind == "rest":
        entry["duration_min"] = None
        entry["distance_km"] = None
        entry["hr_zone"] = None
        entry["pace_target"] = None
        entry["repetitions"] = None
        entry["work_seconds"] = None
        entry["rest_seconds"] = None
        entry["name"] = "Odpoczynek"
        return _finish_day(day, entry, notes, floors)

    if kind in AEROBIC_KINDS:
        zone = zone_number(entry["hr_zone"])
        if zone is None:
            zone = 2 if kind in ("easy", "long") else 1
            notes.append(f"Uzupełniono brakującą strefę tętna: Z{zone}.")
        entry["hr_zone"] = zone
        clipped, changed = _clip_duration(entry["duration_min"], min_minutes, max_minutes)
        if changed:
            entry["duration_min"] = clipped
            notes.append(f"Skrócono do {clipped} min (limit dostępności w tym dniu).")

    if kind in ("tempo", "threshold"):
        if parse_pace_target(entry["pace_target"]) is None:
            notes.append("Zmieniono na bieg łatwy (brak parsowalnego tempa docelowego).")
            entry["kind"] = "easy"

    if kind == "intervals":
        missing = [name for name in ("repetitions", "work_seconds", "rest_seconds")
                   if not isinstance(entry[name], int) or isinstance(entry[name], bool) or entry[name] <= 0]
        if missing:
            notes.append("Zmieniono na bieg łatwy (brak kompletnych parametrów interwałów).")
            entry["kind"] = "easy"
        elif parse_pace_target(entry["pace_target"]) is None:
            notes.append("Zmieniono na bieg łatwy (brak parsowalnego tempa docelowego).")
            entry["kind"] = "easy"

    if kind == "long" and entry["duration_min"] is None:
        notes.append("Zmieniono na bieg łatwy (brak czasu treningu).")
        entry["kind"] = "easy"

    if entry["kind"] != kind and entry["kind"] in AEROBIC_KINDS:
        zone = zone_number(entry["hr_zone"])
        if zone is None:
            zone = 2
            notes.append("Uzupełniono brakującą strefę tętna: Z2.")
        entry["hr_zone"] = zone
        clipped, changed = _clip_duration(entry["duration_min"], min_minutes, max_minutes)
        if changed:
            entry["duration_min"] = clipped
            notes.append(f"Skrócono do {clipped} min (limit dostępności w tym dniu).")

    if entry["kind"] != "rest" and entry["duration_min"] is None:
        entry["duration_min"] = min_minutes
        if entry["kind"] in AEROBIC_KINDS:
            clipped, changed = _clip_duration(entry["duration_min"], min_minutes, max_minutes)
            if changed:
                entry["duration_min"] = clipped
                notes.append(f"Skrócono do {clipped} min (limit dostępności w tym dniu).")

    return _finish_day(day, entry, notes, floors)


def _finish_day(day, entry, notes, floors):
    """Domknij zapis dnia: tempo, zakres tętna, uwagi i klucze zgodne ze schematem."""
    kind = entry["kind"]
    if kind == "rest":
        pace_target = None
        hr_zone = None
        hr_target = None
    else:
        pace_target = normalize_pace_target(entry["pace_target"])
        hr_zone = zone_number(entry["hr_zone"])
        hr_target = hr_band(hr_zone, floors)

    combined = entry["notes"]
    for note in notes:
        combined = f"{combined}; {note}" if combined else note

    workout = {
        "day": day.get("day"),
        "date": day.get("date"),
        "type": kind,
        "name": entry["name"] or "Trening",
        "description": entry["description"],
        "distance_km": entry["distance_km"],
        "duration_min": entry["duration_min"],
        "pace_target": pace_target,
        "hr_target": hr_target,
        "hr_zone": f"Z{hr_zone}" if hr_zone else None,
        "garmin_upload": False,
        "garmin_workout_id": None,
        "notes": _trim(combined, _NOTES_LIMIT),
    }
    if kind == "intervals":
        workout["repetitions"] = entry["repetitions"]
        workout["work_seconds"] = entry["work_seconds"]
        workout["rest_seconds"] = entry["rest_seconds"]
    return workout


def normalize_plan(response, *, context) -> dict:
    """Zamień odpowiedź AI na plan tygodniowy zgodny z regułami i schematem pliku."""
    context = context or {}
    floors = context.get("hr_zone_floors") or {}
    max_quality = context.get("max_quality_sessions")
    max_quality = 1 if max_quality is None else int(max_quality)

    week_days = list(context.get("week_days") or []) or _default_week_days(context)
    dates = [day.get("date") for day in week_days]

    by_date = {}
    for workout in _field(response, "workouts", []) or []:
        date = _field(workout, "date")
        if date in dates and date not in by_date:
            by_date[date] = workout

    workouts = [_normalize_day(day, by_date.get(day.get("date")), floors) for day in week_days]

    quality = [index for index, workout in enumerate(workouts) if workout["type"] in QUALITY_KINDS]
    for index in quality[max_quality:]:
        workouts[index]["type"] = "easy"
        workouts[index]["pace_target"] = None
        workouts[index]["notes"] = _append_note(
            workouts[index]["notes"], f"Zmieniono na bieg łatwy (limit {max_quality} treningu jakościowego w tygodniu).")

    long_runs = [index for index, workout in enumerate(workouts) if workout["type"] == "long"]
    for index in long_runs[1:]:
        workouts[index]["type"] = "easy"
        workouts[index]["notes"] = _append_note(
            workouts[index]["notes"], "Zmieniono na bieg łatwy (limit 1 długiego biegu w tygodniu).")

    for index, workout in enumerate(workouts):
        if workout["type"] not in AEROBIC_KINDS:
            continue
        day = week_days[index]
        zone = zone_number(workout["hr_zone"])
        if zone is None:
            zone = 2
            workout["hr_zone"] = "Z2"
            workout["notes"] = _append_note(workout["notes"], "Uzupełniono brakującą strefę tętna: Z2.")
        workout["hr_target"] = hr_band(zone, floors)
        clipped, changed = _clip_duration(workout["duration_min"], day.get("min_minutes"), day.get("max_minutes"))
        if changed:
            workout["duration_min"] = clipped
            workout["notes"] = _append_note(
                workout["notes"], f"Skrócono do {clipped} min (limit dostępności w tym dniu).")

    start_date = _field(response, "start_date") or context.get("week_start")
    end_date = _field(response, "end_date") or context.get("week_end")

    return {
        "start_date": start_date,
        "end_date": end_date,
        "priority": "normal",
        "focus": _trim(_field(response, "focus"), _TEXT_LIMIT),
        "summary": _trim(_field(response, "summary"), _SUMMARY_LIMIT),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "workouts": workouts,
    }


def _append_note(notes, note):
    """Dopisz uwagę do istniejących uwag."""
    return f"{notes}; {note}" if notes else note


def save_plan(plan, *, plans_dir=None):
    """Zapisz plan atomowo jako JSON i zapisz jego bliźniaczy CSV."""
    monday = datetime.strptime(plan["start_date"], "%Y-%m-%d")
    path = plan_files.plan_path(monday, plans_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    plan_files.write_plan_csv(plan, path.with_suffix(".csv"))
    return path


def load_week_plan(day, *, plans_dir=None):
    """Wczytaj plan obejmujący wskazany dzień albo None."""
    return plan_files.load_plan(day, plans_dir)


def previous_week_load(data, monday):
    """Obciążenie tygodnia poprzedzającego podany poniedziałek (km, min, sesje)."""
    from ai.context import _compute_weekly_load
    return _compute_weekly_load(data, monday - timedelta(days=7))


def plan_workout_to_garmin(workout):
    """Zamień trening z planu na parę (rodzaj, argumenty) dla Garmin Connect."""
    if not isinstance(workout, dict):
        return None
    kind = workout.get("type")
    date = workout.get("date")

    if kind in AEROBIC_KINDS:
        minutes = workout.get("duration_min")
        zone = zone_number(workout.get("hr_zone"))
        if not minutes or zone is None:
            return None
        return ("hr_zone_run", {
            "minutes": int(minutes),
            "zone_number": zone,
            "date": date,
            "warmup_min": 6,
            "warmup_pace_faster": "7:00",
            "warmup_pace_slower": "8:30",
        })

    if kind in ("tempo", "threshold"):
        pace = parse_pace_target(workout.get("pace_target"))
        minutes = workout.get("duration_min")
        if pace is None or not minutes:
            return None
        return ("tempo", {
            "minutes": max(5, int(minutes) - 20),
            "pace_from": _format_pace(pace[0]),
            "pace_to": _format_pace(pace[1]),
            "date": date,
        })

    if kind == "intervals":
        pace = parse_pace_target(workout.get("pace_target"))
        if pace is None:
            return None
        return ("intervals", {
            "repeats": workout.get("repetitions"),
            "work_seconds": workout.get("work_seconds"),
            "rest_seconds": workout.get("rest_seconds"),
            "pace_from": _format_pace(pace[0]),
            "pace_to": _format_pace(pace[1]),
            "date": date,
        })

    return None
