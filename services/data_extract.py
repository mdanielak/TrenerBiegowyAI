# -*- coding: utf-8 -*-
"""
Data extraction and synchronization services.

Extracts training data from GarminDB SQLite databases and exports to JSON.
Importable from CLI, tests, and future API.
"""
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import sqlite3
import sys

from trainer.core import pace_str, parse_timedelta, check_hrv_alert

logger = logging.getLogger(__name__)
from trainer.config import (
    PROJECT_ROOT, ACT_DB, MAIN_DB, DATA_LATEST,
    GARMINDB_SYNC_TIMEOUT, GARMINDB_FRESH_TIMEOUT, SNAPSHOT_TTL_SECONDS,
    GARMIN_EMAIL,
)
from trainer.garmin_auth import ensure_garmindb_config, ensure_token

class GarminDBSyncError(RuntimeError):
    """GarminDB CLI did not complete, so its database snapshot is unsafe to export."""


class SnapshotStatus(str, Enum):
    MISSING = "missing"
    INVALID = "invalid"
    STALE = "stale"
    FRESH = "fresh"


@dataclass(frozen=True)
class SnapshotReadResult:
    status: SnapshotStatus
    data: dict | None = None
    error: Exception | None = None


class SyncStatus(str, Enum):
    FULL = "full"
    PARTIAL = "partial"


def _find_python():
    """Use the interpreter that launched this portable application."""
    return sys.executable


def _find_garmindb_cli():
    """Find garmindb_cli.py in local tools, GarminDB, then PATH."""
    local_script = os.path.join(PROJECT_ROOT, 'local', 'tools', 'garmindb_cli.py')
    if os.path.isfile(local_script):
        return local_script
    legacy_script = os.path.join(PROJECT_ROOT, 'GarminDB', 'scripts', 'garmindb_cli.py')
    if os.path.isfile(legacy_script):
        return legacy_script
    import shutil
    on_path = shutil.which('garmindb_cli')
    if on_path:
        return on_path
    raise FileNotFoundError(
        "garmindb_cli.py not found. Ensure garmindb is installed: pip install garmindb"
    )


def _garmindb_log_dir():
    """Create the runtime log directory before GarminDB writes its relative log."""
    log_dir = PROJECT_ROOT / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


# GarminDB's --latest never fetches the current day. It computes
#   date = last_ts - 1 day;  days = (today - date).days
# then iterates range(0, days), so the newest day it requests is yesterday.
# Today's sleep/HRV/RHR/steps are therefore never downloaded on the day they
# become available. Fetch today explicitly before running the CLI.
_DOWNLOAD_TODAY_SNIPPET = r'''
import datetime, logging, sys
logging.disable(logging.INFO)
from garmindb.garmin_connect_config_manager import GarminConnectConfigManager
from garmindb.download import Download

cfg = GarminConnectConfigManager()
dl = Download(cfg)
if not dl.login():
    sys.exit("Garmin Connect login failed")
today = datetime.date.today()
dl.get_sleep(cfg.get_sleep_dir(), today, 1, True)
dl.get_hrv(cfg.get_rhr_dir(), today, 1, True)
dl.get_rhr(cfg.get_rhr_dir(), today, 1, True)
dl.get_daily_summaries(cfg.get_monitoring_dir, today, 1, True)
dl.get_hydration(cfg.get_monitoring_dir, today, 1, True)
dl.get_monitoring(cfg.get_monitoring_dir, today, 1)
'''


def download_today(timeout=300, cwd=None):
    """Download today's monitoring data (sleep, HRV, RHR, summary) from Garmin.

    Workaround for the GarminDB off-by-one described above. Failures are logged
    and swallowed — a network hiccup here must not abort the whole sync.
    """
    ensure_garmindb_config(GARMIN_EMAIL)
    ensure_token()
    python = _find_python()
    logger.info("Downloading today's data (GarminDB --latest workaround)")
    try:
        r = subprocess.run([python, '-c', _DOWNLOAD_TODAY_SNIPPET],
                           capture_output=True, text=True, timeout=timeout, cwd=cwd)
    except subprocess.TimeoutExpired:
        logger.warning("Today's download timed out after %ds", timeout)
        return False
    if r.returncode != 0:
        logger.warning("Today's download failed (exit %d): %s",
                       r.returncode, (r.stderr or '').strip().splitlines()[-1:] or '')
        return False
    logger.info("Today's data downloaded")
    return True


def sync():
    """Run garmindb CLI incremental sync."""
    ensure_garmindb_config(GARMIN_EMAIL)
    ensure_token()
    python = _find_python()
    script = _find_garmindb_cli()
    log_dir = _garmindb_log_dir()
    today_downloaded = download_today(cwd=log_dir)
    cmd = [python, script, '--all', '--download', '--import', '--analyze', '--latest']
    logger.info("Starting incremental sync: %s", ' '.join(cmd[-3:]))
    print("  Syncing...", end=" ", flush=True)
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=GARMINDB_SYNC_TIMEOUT,
                           cwd=log_dir)
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - t0
        message = f"GarminDB incremental sync timed out after {GARMINDB_SYNC_TIMEOUT}s ({elapsed:.0f}s elapsed)"
        logger.error("%s: %s", message, (e.stderr or e.output or '').strip())
        print(f"failed ({elapsed:.0f}s)")
        raise GarminDBSyncError(message) from e
    elapsed = time.time() - t0
    print(f"done ({elapsed:.0f}s)")
    if r.returncode != 0:
        message = f"GarminDB incremental sync failed with exit code {r.returncode} after {elapsed:.0f}s"
        logger.error("%s: %s", message, (r.stderr or r.stdout or '').strip())
        print(f"  Warnings/errors (exit {r.returncode})")
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-5:]
        for line in tail:
            print(f"    {line}")
        raise GarminDBSyncError(message)
    else:
        logger.info("Sync completed successfully in %.0fs", elapsed)
    return SyncStatus.FULL if today_downloaded else SyncStatus.PARTIAL


def sync_full():
    """Run garmindb CLI full sync (first time / rebuild)."""
    python = _find_python()
    script = _find_garmindb_cli()
    log_dir = _garmindb_log_dir()
    cmd = [python, script, '--all', '--download', '--import', '--analyze']
    logger.info("Starting full sync (timeout: %ds)", GARMINDB_FRESH_TIMEOUT)
    print("Running full sync (this may take a while)...")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=GARMINDB_FRESH_TIMEOUT,
                           cwd=log_dir)
    except subprocess.TimeoutExpired as e:
        message = f"GarminDB full sync timed out after {GARMINDB_FRESH_TIMEOUT}s"
        logger.error("%s: %s", message, (e.stderr or e.output or '').strip())
        raise GarminDBSyncError(message) from e
    if r.returncode != 0:
        message = f"GarminDB full sync failed with exit code {r.returncode}"
        logger.error("%s: %s", message, (r.stderr or r.stdout or '').strip())
        raise GarminDBSyncError(message)
    logger.info("Full sync completed")
    return SyncStatus.FULL


def extract():
    """Extract all recent data from DBs and return dict."""
    logger.debug("Extracting data from databases")
    data = {
        "timestamp": datetime.now().isoformat(),
        "activities": [],
        "daily_health": [],
        "sleep": [],
        "hrv": [],
        "weight": [],
    }

    # === Activities ===
    if os.path.exists(ACT_DB):
        with sqlite3.connect(ACT_DB) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT activity_id, start_time, name, distance, moving_time, avg_hr, max_hr,
                       avg_speed, ascent, training_effect, anaerobic_training_effect,
                       sport, sub_sport
                FROM activities WHERE distance > 0
                ORDER BY start_time DESC LIMIT 50
            """)
            for r in c.fetchall():
                t = parse_timedelta(r[4])
                pace = (t / 60) / r[3] if r[3] > 0 else 0
                data["activities"].append({
                    "activity_id": r[0],
                    "date": str(r[1])[:16] if r[1] else "",
                    "name": r[2] or "",
                    "type": f"{r[11] or ''}/{r[12] or ''}",
                    "distance_km": round(r[3], 2),
                    "duration_min": round(t / 60, 1),
                    "pace": pace_str(pace),
                    "avg_hr": r[5],
                    "max_hr": r[6],
                    "avg_speed_kmh": round(r[7], 1) if r[7] is not None else 0,
                    "ascent_m": round(r[8] or 0, 1),
                    "te": r[9],
                    "ate": r[10],
                })

    # === Daily health, sleep, HRV, weight ===
    if os.path.exists(MAIN_DB):
        with sqlite3.connect(MAIN_DB) as conn:
            c = conn.cursor()

            # Daily summary (last 14 days)
            c.execute("""
                SELECT day, rhr, hr_min, hr_max, steps, stress_avg,
                       rr_waking_avg, spo2_avg, calories_active, calories_total,
                       moderate_activity_time, vigorous_activity_time
                FROM daily_summary ORDER BY day DESC LIMIT 14
            """)
            for r in c.fetchall():
                data["daily_health"].append({
                    "date": str(r[0])[:10],
                    "rhr": r[1],
                    "hr_min": r[2],
                    "hr_max": r[3],
                    "steps": r[4],
                    "stress_avg": r[5],
                    "rr": r[6],
                    "spo2": r[7],
                    "cal_active": r[8],
                    "cal_total": r[9],
                })

            # Sleep (last 14 days)
            try:
                c.execute("""
                    SELECT day, total_sleep, deep_sleep, light_sleep, rem_sleep,
                           awake, score, qualifier
                    FROM sleep ORDER BY day DESC LIMIT 14
                """)
                for r in c.fetchall():
                    data["sleep"].append({
                        "date": str(r[0])[:10],
                        "total_h": round(parse_timedelta(r[1]) / 3600, 1) if r[1] else 0,
                        "deep_h": round(parse_timedelta(r[2]) / 3600, 1) if r[2] else 0,
                        "light_h": round(parse_timedelta(r[3]) / 3600, 1) if r[3] else 0,
                        "rem_h": round(parse_timedelta(r[4]) / 3600, 1) if r[4] else 0,
                        "score": r[6],
                        "qualifier": r[7],
                    })
            except Exception as e:
                print(f"  Warning: sleep table not found or empty: {e}")

            # HRV (last 14 days)
            try:
                c.execute("""
                    SELECT day, weekly_avg, last_night_avg, baseline_low,
                           baseline_upper, status
                    FROM hrv ORDER BY day DESC LIMIT 14
                """)
                for r in c.fetchall():
                    data["hrv"].append({
                        "date": str(r[0])[:10],
                        "weekly_avg": r[1],
                        "last_night": r[2],
                        "baseline_low": r[3],
                        "baseline_high": r[4],
                        "status": r[5],
                    })
            except Exception as e:
                print(f"  Warning: hrv table not found or empty: {e}")

            # Weight (last 10 entries)
            c.execute("SELECT day, weight FROM weight ORDER BY day DESC LIMIT 10")
            for r in c.fetchall():
                data["weight"].append({
                    "date": str(r[0])[:10],
                    "weight_kg": r[1],
                })

    return data


def save_json(data, path=None):
    """Save extracted data to JSON file."""
    path = path or DATA_LATEST
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Data saved to {path}")


def load_data_latest(path=None):
    """Load data_latest.json and return parsed dict. Raises on missing/corrupt."""
    path = path or DATA_LATEST
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def read_snapshot_status(path=None, now=None, ttl_seconds=SNAPSHOT_TTL_SECONDS):
    """Load a snapshot and classify it without changing ``load_data_latest`` API."""
    path = path or DATA_LATEST
    try:
        data = load_data_latest(path)
        timestamp = data.get("timestamp") if isinstance(data, dict) else None
        if not timestamp:
            raise ValueError("Snapshot is missing its timestamp")
        created_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
    except FileNotFoundError as exc:
        return SnapshotReadResult(SnapshotStatus.MISSING, error=exc)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return SnapshotReadResult(SnapshotStatus.INVALID, error=exc)

    status = (SnapshotStatus.STALE if (current - created_at).total_seconds() > ttl_seconds
              else SnapshotStatus.FRESH)
    return SnapshotReadResult(status, data=data)


def print_summary(d):
    """Print a human-readable summary of extracted data."""
    print(f"\n=== OSTATNIA SYNCHRONIZACJA: {d['timestamp']} ===")

    if d['activities']:
        print(f"\n--- AKTYWNOŚCI (ostatnie) ---")
        for a in d['activities'][:5]:
            print(f"  {a['date']}: {a['name'] or 'bieg'}, {a['distance_km']}km, "
                  f"{a['pace']}, HR {a['avg_hr']}/{a['max_hr']}, "
                  f"wznies {a['ascent_m']}m")

    if d['daily_health']:
        print(f"\n--- ZDROWIE DZIENNE ---")
        for h in d['daily_health'][:7]:
            print(f"  {h['date']}: RHR={h['rhr']}, HR={h['hr_min']}-{h['hr_max']}, "
                  f"kroki={h['steps']}, stres={h['stress_avg']}, RR={h['rr']}, SpO2={h['spo2']}%")

    if d['sleep']:
        print(f"\n--- SEN ---")
        for s in d['sleep'][:7]:
            print(f"  {s['date']}: {s['total_h']}h, gleboki={s['deep_h']}h, "
                  f"REM={s['rem_h']}h, score={s['score']}, {s['qualifier'] or ''}")

    if d['hrv']:
        print(f"\n--- HRV ---")
        for h in d['hrv'][:7]:
            print(f"  {h['date']}: tydz={h['weekly_avg']}, ostatnia={h['last_night']}, "
                  f"base={h['baseline_low']}-{h['baseline_high']}, status={h['status']}")

    if d['weight']:
        print(f"\n--- WAGA ---")
        for w in d['weight'][:5]:
            print(f"  {w['date']}: {w['weight_kg']} kg")

    # HRV ALERT — uses check_hrv_alert from core.py (no duplicate logic)
    hrv_alert = check_hrv_alert(d.get('hrv', []))
    if hrv_alert:
        print(f"\n{'!' * 60}")
        print(f"  ALERT: HRV NISKIE OD {hrv_alert['days']} DNI!")
        print(f"  Statusy: {', '.join(hrv_alert['statuses'])}")
        print(f"  Wartosci: {hrv_alert['values']}")
        print(f"  REKOMENDACJA: Odpoczynek lub bardzo lekki bieg.")
        print(f"{'!' * 60}")

    print()
