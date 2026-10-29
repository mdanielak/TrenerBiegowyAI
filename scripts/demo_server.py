# -*- coding: utf-8 -*-
"""Aplikacja na zmyślonych danych — do zrzutów ekranu w README.

Żaden dostawca nie czyta `local/`, `~/.GarminDb` ani `.env`: profil, snapshot zegarka,
stan AI, dziennik i zadania są przykładowe albo leżą w katalogu tymczasowym.

    python scripts/demo_server.py          # http://127.0.0.1:8020
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

from api.main import create_app  # noqa: E402
from services.ai_status import record_test  # noqa: E402
from services.data_extract import SnapshotReadResult, SnapshotStatus  # noqa: E402
from services.jobs import JobStore  # noqa: E402
from services.today import build_today_report  # noqa: E402

PORT = 8020
FLOORS = {"z1": 98, "z2": 120, "z3": 138, "z4": 156, "z5": 172}
PROFILE = {"name": "Ala", "age": 34, "hr_max": 188, "hr_rest": 49, "hr_zone_floors": FLOORS,
           "hr_zones": "Z1 98-119, Z2 120-137, Z3 138-155, Z4 156-171, Z5 172-188",
           "target_race": "Półmaraton", "target_time": "1:55:00", "training_frequency": "4 treningi w tygodniu"}
GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/"


def _snapshot(today):
    day = lambda offset: (today - timedelta(days=offset)).isoformat()  # noqa: E731
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "activities": [{"date": f"{day(1)} 18:05", "name": "Bieg", "type": "running/generic",
                        "distance_km": 8.2, "duration_min": 49.0, "avg_hr": 136, "max_hr": 151}],
        "daily_health": [{"date": day(0), "rhr": 48, "stress_avg": 24}, {"date": day(1), "rhr": 50, "stress_avg": 29}],
        "sleep": [{"date": day(0), "score": 86, "total_h": 7.4}, {"date": day(1), "score": 84, "total_h": 7.1}],
        "hrv": [{"date": day(0), "status": "BALANCED", "last_night": 64, "baseline_low": 55, "baseline_high": 70},
                {"date": day(1), "status": "BALANCED", "last_night": 61, "baseline_low": 55, "baseline_high": 70}],
    }


def build_demo_app():
    now = datetime.now()
    today = now.date()
    workdir = Path(tempfile.mkdtemp(prefix="trener-demo-"))
    record_test(ok=True, base_url=GEMINI, model="gemini-3.8-flash", path=workdir / "ai_status.json")
    planned = {"workout_id": 1, "date": today.isoformat(), "name": "Łatwy 45 min – Z2",
               "spec": {"kind": "hr_zone_run", "duration_min": 45, "zone_number": 2, "warmup_min": 6,
                        "warmup_pace_faster": "6:50", "warmup_pace_slower": "8:00"}}

    def report():
        return build_today_report(
            snapshot=SnapshotReadResult(SnapshotStatus.FRESH, _snapshot(today)), planned=[planned],
            availability={"available": True, "min_minutes": 40, "max_minutes": 60}, now=now)

    return create_app(
        report_provider=report,
        profile_provider=lambda: PROFILE,
        journal_path=workdir / "journal.jsonl",
        ai_status_path=workdir / "ai_status.json",
        ai_settings_provider=lambda: {"base_url": GEMINI, "model": "gemini-3.8-flash",
                                      "key_present": True, "export_enabled": True},
        ai_env_path=workdir / "demo.env",
        job_store=JobStore(workdir / "jobs"),
        lock_directory=workdir / "locks",
        recommendation_loader=lambda **_: None,
        review_loader=lambda **_: None,
        registry_provider=lambda: [],
        garmin_token_check=lambda: True,
    )


if __name__ == "__main__":
    uvicorn.run(build_demo_app(), host="127.0.0.1", port=PORT, log_level="warning")
