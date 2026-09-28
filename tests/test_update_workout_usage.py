# -*- coding: utf-8 -*-
"""Tests for update_workout_usage.py — matching workouts to activities."""
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import workout_registry as reg
import update_workout_usage as uwu


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, 'REGISTRY_PATH', tmp_path / "_garmin_workouts.jsonl")


class TestCounts:
    def test_exact_match_counts(self):
        w = {'name': 'Regeneracja 45 min', 'date': '2026-09-28'}
        assert uwu._counts(w, 'Wieliczka - Regeneracja 45 min', '2026-09-21')

    def test_shared_name_only_counts_on_the_scheduled_day(self):
        """Two library entries can share a name — then the day is the only clue."""
        w = {'name': 'Regeneracja 45 min', 'date': '2026-09-28'}
        assert not uwu._counts(w, 'Wieliczka - Regeneracja 45 min', '2026-09-21',
                               require_date=True)
        assert uwu._counts(w, 'Wieliczka - Regeneracja 45 min', '2026-09-28',
                           require_date=True)

    def test_shared_name_without_a_scheduled_date_still_counts(self):
        """An unknown date must not silently hide a used workout."""
        w = {'name': 'Regeneracja 45 min', 'date': None}
        assert uwu._counts(w, 'Wieliczka - Regeneracja 45 min', '2026-09-21',
                           require_date=True)

    def test_unrelated_activity_never_counts(self):
        w = {'name': 'Regeneracja 45 min', 'date': '2026-09-28'}
        assert not uwu._counts(w, 'Wieliczka - 3x8 min tempo', '2026-09-28')


class TestSharedNames:
    def test_detects_a_name_used_twice(self):
        lib = [{'name': 'A'}, {'name': 'B'}, {'name': 'A'}]
        assert uwu.shared_names(lib) == {'A'}

    def test_distinct_names_are_not_flagged(self):
        assert uwu.shared_names([{'name': 'A'}, {'name': 'B'}]) == set()

    def test_missing_names_are_ignored(self):
        assert uwu.shared_names([{'name': None}, {'name': None}]) == set()


class TestRefresh:
    def test_does_not_credit_the_wrong_workout(self):
        """A rebuilt template shares the old name but was never run."""
        reg.record_added('Regeneracja 45 min', '2026-09-21', 111)
        reg.record_added('Regeneracja 45 min', '2026-09-28', 222)
        activities = [('Wieliczka - Regeneracja 45 min', '2026-09-21')]

        uwu.refresh(activities)

        assert reg.find_workout(111)['last_used'] == '2026-09-21'
        # "never used" is the absence of a usage event, not a null one.
        assert reg.find_workout(222).get('last_used') is None

    def test_unique_name_still_matches_by_name_alone(self):
        reg.record_added('3x8 min tempo', '2026-09-22', 111)
        uwu.refresh([('Wieliczka - 3x8 min tempo', '2026-09-22')])
        assert reg.find_workout(111)['last_used'] == '2026-09-22'
