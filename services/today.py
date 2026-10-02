"""Dane dla lokalnego widoku planu i gotowości na dziś."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from services.data_extract import SnapshotReadResult, SnapshotStatus, read_snapshot_status
from services.readiness import compute_readiness_breakdown
from services.workout_registry import list_workouts
from trainer.preferences import get_weekly_availability
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


def _today_registry_entry(today: str):
    """Zwróć najnowszy aktywny trening na datę z aktualnej projekcji rejestru."""
    return next(
        (entry for entry in list_workouts("active") if entry.get("date") == today),
        None,
    )


def build_today_report(*, snapshot: SnapshotReadResult | None, planned, availability, now) -> TodayReport:
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
    )
    if empty.status != "ok":
        return empty

    data = snapshot.data or {}
    day_activities = sorted(
        (item for item in data.get("activities", []) if str(item.get("date", ""))[:10] == yesterday),
        key=lambda item: str(item.get("date", "")),
    )
    readiness = compute_readiness_breakdown(data)
    health = (data.get("daily_health") or [{}])[0]
    sleep = (data.get("sleep") or [{}])[0]
    hrv = (data.get("hrv") or [{}])[0]
    signals = {
        "sleep_score": sleep.get("score"),
        "hrv_status": hrv.get("status"),
        "rhr": health.get("rhr"),
        "stress_avg": health.get("stress_avg"),
    }
    suggestion = "follow_plan" if planned and readiness["level"] != "not_ready" else "rest"
    return TodayReport(
        status="ok",
        date=today,
        weekday_index=weekday_index,
        snapshot_status=snapshot.status,
        planned=planned,
        yesterday_date=yesterday,
        yesterday_activities=day_activities,
        readiness=readiness,
        signals=signals,
        availability=availability,
        suggestion=suggestion,
        snapshot_timestamp=data.get("timestamp"),
    )


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

    planned = _today_registry_entry(current.date().isoformat())
    availability = get_weekly_availability(_DAYS[current.weekday()])
    return build_today_report(
        snapshot=snapshot,
        planned=planned,
        availability=availability,
        now=current,
    )
