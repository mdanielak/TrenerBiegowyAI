# -*- coding: utf-8 -*-
"""
Training plan loading and query utilities.

Plans are stored one JSON file per training block:

    training-plans/{YYYY-MM}/{start_day}-{end_day}.json

filed under the month the block starts in, e.g.
    training-plans/2026-09/14-20.json     (Mon 14 Sep - Sun 20 Sep)
    training-plans/2026-09/28-4.json      (Mon 28 Sep - Sun 04 Oct)

A block does not have to be a full Mon-Sun week — a mid-week revision such as
16-20.json is valid. When more than one file covers the same day, the one with
the latest start_date wins, so a revision supersedes the original week.

Importable from CLI, tests, and future API.
"""
import csv
import json
from datetime import datetime, timedelta

from config import TRAINING_PLANS_DIR


def week_bounds(day):
    """Return (monday, sunday) of the training week containing `day`."""
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def plan_filename(day):
    """Filename of the training week containing `day`, e.g. '21-27.json'."""
    monday, sunday = week_bounds(day)
    return f"{monday.day}-{sunday.day}.json"


def plan_path(day, plans_dir=None):
    """Return the canonical Path for the plan of the week containing `day`.

    This is where a new weekly plan should be written. Reading goes through
    find_plan_file(), which also picks up blocks that are not full weeks.
    """
    monday, _ = week_bounds(day)
    base = TRAINING_PLANS_DIR if plans_dir is None else plans_dir
    return base / monday.strftime('%Y-%m') / plan_filename(day)


def _candidate_dirs(day, base):
    """Month directories that could hold a plan covering `day`.

    The previous month is included because a block may span a month boundary.
    """
    previous_month_day = day.replace(day=1) - timedelta(days=1)
    return [
        base / day.strftime('%Y-%m'),
        base / previous_month_day.strftime('%Y-%m'),
    ]


def find_plan_file(day, plans_dir=None):
    """Find the plan file covering `day`, or None.

    Scans the surrounding month directories for a plan whose start_date and
    end_date bracket the day. The match with the latest start_date wins.
    """
    base = TRAINING_PLANS_DIR if plans_dir is None else plans_dir
    target = day.strftime('%Y-%m-%d')
    matches = []

    seen_dirs = set()
    for directory in _candidate_dirs(day, base):
        if directory in seen_dirs or not directory.is_dir():
            continue
        seen_dirs.add(directory)
        for path in sorted(directory.glob('*.json')):
            try:
                with open(path, encoding='utf-8') as f:
                    plan = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            start, end = plan.get('start_date'), plan.get('end_date')
            if start and end and start <= target <= end:
                matches.append((start, str(path), path))

    if matches:
        return max(matches)[2]

    canonical = plan_path(day, base)
    return canonical if canonical.is_file() else None


def load_plan(day, plans_dir=None):
    """Load the plan covering `day`.

    Returns the parsed dict, or None when no plan covers that day.
    Raises json.JSONDecodeError when the resolved file is not valid JSON.
    """
    path = find_plan_file(day, plans_dir)
    if path is None:
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def find_current_plan(today=None):
    """Find the training plan covering today.

    Returns parsed dict or None if no plan exists for the current week.
    """
    if today is None:
        today = datetime.now()
    return load_plan(today)


def get_today_workout_from_plan(plan, today=None):
    """Get today's planned workout from a training plan.

    Returns workout dict or None (rest day or no plan for today).
    """
    if today is None:
        today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')

    for w in plan.get('workouts', []):
        if w['date'] == today_str:
            return w
    return None


# --- CSV twin ---------------------------------------------------------------
# The JSON is the source of truth; the CSV exists so the week can be read at a
# glance (and edited in Excel). Generating both from one place keeps them from
# drifting apart, which is what happened when the CSV was written by hand.

CSV_COLUMNS = ['Dzień', 'Data', 'Typ', 'Nazwa', 'Opis', 'Dystans (km)',
               'Czas (min)', 'Tempo docelowe', 'HR docelowe', 'Strefa HR',
               'Garmin upload', 'ID Garmin', 'Uwagi']


def plan_csv_rows(plan):
    """CSV rows for a plan, header first."""
    rows = [CSV_COLUMNS]
    for w in plan.get('workouts', []):
        rows.append([
            w.get('day', ''), w.get('date', ''), w.get('type', ''), w.get('name', ''),
            w.get('description', ''), w.get('distance_km', 0), w.get('duration_min', 0),
            w.get('pace_target') or '-', w.get('hr_target') or '-',
            w.get('hr_zone') or '-',
            'Tak' if w.get('garmin_upload') else 'Nie',
            w.get('garmin_workout_id') or '-',
            w.get('notes') or '',
        ])
    return rows


def write_plan_csv(plan, path=None):
    """Write the CSV twin of a plan, next to the JSON unless told otherwise.

    utf-8-sig because Excel needs the BOM to read Polish diacritics, and an
    explicit '\\n' so rows do not double-space on Windows.
    """
    if path is None:
        path = plan_path(datetime.strptime(plan['start_date'], '%Y-%m-%d')).with_suffix('.csv')
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        csv.writer(f, lineterminator='\n').writerows(plan_csv_rows(plan))
    return path
