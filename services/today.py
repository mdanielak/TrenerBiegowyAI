"""Dane dla lokalnego widoku planu i gotowości na dziś."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from services.data_extract import SnapshotReadResult, SnapshotStatus, read_snapshot_status
from services.activity_matching import find_activity_for_workout
from services.readiness import compute_readiness_breakdown, record_for_day, signal_trends
from services.plan_files import find_current_plan, get_today_workout_from_plan
from services.workout_registry import list_workouts
from trainer.preferences import get_active_pause, get_weekly_availability
from trainer.core import check_hrv_alert
from trainer.profile_store import load_profile


_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass
class TodayReport:
    status: str
    date: str
    weekday_index: int
    snapshot_status: SnapshotStatus | None
    planned: dict | None
    yesterday_date: str
    yesterday_activities: list[dict]
    readiness: dict | None
    signals: dict
    availability: dict | None
    suggestion: str
    snapshot_timestamp: str | None = None
    trends: dict = field(default_factory=dict)
    today_activities: list = field(default_factory=list)
    execution: dict | None = None
    active_pause: dict | None = None
    plan_workout: dict | None = None
    hrv_alert: dict | None = None
    other_planned: list = field(default_factory=list)
    next_workout: dict | None = None


def _today_registry_entries(today: str):
    """Zwróć aktywne treningi na datę z aktualnej projekcji rejestru."""
    return [entry for entry in list_workouts("active") if entry.get("date") == today]


def _execution(*, workouts, today_activities, today):
    """Zwróć wykonanie pierwszego treningu zaplanowanego na dziś."""
    if not workouts:
        return None

    workout = workouts[0]
    matching_workout = {**workout, "date": workout.get("date") or today}
    activity, match_method = find_activity_for_workout(
        workout=matching_workout,
        activities=today_activities,
    )
    happened = activity is not None
    execution = {
        "happened": happened,
        "match_method": match_method,
        "certain": match_method != "ambiguous",
        "activity_id": activity.get("activity_id") if happened else None,
        "distance_km": activity.get("distance_km") if happened else None,
        "duration_min": activity.get("duration_min") if happened else None,
        "avg_hr": activity.get("avg_hr") if happened else None,
        "max_hr": activity.get("max_hr") if happened else None,
        "pace": activity.get("pace") if happened else None,
        "review_key": f"{matching_workout['date']}:{workout.get('workout_id')}"
        if workout.get("workout_id") is not None else f"{matching_workout['date']}:{workout.get('name')}",
    }
    if len(workouts) > 1:
        execution["planned_count"] = len(workouts)
    return execution


def build_today_report(*, snapshot: SnapshotReadResult | None, planned, availability, now,
                       active_pause: dict | None = None, plan_workout: dict | None = None,
                       next_workout: dict | None = None) -> TodayReport:
    """Zbuduj raport wyłącznie z przekazanych danych, bez efektów ubocznych."""
    today = now.date().isoformat()
    yesterday = now.date().fromordinal(now.date().toordinal() - 1).isoformat()
    weekday_index = now.weekday()
    empty = TodayReport(
        status="profile_missing" if snapshot is None else {
            SnapshotStatus.MISSING: "snapshot_missing",
            SnapshotStatus.INVALID: "snapshot_invalid",
        }.get(snapshot.status, "ok"),
        date=today,
        weekday_index=weekday_index,
        snapshot_status=None if snapshot is None else snapshot.status,
        planned=None,
        yesterday_date=yesterday,
        yesterday_activities=[],
        readiness=None,
        signals={"sleep_score": None, "hrv_status": None, "rhr": None, "stress_avg": None},
        availability=None,
        suggestion="rest",
        snapshot_timestamp=None,
        trends={},
        today_activities=[],
        execution=None,
        active_pause=active_pause,
        plan_workout=plan_workout,
        next_workout=next_workout,
    )
    if empty.status != "ok":
        return empty

    data = snapshot.data or {}
    day_activities = sorted(
        (item for item in data.get("activities", []) if str(item.get("date", ""))[:10] == yesterday),
        key=lambda item: str(item.get("date", "")),
    )
    today_activities = sorted(
        (item for item in data.get("activities", []) if str(item.get("date", ""))[:10] == today),
        key=lambda item: str(item.get("date", "")),
    )
    planned_workouts = planned if isinstance(planned, list) else [planned] if planned else []
    # Tylko pomiary z dzisiejszą datą: gdy pobranie dzisiejszych danych się nie uda,
    # wczorajszy sen nie może udawać dzisiejszego.
    health = record_for_day(data.get("daily_health"), today)
    sleep = record_for_day(data.get("sleep"), today)
    hrv = record_for_day(data.get("hrv"), today)
    readiness = compute_readiness_breakdown({
        "daily_health": [health] if health else [], "sleep": [sleep] if sleep else [], "hrv": [hrv] if hrv else []})
    trends = signal_trends(data, today)
    signals = {
        "sleep_score": sleep.get("score"),
        "hrv_status": hrv.get("status"),
        "rhr": health.get("rhr"),
        "stress_avg": health.get("stress_avg"),
    }
    if active_pause is not None:
        suggestion = "medical_rest"
        if isinstance(availability, dict):
            availability = {**availability, "available": False, "pause": active_pause}
    else:
        suggestion = "follow_plan" if planned and readiness["level"] != "not_ready" else "rest"
    return TodayReport(
        status="ok",
        date=today,
        weekday_index=weekday_index,
        snapshot_status=snapshot.status,
        planned=planned_workouts[0] if planned_workouts else None,
        yesterday_date=yesterday,
        yesterday_activities=day_activities,
        readiness=readiness,
        signals=signals,
        availability=availability,
        suggestion=suggestion,
        snapshot_timestamp=data.get("timestamp"),
        trends=trends,
        today_activities=today_activities,
        execution=_execution(
            workouts=planned_workouts,
            today_activities=today_activities,
            today=today,
        ),
        active_pause=active_pause,
        plan_workout=plan_workout,
        hrv_alert=check_hrv_alert(data.get("hrv") or []),
        other_planned=[w.get("name") or "Trening" for w in planned_workouts[1:] if isinstance(w, dict)],
        next_workout=next_workout,
    )


def _today_plan_workout(current):
    """Trening z zapisanego planu AI na dziś; rejestr Garmina to osobne źródło."""
    try:
        plan = find_current_plan(current)
    except (OSError, ValueError):
        return None
    if not plan:
        return None
    try:
        return get_today_workout_from_plan(plan, current)
    except (KeyError, TypeError):
        return None


def _next_plan_workout(current):
    """Najbliższy trening z planu po dzisiejszym dniu: z tego albo z następnego tygodnia."""
    today = current.date().isoformat()
    for offset in (0, 7):
        try:
            plan = find_current_plan(current + timedelta(days=offset))
        except (OSError, ValueError):
            continue
        upcoming = sorted((w for w in (plan or {}).get("workouts") or []
                           if isinstance(w, dict) and str(w.get("date") or "") > today and w.get("type") != "rest"),
                          key=lambda w: str(w.get("date")))
        if upcoming:
            return upcoming[0]
    return None


def get_today_report(*, now=None) -> TodayReport:
    """Wczytaj lokalne zależności i zwróć raport na wskazany dzień."""
    current = now or datetime.now()
    try:
        load_profile()
    except FileNotFoundError:
        return build_today_report(snapshot=None, planned=None, availability=None, now=current)

    snapshot = read_snapshot_status()
    if snapshot.status in (SnapshotStatus.MISSING, SnapshotStatus.INVALID):
        return build_today_report(snapshot=snapshot, planned=None, availability=None, now=current)

    planned = _today_registry_entries(current.date().isoformat())
    availability = get_weekly_availability(_DAYS[current.weekday()])
    active_pause = get_active_pause(current.date().isoformat())
    return build_today_report(
        snapshot=snapshot,
        planned=planned,
        availability=availability,
        now=current,
        active_pause=active_pause,
        plan_workout=_today_plan_workout(current),
        next_workout=_next_plan_workout(current),
    )
