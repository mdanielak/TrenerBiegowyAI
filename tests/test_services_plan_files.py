# -*- coding: utf-8 -*-
"""Tests for services/plan_files.py — training plan loading utilities."""
import sys
import os
import csv
import json
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import plan_files as tp
from services.plan_files import (
    plan_path, find_plan_file, load_plan, find_current_plan,
    get_today_workout_from_plan,
)


def write_plan(base, year_month, filename, plan):
    plan_dir = base / year_month
    plan_dir.mkdir(exist_ok=True)
    (plan_dir / filename).write_text(json.dumps(plan), encoding='utf-8')


class TestPlanPath:
    def test_names_file_after_week_bounds(self, tmp_path):
        # 2026-09-16 is a Wednesday; the week runs Mon 14 - Sun 20
        assert plan_path(datetime(2026, 9, 16), tmp_path) == tmp_path / "2026-09" / "14-20.json"

    def test_monday_and_sunday_map_to_same_file(self, tmp_path):
        monday = plan_path(datetime(2026, 9, 14), tmp_path)
        sunday = plan_path(datetime(2026, 9, 20), tmp_path)
        assert monday == sunday

    def test_week_spanning_month_is_filed_under_start_month(self, tmp_path):
        # Mon 2026-09-28 - Sun 2026-10-04
        assert plan_path(datetime(2026, 10, 2), tmp_path) == tmp_path / "2026-09" / "28-4.json"


class TestFindPlanFile:
    def test_partial_week_block_is_found(self, tmp_path):
        # A block that is not a full Mon-Sun week, e.g. a mid-week revision
        write_plan(tmp_path, "2026-09", "16-20.json",
                   {"start_date": "2026-09-16", "end_date": "2026-09-20"})
        assert find_plan_file(datetime(2026, 9, 18), tmp_path).name == "16-20.json"

    def test_latest_start_date_wins_on_overlap(self, tmp_path):
        write_plan(tmp_path, "2026-09", "14-20.json",
                   {"start_date": "2026-09-14", "end_date": "2026-09-20"})
        write_plan(tmp_path, "2026-09", "16-20.json",
                   {"start_date": "2026-09-16", "end_date": "2026-09-20"})

        # Inside the overlap the revision wins...
        assert find_plan_file(datetime(2026, 9, 18), tmp_path).name == "16-20.json"
        # ...but before it starts, the original week still applies
        assert find_plan_file(datetime(2026, 9, 15), tmp_path).name == "14-20.json"

    def test_block_spanning_month_boundary(self, tmp_path):
        write_plan(tmp_path, "2026-09", "28-4.json",
                   {"start_date": "2026-09-28", "end_date": "2026-10-04"})
        assert find_plan_file(datetime(2026, 10, 2), tmp_path).name == "28-4.json"

    def test_no_match_returns_none(self, tmp_path):
        assert find_plan_file(datetime(2026, 9, 18), tmp_path) is None


class TestLoadPlan:
    def test_load_valid_plan(self, tmp_path):
        plan = {"week": 38, "start_date": "2026-09-14", "end_date": "2026-09-20", "workouts": []}
        write_plan(tmp_path, "2026-09", "14-20.json", plan)

        result = load_plan(datetime(2026, 9, 16), tmp_path)
        assert result is not None
        assert result['week'] == 38

    def test_load_missing_month_returns_none(self, tmp_path):
        assert load_plan(datetime(2099, 1, 5), tmp_path) is None

    def test_load_missing_week_returns_none(self, tmp_path):
        write_plan(tmp_path, "2026-09", "14-20.json", {"week": 38})

        # 2026-01-05 is a Monday of a week with no plan file
        assert load_plan(datetime(2026, 1, 5), tmp_path) is None

    def test_load_corrupted_json_raises(self, tmp_path):
        plan_dir = tmp_path / "2026-09"
        plan_dir.mkdir()
        (plan_dir / "14-20.json").write_text("{bad json", encoding='utf-8')

        with pytest.raises(json.JSONDecodeError):
            load_plan(datetime(2026, 9, 16), tmp_path)


class TestFindCurrentPlan:
    def test_finds_current_plan(self, tmp_path, monkeypatch):
        monkeypatch.setattr('services.plan_files.TRAINING_PLANS_DIR', tmp_path)
        write_plan(tmp_path, "2026-09", "14-20.json", {"week": 38, "workouts": []})

        result = find_current_plan(datetime(2026, 9, 16))
        assert result is not None
        assert result['week'] == 38

    def test_no_plan_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr('services.plan_files.TRAINING_PLANS_DIR', tmp_path)
        assert find_current_plan(datetime(2026, 9, 16)) is None


class TestGetTodayWorkoutFromPlan:
    def test_found(self):
        plan = {'workouts': [
            {'date': '2026-09-16', 'name': 'Easy', 'type': 'easy'},
        ]}
        result = get_today_workout_from_plan(plan, datetime(2026, 9, 16))
        assert result is not None
        assert result['name'] == 'Easy'

    def test_not_found(self):
        plan = {'workouts': [
            {'date': '2026-09-15', 'name': 'Easy', 'type': 'easy'},
        ]}
        result = get_today_workout_from_plan(plan, datetime(2026, 9, 16))
        assert result is None

    def test_empty_workouts(self):
        result = get_today_workout_from_plan({'workouts': []}, datetime(2026, 9, 16))
        assert result is None


class TestPlanCsv:
    PLAN = {
        'start_date': '2026-09-28', 'end_date': '2026-10-04',
        'workouts': [
            {'day': 'Pon', 'date': '2026-09-28', 'type': 'regeneration',
             'name': 'Regeneracja 45 min', 'description': 'Opis', 'distance_km': 5.8,
             'duration_min': 45, 'pace_target': '7:00-8:30/km',
             'hr_target': '115-134 (Z2)', 'hr_zone': 'Z2', 'garmin_upload': True,
             'garmin_workout_id': 1710820778, 'notes': 'Uwaga'},
            {'day': 'Śr', 'date': '2026-09-30', 'type': 'rest', 'name': 'Odpoczynek',
             'description': 'Dzień wolny.', 'distance_km': 0, 'duration_min': 0,
             'pace_target': None, 'hr_target': None, 'hr_zone': None,
             'garmin_upload': False, 'garmin_workout_id': None, 'notes': None},
        ],
    }

    def test_header_then_one_row_per_workout(self):
        rows = tp.plan_csv_rows(self.PLAN)
        assert rows[0] == tp.CSV_COLUMNS
        assert len(rows) == 3

    def test_missing_targets_become_dashes(self):
        rows = tp.plan_csv_rows(self.PLAN)
        assert rows[2][7:10] == ['-', '-', '-']

    def test_upload_flag_reads_as_tak_nie(self):
        rows = tp.plan_csv_rows(self.PLAN)
        assert rows[1][10] == 'Tak'
        assert rows[2][10] == 'Nie'
        assert rows[2][11] == '-'

    def test_writes_utf8_bom_so_excel_reads_diacritics(self, tmp_path):
        path = tmp_path / 'plan.csv'
        tp.write_plan_csv(self.PLAN, path)
        raw = path.read_bytes()
        assert raw.startswith(b'\xef\xbb\xbf')
        assert 'Dzień' in raw.decode('utf-8-sig')

    def test_roundtrip_row_count(self, tmp_path):
        path = tmp_path / 'plan.csv'
        tp.write_plan_csv(self.PLAN, path)
        with open(path, encoding='utf-8-sig', newline='') as f:
            assert len(list(csv.reader(f))) == len(self.PLAN['workouts']) + 1
