# -*- coding: utf-8 -*-
"""
Wspolne funkcje analityczne — bez efektow ubocznych (brak print, brak read).
Mozna bezpiecznie importowac w testach.
"""
from datetime import datetime


def parse_timedelta(td):
    """Parse SQLite TIME or timedelta to seconds."""
    if not td:
        return 0
    s = str(td)
    p = s.split(':')
    return int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2].split('.')[0])


def pace_str(pace_sec_per_km):
    """Convert pace (seconds per km) to 'M:SS/km' string."""
    m = int(pace_sec_per_km)
    s = int((pace_sec_per_km - m) * 60)
    return f"{m}:{s:02d}/km"


def check_hrv_alert(hrv_data):
    """Check if HRV has been LOW/UNBALANCED for 3+ consecutive days."""
    if len(hrv_data) < 3:
        return None

    consecutive_low = 0
    statuses = []
    for h in hrv_data[:7]:
        s = h.get('status', '')
        statuses.append(s)
        if s in ('LOW', 'UNBALANCED'):
            consecutive_low += 1
        else:
            break

    if consecutive_low >= 3:
        return {
            'days': consecutive_low,
            'statuses': statuses[:consecutive_low],
            'values': [h['last_night'] for h in hrv_data[:consecutive_low]],
            'baseline': f"{hrv_data[0]['baseline_low']}-{hrv_data[0]['baseline_high']}"
        }
    return None


def compute_readiness_score(latest_health, latest_sleep, latest_hrv):
    """Compatibility wrapper around the canonical readiness implementation."""
    from services.readiness import compute_readiness_breakdown
    return compute_readiness_breakdown({
        'daily_health': [latest_health or {}],
        'sleep': [latest_sleep or {}],
        'hrv': [latest_hrv or {}],
    })['score']


def week_bounds(day):
    """Compatibility wrapper for services.plan_files.week_bounds."""
    from services.plan_files import week_bounds as canonical_week_bounds
    return canonical_week_bounds(day)


def plan_filename(day):
    """Compatibility wrapper for services.plan_files.plan_filename."""
    from services.plan_files import plan_filename as canonical_plan_filename
    return canonical_plan_filename(day)


def find_current_plan(base_dir, today=None):
    """Find the training plan covering `today`.

    Plans are stored one file per training week under
    training-plans/{YYYY-MM}/{start_day}-{end_day}.json, filed under the month
    the week starts in (e.g. training-plans/2026-09/21-27.json).
    """
    from pathlib import Path
    from services.plan_files import load_plan
    return load_plan(today or datetime.now(), Path(base_dir) / 'training-plans')
