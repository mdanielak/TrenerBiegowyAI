# -*- coding: utf-8 -*-
"""Statystyki wielotygodniowe: kilometry tygodniowo i trendy sygnałów z zegarka.

Wszystko liczone jest z lokalnego snapshotu, bez sieci i bez AI. Brak pomiaru
zostaje brakiem (None), nigdy zerem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from services.data_extract import SnapshotStatus, read_snapshot_status
from services.plan_files import get_today_workout_from_plan, load_plan, week_bounds
from services.readiness import readiness_for_day
from services.strategy import Strategy, load_strategy

WEEK_OPTIONS = (4, 8, 12)
DEFAULT_WEEKS = 8
# Ostatnie dni porównywane ze średnią całego zakresu.
RECENT_DAYS = 7

# metric -> (źródło w snapshocie, pole, czy wyższa wartość jest korzystna)
_METRICS = {
    "readiness": (None, None, True),
    "rhr": ("daily_health", "rhr", False),
    "hrv": ("hrv", "last_night", True),
    "sleep": ("sleep", "score", True),
    "stress": ("daily_health", "stress_avg", False),
}


@dataclass(frozen=True)
class WeekLoad:
    monday: date
    distance_km: float
    duration_min: float
    sessions: int
    is_current: bool
    longest_km: float = 0
    planned_min: int | None = None
    phase_name: str | None = None
    phase_km: tuple | None = None
    phase_long_km: tuple | None = None


@dataclass(frozen=True)
class MetricTrend:
    key: str
    points: list  # [(iso_date, value | None)], dzień po dniu
    average: float | None
    recent_average: float | None
    higher_is_better: bool

    @property
    def measured_days(self) -> int:
        return sum(1 for _, value in self.points if value is not None)


@dataclass(frozen=True)
class StatsReport:
    status: str
    snapshot_status: SnapshotStatus | None = None
    weeks: int = DEFAULT_WEEKS
    start: date | None = None
    end: date | None = None
    weekly: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    strategy: Strategy | None = None


# Różnica ostatnich 7 dni od średniej mniejsza niż ten ułamek to „bez zmian”.
FLAT_THRESHOLD = 0.03


def trend_direction(trend) -> str | None:
    """'up', 'down', 'flat' albo None, gdy brakuje pomiarów do porównania."""
    if trend.average is None or trend.recent_average is None:
        return None
    difference = trend.recent_average - trend.average
    if abs(difference) <= abs(trend.average) * FLAT_THRESHOLD:
        return "flat"
    return "up" if difference > 0 else "down"


def normalize_weeks(value) -> int:
    """Dozwolony zakres tygodni; wszystko inne daje wartość domyślną."""
    try:
        weeks = int(value)
    except (TypeError, ValueError):
        return DEFAULT_WEEKS
    return weeks if weeks in WEEK_OPTIONS else DEFAULT_WEEKS


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _average(values) -> float | None:
    measured = [value for value in values if value is not None]
    if not measured:
        return None
    return round(sum(measured) / len(measured), 1)


def _is_run(activity) -> bool:
    return str(activity.get("type") or "").startswith("running")


def _weekly_load(activities, first_monday: date, current_monday: date, *,
                 strategy=None, planned_minutes=None) -> list[WeekLoad]:
    planned_minutes = planned_minutes or {}
    weeks = []
    monday = first_monday
    while monday <= current_monday:
        sunday = monday + timedelta(days=6)
        runs = []
        for activity in activities:
            try:
                day = date.fromisoformat(str(activity.get("date") or "")[:10])
            except ValueError:
                continue
            if monday <= day <= sunday and _is_run(activity):
                runs.append(activity)
        phase = strategy.phase_for(monday) if strategy is not None else None
        weeks.append(WeekLoad(
            monday=monday,
            distance_km=round(sum(_number(a.get("distance_km")) or 0 for a in runs), 1),
            duration_min=round(sum(_number(a.get("duration_min")) or 0 for a in runs)),
            sessions=len(runs),
            is_current=monday == current_monday,
            longest_km=round(max((_number(a.get("distance_km")) or 0 for a in runs), default=0), 1),
            planned_min=planned_minutes.get(monday),
            phase_name=phase.name if phase else None,
            phase_km=phase.km if phase else None,
            phase_long_km=phase.long_km if phase else None,
        ))
        monday += timedelta(days=7)
    return weeks


def _metric_points(data, key, days) -> list:
    source, field_name, _ = _METRICS[key]
    if key == "readiness":
        points = []
        for day in days:
            result = readiness_for_day(data, day)
            points.append((day, _number(result.get("score")) if result else None))
        return points
    records = data.get(source) or []
    by_day = {str(record.get("date")): record for record in records if isinstance(record, dict)}
    return [(day, _number((by_day.get(day) or {}).get(field_name))) for day in days]


def build_stats_report(*, snapshot, today: date, weeks: int = DEFAULT_WEEKS,
                       strategy: Strategy | None = None, planned_minutes=None) -> StatsReport:
    """Zbuduj raport z przekazanego snapshotu, bez odczytu plików."""
    weeks = normalize_weeks(weeks)
    status = snapshot.status if snapshot is not None else SnapshotStatus.MISSING
    if status is SnapshotStatus.MISSING:
        return StatsReport(status="snapshot_missing", snapshot_status=status, weeks=weeks)
    data = snapshot.data if isinstance(getattr(snapshot, "data", None), dict) else None
    if status is SnapshotStatus.INVALID or data is None:
        return StatsReport(status="snapshot_invalid", snapshot_status=status, weeks=weeks)

    current_monday, _ = week_bounds(today)
    first_monday = current_monday - timedelta(days=7 * (weeks - 1))
    days = [(first_monday + timedelta(days=offset)).isoformat()
            for offset in range((today - first_monday).days + 1)]
    recent = set(days[-RECENT_DAYS:])

    activities = [a for a in data.get("activities") or [] if isinstance(a, dict)]
    metrics = {}
    for key, (_, _, higher_is_better) in _METRICS.items():
        points = _metric_points(data, key, days)
        metrics[key] = MetricTrend(
            key=key,
            points=points,
            average=_average(value for _, value in points),
            recent_average=_average(value for day, value in points if day in recent),
            higher_is_better=higher_is_better,
        )

    return StatsReport(
        status="ok",
        snapshot_status=status,
        weeks=weeks,
        start=first_monday,
        end=today,
        weekly=_weekly_load(activities, first_monday, current_monday,
                            strategy=strategy, planned_minutes=planned_minutes),
        metrics=metrics,
        strategy=strategy,
    )


def planned_minutes_by_week(first_monday: date, current_monday: date) -> dict:
    """Zaplanowane minuty treningów (bez odpoczynku) w każdym tygodniu z zapisanym planem.

    Dzień po dniu, bo rewizja w środku tygodnia zastępuje tylko część dni.
    """
    result = {}
    monday = first_monday
    while monday <= current_monday:
        total, covered = 0, False
        for offset in range(7):
            day = datetime.combine(monday + timedelta(days=offset), datetime.min.time())
            try:
                plan = load_plan(day)
            except ValueError:
                plan = None
            if not plan:
                continue
            covered = True
            workout = get_today_workout_from_plan(plan, day) or {}
            if workout.get("type") != "rest":
                total += int(_number(workout.get("duration_min")) or 0)
        if covered:
            result[monday] = total
        monday += timedelta(days=7)
    return result


def get_stats_report(weeks: int = DEFAULT_WEEKS, *, now=None) -> StatsReport:
    """Raport statystyk z lokalnego snapshotu, planów i strategii dla bieżącego dnia."""
    current = now or datetime.now()
    weeks = normalize_weeks(weeks)
    current_monday, _ = week_bounds(current.date())
    first_monday = current_monday - timedelta(days=7 * (weeks - 1))
    return build_stats_report(
        snapshot=read_snapshot_status(),
        today=current.date(),
        weeks=weeks,
        strategy=load_strategy(),
        planned_minutes=planned_minutes_by_week(first_monday, current_monday),
    )
