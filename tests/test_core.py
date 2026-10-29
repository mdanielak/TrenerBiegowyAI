# -*- coding: utf-8 -*-
"""Unit tests for trainer.core shared functions."""
import sys
import os
import json
from datetime import datetime


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trainer.core import (
    parse_timedelta, pace_str, check_hrv_alert,
    find_current_plan, week_bounds, plan_filename,
)


# ======================================================================
# parse_timedelta
# ======================================================================
class TestParseTimedelta:
    def test_standard_format(self):
        assert parse_timedelta("1:30:00") == 5400

    def test_minutes_only(self):
        assert parse_timedelta("0:45:00") == 2700

    def test_with_milliseconds(self):
        assert parse_timedelta("0:30:15.500") == 1815

    def test_zero(self):
        assert parse_timedelta("0:00:00") == 0

    def test_none_returns_zero(self):
        assert parse_timedelta(None) == 0

    def test_empty_string_returns_zero(self):
        assert parse_timedelta("") == 0


# ======================================================================
# pace_str
# ======================================================================
class TestPaceStr:
    def test_five_min_pace(self):
        assert pace_str(5.0) == "5:00/km"

    def test_six_thirty_pace(self):
        assert pace_str(6.5) == "6:30/km"

    def test_whole_minutes(self):
        assert pace_str(4.0) == "4:00/km"

    def test_seconds_only(self):
        assert pace_str(0.5) == "0:30/km"


# ======================================================================
# check_hrv_alert
# ======================================================================
class TestHrvAlert:
    def _make_hrv(self, status, last_night, baseline_low=67, baseline_high=82):
        return {
            'date': '2026-09-15', 'weekly_avg': 70,
            'last_night': last_night,
            'baseline_low': baseline_low, 'baseline_high': baseline_high,
            'status': status,
        }

    def test_no_alert_when_balanced(self):
        data = [self._make_hrv('BALANCED', 70) for _ in range(5)]
        assert check_hrv_alert(data) is None

    def test_alert_on_3_consecutive_low(self):
        data = [
            self._make_hrv('LOW', 60),
            self._make_hrv('LOW', 59),
            self._make_hrv('LOW', 58),
            self._make_hrv('BALANCED', 70),
        ]
        result = check_hrv_alert(data)
        assert result is not None
        assert result['days'] == 3

    def test_alert_on_unbalanced(self):
        data = [
            self._make_hrv('UNBALANCED', 62),
            self._make_hrv('LOW', 60),
            self._make_hrv('LOW', 59),
        ]
        assert check_hrv_alert(data) is not None

    def test_no_alert_when_2_consecutive(self):
        data = [
            self._make_hrv('LOW', 60),
            self._make_hrv('LOW', 59),
            self._make_hrv('BALANCED', 70),
        ]
        assert check_hrv_alert(data) is None

    def test_no_alert_on_short_data(self):
        data = [self._make_hrv('LOW', 60), self._make_hrv('LOW', 59)]
        assert check_hrv_alert(data) is None

    def test_no_alert_on_empty_data(self):
        assert check_hrv_alert([]) is None


# ======================================================================
# find_current_plan
# ======================================================================
class TestWeekBounds:
    def test_monday_to_sunday(self):
        monday, sunday = week_bounds(datetime(2026, 9, 16))
        assert monday == datetime(2026, 9, 14)
        assert sunday == datetime(2026, 9, 20)

    def test_plan_filename_uses_day_numbers(self):
        assert plan_filename(datetime(2026, 9, 16)) == "14-20.json"
        assert plan_filename(datetime(2026, 10, 2)) == "28-4.json"


class TestFindPlan:
    def test_finds_plan(self, tmp_path):
        plans_dir = tmp_path / "training-plans" / "2026-09"
        plans_dir.mkdir(parents=True)
        plan = {"week": 38, "workouts": []}
        (plans_dir / "14-20.json").write_text(json.dumps(plan), encoding='utf-8')

        from datetime import datetime
        result = find_current_plan(str(tmp_path), datetime(2026, 9, 16))
        assert result is not None
        assert result['week'] == 38

    def test_no_plan_returns_none(self, tmp_path):
        from datetime import datetime
        result = find_current_plan(str(tmp_path), datetime(2026, 9, 16))
        assert result is None
