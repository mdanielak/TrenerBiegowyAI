"""Czysta warstwa danych tygodniowego raportu treningowego."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from services.activity_matching import assign_activities
from services.data_extract import MAX_SNAPSHOT_ROWS, SnapshotStatus, read_snapshot_status
from services.plan import zone_number
from services.readiness import readiness_for_day
from services.plan_files import week_bounds
from services.workout_registry import list_workouts
from services.workout_scoring import planned_duration_min
from trainer.preferences import get_active_pause, get_weekly_availability

_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass
class DayAvailability:
    available: bool
    min_minutes: int
    max_minutes: int
    configured: bool
    pause_reason: str | None = None


@dataclass
class WeekWorkout:
    workout_id: int
    schedule_id: int | None
    name: str
    sport: str
    status: str
    matched_activity_id: int | None
    match_method: str
    warnings: list[str]
    planned_duration_min: int | None = None
    hr_zone: str | None = None


@dataclass
class WeekActivity:
    activity_id: int | None
    started_at: str
    sport: str
    name: str
    distance_km: float | None
    duration_min: float | None
    matched_workout_id: int | None
    avg_hr: int | None = None


@dataclass
class WeekDayReport:
    date: str
    weekday_index: int
    temporal_state: str
    availability: DayAvailability | None
    status: str
    warnings: list[str]
    workouts: list[WeekWorkout]
    activities: list[WeekActivity]
    readiness: dict | None = None


@dataclass
class WeekSummary:
    total_distance_km: float | None = None
    total_duration_min: float | None = None
    average_hr: int | None = None
    completed_workouts: int = 0
    planned_workouts: int = 0


@dataclass
class WeekReport:
    week_start: str
    week_end: str
    today: str
    plan_source: str
    registry_status: str
    snapshot_status: SnapshotStatus
    snapshot_timestamp: str | None
    warnings: list[str]
    days: list[WeekDayReport]
    summary: WeekSummary | None = None


def _sport(entry):
    """Rozpoznaj sport jedynie z jednoznacznego technicznego opisu."""
    spec = entry.get('spec')
    kind = spec.get('kind') if isinstance(spec, dict) else None
    if isinstance(kind, str) and ('run' in kind.lower() or kind.lower() == 'easy'):
        return 'running'
    definition = entry.get('definition')
    if isinstance(definition, dict) and definition.get('sport') == 'running':
        return 'running'
    return 'unknown'


def _valid_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _availability(raw):
    if not isinstance(raw, dict):
        return None
    available = bool(raw.get('available', False))
    minimum = raw.get('min_minutes', 0)
    maximum = raw.get('max_minutes', 0)
    if not isinstance(minimum, int):
        minimum = 0
    if not isinstance(maximum, int):
        maximum = 0
    return DayAvailability(available, minimum, maximum, available or minimum != 0 or maximum != 0)


def _activities_may_be_truncated(data, activities) -> bool:
    """Czy snapshot mógł uciąć listę aktywności.

    Snapshot z polem `window` bierze wszystkie aktywności z okna dat, więc ucięcie
    oznacza tylko dojście do twardego limitu wierszy. Starszy format bez `window`
    zawierał 50 ostatnich aktywności.
    """
    if isinstance(data.get('window'), dict):
        return len(activities) >= MAX_SNAPSHOT_ROWS
    return len(activities) >= 50


def build_week_report(*, snapshot, registry_entries, registry_status, availability, now) -> WeekReport:
    """Zbuduj raport tygodnia z przekazanych danych, bez odczytu plików."""
    monday, sunday = week_bounds(now.date())
    today = now.date().isoformat()
    snapshot_status = snapshot.status if snapshot is not None else SnapshotStatus.MISSING
    data = snapshot.data if snapshot is not None and isinstance(snapshot.data, dict) else {}
    timestamp = data.get('timestamp') if isinstance(data.get('timestamp'), str) else None
    warnings = []
    if snapshot_status == SnapshotStatus.STALE:
        warnings.append('snapshot_stale')
    raw_activities = data.get('activities', [])
    if not isinstance(raw_activities, list):
        raw_activities = []
    if _activities_may_be_truncated(data, raw_activities):
        warnings.append('snapshot_activities_may_be_incomplete')
    entries = []
    for entry in registry_entries or []:
        if not isinstance(entry, dict) or entry.get('atp_plan_id'):
            continue
        entry_date = _valid_date(entry.get('date'))
        if entry_date is not None and monday <= entry_date <= sunday:
            entries.append(entry)
    by_date = {}
    for entry in entries:
        by_date.setdefault(entry['date'], []).append(entry)
    activities_by_date = {}
    for activity in raw_activities:
        if isinstance(activity, dict) and monday.isoformat() <= str(activity.get('date', ''))[:10] <= sunday.isoformat():
            activities_by_date.setdefault(str(activity.get('date'))[:10], []).append(activity)

    days = []
    for index in range(7):
        date = monday + timedelta(days=index)
        date_text = date.isoformat()
        day_entries = by_date.get(date_text, [])
        day_activities = activities_by_date.get(date_text, [])
        assignments = assign_activities(workouts=day_entries, activities=day_activities)
        matched_ids = {}
        workouts = []
        for position, entry in enumerate(day_entries):
            activity, method = assignments[position]
            matched_id = activity.get('activity_id') if activity else None
            if matched_id is not None:
                matched_ids[matched_id] = entry.get('workout_id')
            if method == 'ambiguous':
                status = 'uncertain'
            elif activity is not None:
                status = 'matched'
            elif date_text >= today:
                status = 'planned'
            else:
                status = 'no_record'
            spec = entry.get('spec') if isinstance(entry.get('spec'), dict) else {}
            try:
                duration = planned_duration_min(spec)
            except (TypeError, ValueError):
                duration = None
            zone = zone_number(spec.get('zone_number'))
            workouts.append(WeekWorkout(
                workout_id=entry.get('workout_id'),
                schedule_id=entry.get('schedule_id'),
                name=entry.get('name') or '',
                sport=_sport(entry),
                status=status,
                matched_activity_id=matched_id,
                match_method=method,
                warnings=[],
                planned_duration_min=duration,
                hr_zone=f"Z{zone}" if zone else None,
            ))
        week_activities = [WeekActivity(
            activity.get('activity_id'), str(activity.get('date', '')), activity.get('type') or '',
            activity.get('name') or '', activity.get('distance_km'), activity.get('duration_min'),
            matched_ids.get(activity.get('activity_id')), activity.get('avg_hr'),
        ) for activity in day_activities]
        if any(workout.status == 'uncertain' for workout in workouts):
            day_status = 'uncertain'
        elif not workouts:
            day_status = 'activity_only' if week_activities else 'no_plan'
        elif all(workout.status == 'matched' for workout in workouts):
            day_status = 'matched'
        elif any(workout.status == 'matched' for workout in workouts):
            day_status = 'partially_matched'
        elif date_text >= today:
            day_status = 'planned'
        else:
            day_status = 'no_record'
        temporal = 'today' if date_text == today else 'past' if date_text < today else 'future'
        raw_availability = availability.get(_DAYS[index]) if isinstance(availability, dict) else None
        day_avail = _availability(raw_availability)
        active_pause = get_active_pause(date_text)
        if active_pause:
            day_avail.available = False
            day_avail.pause_reason = active_pause.get("reason")
            if day_status == "no_plan":
                day_status = "planned_pause"
        days.append(WeekDayReport(date_text, index, temporal, day_avail, day_status, [],
                                  workouts, week_activities, readiness_for_day(data, date_text)))
    all_activities = [activity for day in days for activity in day.activities]
    distances = [activity.distance_km for activity in all_activities
                 if isinstance(activity.distance_km, (int, float)) and not isinstance(activity.distance_km, bool)]
    durations = [activity.duration_min for activity in all_activities
                 if isinstance(activity.duration_min, (int, float)) and not isinstance(activity.duration_min, bool)]
    heart_rates = [activity.avg_hr for activity in all_activities
                   if isinstance(activity.avg_hr, int) and not isinstance(activity.avg_hr, bool)]
    # Liczymy dni, nie wpisy rejestru: stary trening zostawiony na zegarku obok nowego
    # nie może podbijać liczby planowanych treningów ponad to, co pokazuje strona Planu.
    planned_days = [day for day in days if day.workouts]
    summary = WeekSummary(
        total_distance_km=sum(distances) if distances else None,
        total_duration_min=sum(durations) if durations else None,
        average_hr=round(sum(heart_rates) / len(heart_rates)) if heart_rates else None,
        completed_workouts=sum(any(workout.status == 'matched' for workout in day.workouts)
                               for day in planned_days),
        planned_workouts=len(planned_days),
    )
    return WeekReport(monday.isoformat(), sunday.isoformat(), today, 'local_registry', registry_status,
                      snapshot_status, timestamp, warnings, days, summary)


def get_week_report(*, now=None) -> WeekReport:
    """Wczytaj lokalny snapshot, rejestr i preferencje dla raportu tygodnia."""
    current = now or datetime.now()
    snapshot = read_snapshot_status()
    try:
        entries = list_workouts('active')
        registry_status = 'ok'
    except FileNotFoundError:
        entries = []
        registry_status = 'missing'
    except (ValueError, OSError):
        entries = []
        registry_status = 'invalid'
    return build_week_report(snapshot=snapshot, registry_entries=entries,
                             registry_status=registry_status,
                             availability=get_weekly_availability(), now=current)
