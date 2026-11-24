# -*- coding: utf-8 -*-
"""Aplikacja na zmyślonych danych — do zrzutów ekranu w README i testów wizualnych.

Żaden dostawca nie czyta `local/`, `~/.GarminDb` ani `.env`: profil, snapshot zegarka,
plan tygodnia, strategia celu, stan AI, dziennik, notatki i zadania są przykładowe
albo leżą w katalogu tymczasowym.

    python scripts/demo_server.py          # http://127.0.0.1:8020
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

import services.ai_notes as ai_notes_service  # noqa: E402
import services.plan_conflicts as plan_conflicts_service  # noqa: E402
import services.plan_files as plan_files_service  # noqa: E402
import services.strategy as strategy_service  # noqa: E402
import trainer.config as trainer_config  # noqa: E402
import trainer.preferences as trainer_preferences  # noqa: E402
from api.main import create_app  # noqa: E402
from services.ai_status import record_test  # noqa: E402
from services.data_extract import SnapshotReadResult, SnapshotStatus  # noqa: E402
from services.goal import build_goal_report  # noqa: E402
from services.jobs import JobStore  # noqa: E402
from services.plan_files import week_bounds  # noqa: E402
from services.runner_level import current_runner  # noqa: E402
from services.stats import build_stats_report  # noqa: E402
from services.strategy import parse_strategy  # noqa: E402
from services.today import build_today_report  # noqa: E402

PORT = 8020
FLOORS = {"z1": 98, "z2": 120, "z3": 138, "z4": 156, "z5": 172}
PROFILE = {
    "name": "Ala",
    "age": 34,
    "hr_max": 188,
    "hr_rest": 49,
    "hr_zone_floors": FLOORS,
    "hr_zones": "Z1 98-119, Z2 120-137, Z3 138-155, Z4 156-171, Z5 172-188",
    "target_race": "Półmaraton",
    "target_time": "1:55:00",
    "training_frequency": "4 treningi w tygodniu",
}
AVAILABILITY = {
    "mon": {"available": True, "min_minutes": 35, "max_minutes": 45},
    "tue": {"available": True, "min_minutes": 40, "max_minutes": 60},
    "wed": {"available": False, "min_minutes": 0, "max_minutes": 0},
    "thu": {"available": True, "min_minutes": 35, "max_minutes": 50},
    "fri": {"available": True, "min_minutes": 35, "max_minutes": 45},
    "sat": {"available": False, "min_minutes": 0, "max_minutes": 0},
    "sun": {"available": True, "min_minutes": 60, "max_minutes": 90},
}
GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/"


def _snapshot(today):
    day = lambda offset: (today - timedelta(days=offset)).isoformat()  # noqa: E731
    activities = [
        {"date": f"{day(1)} 18:05", "name": "Bieg", "type": "running/generic",
         "distance_km": 6.4, "duration_min": 38.0, "avg_hr": 134, "max_hr": 149},
        {"date": f"{day(4)} 08:15", "name": "Bieg", "type": "running/generic",
         "distance_km": 11.2, "duration_min": 67.0, "avg_hr": 137, "max_hr": 154},
    ]
    for week_offset in range(1, 7):
        for step in (2, 4, 6):
            offset = week_offset * 7 + step
            dist = 7.5 + (week_offset % 3) * 1.4 + (2.5 if step == 6 else 0.0)
            activities.append({
                "date": f"{day(offset)} 17:30",
                "name": "Bieg",
                "type": "running/generic",
                "distance_km": round(dist, 1),
                "duration_min": round(dist * 6.0, 1),
                "avg_hr": 135,
                "max_hr": 152,
            })
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "activities": activities,
        "daily_health": [{"date": day(0), "rhr": 48, "stress_avg": 24},
                         {"date": day(1), "rhr": 50, "stress_avg": 29}]
                        + [{"date": day(offset), "rhr": 47 + (offset % 3), "stress_avg": 25 + (offset % 4)}
                           for offset in range(2, 28)],
        "sleep": [{"date": day(0), "score": 86, "total_h": 7.4},
                  {"date": day(1), "score": 84, "total_h": 7.1}]
                 + [{"date": day(offset), "score": 80 + (offset % 9), "total_h": 7.2} for offset in range(2, 28)],
        "hrv": [{"date": day(offset), "status": "LOW", "last_night": 48 + offset,
                 "baseline_low": 55, "baseline_high": 70} for offset in range(6)]
               + [{"date": day(offset), "status": "BALANCED", "last_night": 60 + (offset % 5),
                   "baseline_low": 55, "baseline_high": 70} for offset in range(6, 28)],
    }


def _demo_plan(today):
    monday, sunday = week_bounds(today)
    day_keys = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    workouts = [
        {"day": "mon", "date": (monday + timedelta(days=0)).isoformat(), "type": "rest", "name": "Odpoczynek",
         "duration_min": None, "distance_km": None, "hr_zone": None, "pace_target": None},
        {"day": "tue", "date": (monday + timedelta(days=1)).isoformat(), "type": "easy", "name": "Łatwy 45 min – Z2",
         "duration_min": 45, "distance_km": 7.2, "hr_zone": "Z2", "hr_target": "120–137 bpm",
         "description": "Spokojny bieg w tempie rozmowy.", "garmin_upload": True, "garmin_workout_id": 101},
        {"day": "wed", "date": (monday + timedelta(days=2)).isoformat(), "type": "rest", "name": "Mobilność 15 min",
         "duration_min": None, "distance_km": None, "hr_zone": None, "pace_target": None},
        {"day": "thu", "date": (monday + timedelta(days=3)).isoformat(), "type": "tempo", "name": "Bieg progowy 35 min",
         "duration_min": 35, "distance_km": 6.4, "hr_zone": "Z4", "pace_target": "5:15–5:25 /km",
         "description": "10 min rozgrzewki, 15 min w tempie progowym, 10 min schłodzenia.", "garmin_upload": False},
        {"day": "fri", "date": (monday + timedelta(days=4)).isoformat(), "type": "easy", "name": "Spokojny bieg 35 min – Z2",
         "duration_min": 35, "distance_km": 5.5, "hr_zone": "Z2", "hr_target": "120–137 bpm",
         "description": "Luźne wybieganie regeneracyjne.", "garmin_upload": True, "garmin_workout_id": 102},
        {"day": "sat", "date": (monday + timedelta(days=5)).isoformat(), "type": "rest", "name": "Odpoczynek",
         "duration_min": None, "distance_km": None, "hr_zone": None, "pace_target": None},
        {"day": "sun", "date": (monday + timedelta(days=6)).isoformat(), "type": "long", "name": "Długi bieg 70 min – Z2",
         "duration_min": 70, "distance_km": 11.5, "hr_zone": "Z2", "hr_target": "120–137 bpm",
         "description": "Dłuższy bieg tlenowy bez przyspieszania.", "garmin_upload": False},
    ]
    assert len(workouts) == len(day_keys)
    return {
        "start_date": monday.isoformat(),
        "end_date": sunday.isoformat(),
        "focus": "Stabilizacja bazy tlenowej i spokojny akcent progowy",
        "summary": "Cztery treningi w tygodniu z jednym kontrolowanym biegiem progowym i dłuższym biegiem w niedzielę.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "week_decision": "utrzymaj",
        "week_decision_reason": "Objętość jest stabilna; przy niższym HRV pilnuj spokojnego tętna na biegach łatwych.",
        "workouts": workouts,
    }


def _demo_strategy(today):
    start = today - timedelta(days=28)
    end = today + timedelta(days=140)
    target_date = end.isoformat()
    sample = f"""# Plan: Półmaraton {PROFILE['target_time']}

## Periodyzacja: {start.isoformat()}—{target_date}

| Faza | Daty robocze | Objętość i long run | Akcent |
|---|---|---|---|
| Baza tlenowa | {start.day}.{start.month:02d}.{start.year}—{(start + timedelta(days=55)).day}.{(start + timedelta(days=55)).month:02d}.{(start + timedelta(days=55)).year} | zwykle 24-32 km, long 11-14 km | 4 biegi/tydz. |
| Budowanie | {(start + timedelta(days=56)).day}.{(start + timedelta(days=56)).month:02d}.{(start + timedelta(days=56)).year}—{(start + timedelta(days=111)).day}.{(start + timedelta(days=111)).month:02d}.{(start + timedelta(days=111)).year} | zwykle 30-38 km, long 14-18 km | tempo i progi |
| Szczyt i taper | {(start + timedelta(days=112)).day}.{(start + timedelta(days=112)).month:02d}.{(start + timedelta(days=112)).year}—{end.day}.{end.month:02d}.{end.year} | redukcja objętości, long 10-12 km | świeżość |

## Kryteria gotowości do celu {PROFILE['target_time']}

Potrzebne są regularne long runy 16-20 km. Potwierdzeniem test 10 km około **50:00-52:00**.
"""
    return parse_strategy(sample), target_date


def _isolate_paths(workdir: Path) -> None:
    """Przekieruj modułowe ścieżki na katalog tymczasowy, by żadna trasa nie dotykała dysku projektu."""
    plans_dir = workdir / "training-plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    demo_settings = replace(
        trainer_config.SETTINGS,
        local_dir=workdir,
        data_latest=workdir / "data_latest.json",
        runner_profile_local=workdir / "runner_profile.json",
        memory_dir=workdir / "memory",
        workout_registry=workdir / "workout_registry.json",
        training_plans_dir=plans_dir,
        ai_base_url=GEMINI,
        ai_api_key="demo-key",
        ai_model="gemini-3.8-flash",
        ai_data_export_enabled=True,
    )
    trainer_config.SETTINGS = demo_settings
    trainer_preferences.SETTINGS = demo_settings
    ai_notes_service.NOTES_PATH = workdir / "ai-notes.jsonl"
    plan_files_service.TRAINING_PLANS_DIR = plans_dir
    plan_conflicts_service.TRAINING_PLANS_DIR = plans_dir
    strategy_service.STRATEGY_PATH = plans_dir / "long-term" / "strategia.md"


def build_demo_app():
    now = datetime.now()
    today = now.date()
    workdir = Path(tempfile.mkdtemp(prefix="trener-demo-"))
    _isolate_paths(workdir)
    trainer_preferences.save_preferences({
        "days": AVAILABILITY,
        "max_quality_sessions_per_week": 1,
        "planned_pauses": [],
    })

    snap_result = SnapshotReadResult(SnapshotStatus.FRESH, _snapshot(today))
    strategy, target_date = _demo_strategy(today)
    profile = {**PROFILE, "target_date": target_date, "current_hm_record": "1:59:30"}
    demo_plan = _demo_plan(today)

    record_test(ok=True, base_url=GEMINI, model="gemini-3.8-flash", path=workdir / "ai_status.json")
    planned = {
        "workout_id": 1,
        "date": today.isoformat(),
        "name": "Łatwy 45 min – Z2",
        "spec": {
            "kind": "hr_zone_run",
            "duration_min": 45,
            "zone_number": 2,
            "warmup_min": 6,
            "warmup_pace_faster": "6:50",
            "warmup_pace_slower": "8:00",
        },
    }

    def report():
        return build_today_report(
            snapshot=snap_result,
            planned=[planned],
            availability={"available": True, "min_minutes": 40, "max_minutes": 60},
            now=now,
        )

    def stats_provider(weeks: int):
        return build_stats_report(snapshot=snap_result, today=today, weeks=weeks, strategy=strategy, planned_minutes={})

    def goal_provider():
        return build_goal_report(snapshot=snap_result, strategy=strategy, profile=profile, today=today)

    return create_app(
        report_provider=report,
        stats_report_provider=stats_provider,
        goal_report_provider=goal_provider,
        snapshot_provider=lambda: snap_result,
        profile_provider=lambda: profile,
        availability_provider=lambda: AVAILABILITY,
        plan_provider=lambda monday_iso: demo_plan if monday_iso == demo_plan["start_date"] else None,
        runner_provider=lambda: current_runner(snapshot_provider=lambda: snap_result, profile_provider=lambda: profile, today=today),
        journal_path=workdir / "journal.jsonl",
        ai_status_path=workdir / "ai_status.json",
        ai_settings_provider=lambda: {"base_url": GEMINI, "model": "gemini-3.8-flash",
                                      "key_present": True, "export_enabled": True},
        ai_env_path=workdir / "demo.env",
        job_store=JobStore(workdir / "jobs"),
        lock_directory=workdir / "locks",
        recommendation_loader=lambda **_: None,
        recommendation_history=lambda **_: [],
        review_loader=lambda **_: None,
        registry_provider=lambda: [],
        garmin_token_check=lambda: True,
    )


if __name__ == "__main__":
    uvicorn.run(build_demo_app(), host="127.0.0.1", port=PORT, log_level="warning")
