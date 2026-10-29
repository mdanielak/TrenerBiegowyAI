# -*- coding: utf-8 -*-
"""Postęp wobec celu długoterminowego: odliczanie, faza strategii i kryteria gotowości.

Liczone z lokalnego snapshotu, bez AI. Kryteria są przybliżone: snapshot zawiera
całe aktywności, bez splitów, więc „test 10 km” to najszybszy bieg o długości ~10 km.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from services.data_extract import SnapshotStatus, read_snapshot_status
from services.plan_files import week_bounds
from services.stats import _is_run, _number
from services.strategy import Strategy, load_strategy
from services.wizard import _distance_key

# Dystanse celów z kreatora; „inny dystans” i „bez zawodów” nie mają tempa.
RACE_KM = {"5k": (5.0, "5 km"), "10k": (10.0, "10 km"), "hm": (21.0975, "21,1 km"), "marathon": (42.195, "42,2 km")}
LONG_RUN_WINDOW_DAYS = 56
FREQUENCY_WEEKS = 4
TEST_DISTANCE_KM = (9.8, 10.5)


@dataclass(frozen=True)
class Criterion:
    label: str
    target: str
    actual: str
    met: bool | None  # None: brak danych, żeby to rozstrzygnąć


@dataclass(frozen=True)
class PhaseStep:
    number: int
    name: str
    start: date
    end: date
    is_current: bool
    is_past: bool


@dataclass(frozen=True)
class GoalReport:
    status: str
    title: str = ""
    target_date: date | None = None
    days_left: int | None = None
    target_time: str | None = None
    target_pace: str | None = None
    distance_label: str | None = None
    record: str | None = None
    phases: list = field(default_factory=list)
    current_phase: PhaseStep | None = None
    week_number: int | None = None
    total_weeks: int | None = None
    criteria: list = field(default_factory=list)


def _clock(seconds: float) -> str:
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _seconds(text) -> int | None:
    match = re.fullmatch(r"\s*(?:(\d+):)?(\d{1,2}):(\d{2})\s*", str(text or ""))
    if not match:
        return None
    hours, minutes, secs = (int(part) if part else 0 for part in match.groups())
    return hours * 3600 + minutes * 60 + secs


def _target_date(profile, strategy) -> date | None:
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(profile.get("target_date") or ""))
    if match:
        try:
            return date.fromisoformat(match.group(0))
        except ValueError:
            pass
    return strategy.phases[-1].end if strategy and strategy.phases else None


def _runs(activities, since: date, until: date) -> list[tuple[date, dict]]:
    runs = []
    for activity in activities:
        try:
            day = date.fromisoformat(str(activity.get("date") or "")[:10])
        except ValueError:
            continue
        if since <= day <= until and _is_run(activity):
            runs.append((day, activity))
    return runs


def _km(value: float) -> str:
    text = f"{value:.1f}".replace(".", ",")
    return text[:-2] if text.endswith(",0") else text


def _criteria(strategy: Strategy, activities, today: date) -> list[Criterion]:
    criteria = []
    current_monday, _ = week_bounds(today)

    if strategy.long_run_target:
        low, high = strategy.long_run_target
        recent = _runs(activities, today - timedelta(days=LONG_RUN_WINDOW_DAYS), today)
        longest = max((_number(a.get("distance_km")) or 0 for _, a in recent), default=0)
        criteria.append(Criterion(
            label="Długi bieg",
            target=f"regularnie {low}–{high} km",
            actual=f"najdłuższy w 8 tygodniach: {_km(longest)} km" if longest else "brak biegów w 8 tygodniach",
            met=longest >= low if longest else False,
        ))

    if strategy.test_10k_seconds:
        low, high = strategy.test_10k_seconds
        candidates = []
        for day, activity in _runs(activities, date.min, today):
            distance = _number(activity.get("distance_km")) or 0
            minutes = _number(activity.get("duration_min"))
            if TEST_DISTANCE_KM[0] <= distance <= TEST_DISTANCE_KM[1] and minutes:
                candidates.append((minutes * 60 * 10 / distance, day))
        best = min(candidates, default=None)
        criteria.append(Criterion(
            label="Test 10 km",
            target=f"około {_clock(low)}–{_clock(high)}",
            actual=(f"najszybszy bieg ~10 km: {_clock(best[0])} ({best[1].day}.{best[1].month:02d})"
                    if best else "brak biegu ~10 km w danych"),
            met=best[0] <= high if best else None,
        ))

    if strategy.runs_per_week:
        low, high = strategy.runs_per_week
        first = current_monday - timedelta(days=7 * FREQUENCY_WEEKS)
        count = len(_runs(activities, first, current_monday - timedelta(days=1)))
        average = count / FREQUENCY_WEEKS
        criteria.append(Criterion(
            label="Częstotliwość",
            target=f"{low}–{high} biegów w tygodniu",
            actual=f"średnio {_km(average)} w 4 pełnych tygodniach",
            met=average >= low,
        ))

    phase = strategy.phase_for(today)
    if phase is not None and phase.km:
        low, high = phase.km
        last_monday = current_monday - timedelta(days=7)
        week_km = sum(_number(a.get("distance_km")) or 0
                      for _, a in _runs(activities, last_monday, current_monday - timedelta(days=1)))
        criteria.append(Criterion(
            label="Objętość fazy",
            target=f"{phase.name}: zwykle {low}–{high} km",
            actual=f"ostatni pełny tydzień: {_km(week_km)} km",
            met=low <= week_km,
        ))
    return criteria


def build_goal_report(*, snapshot, strategy: Strategy | None, profile: dict, today: date) -> GoalReport:
    """Zbuduj raport celu z przekazanych danych, bez odczytu plików."""
    if strategy is None:
        return GoalReport(status="strategy_missing")
    if snapshot is None or snapshot.status is SnapshotStatus.MISSING:
        return GoalReport(status="snapshot_missing")
    data = snapshot.data if isinstance(getattr(snapshot, "data", None), dict) else None
    if snapshot.status is SnapshotStatus.INVALID or data is None:
        return GoalReport(status="snapshot_invalid")

    steps = [PhaseStep(index + 1, phase.name, phase.start, phase.end,
                       is_current=phase.start <= today <= phase.end, is_past=phase.end < today)
             for index, phase in enumerate(strategy.phases)]
    current = next((step for step in steps if step.is_current), None)
    target_day = _target_date(profile, strategy)
    target_seconds = _seconds(profile.get("target_time"))
    race = RACE_KM.get(_distance_key(profile.get("target_race")))
    activities = [a for a in data.get("activities") or [] if isinstance(a, dict)]

    return GoalReport(
        status="ok",
        title=strategy.title,
        target_date=target_day,
        days_left=(target_day - today).days if target_day else None,
        target_time=profile.get("target_time") or None,
        target_pace=(_clock(target_seconds / race[0]) if target_seconds and race else None),
        distance_label=race[1] if race else None,
        record=profile.get("current_hm_record") or None,
        phases=steps,
        current_phase=current,
        week_number=(today - current.start).days // 7 + 1 if current else None,
        total_weeks=(current.end - current.start).days // 7 + 1 if current else None,
        criteria=_criteria(strategy, activities, today),
    )


def get_goal_report(*, now=None) -> GoalReport:
    """Raport celu z lokalnego snapshotu, strategii i profilu."""
    from trainer.profile_store import load_profile

    current = now or datetime.now()
    try:
        profile = load_profile()
    except (FileNotFoundError, OSError, ValueError):
        profile = {}
    return build_goal_report(snapshot=read_snapshot_status(), strategy=load_strategy(),
                             profile=profile, today=current.date())
