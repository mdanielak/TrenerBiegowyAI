# -*- coding: utf-8 -*-
"""Tests for services/workout_registry.py — append-only Garmin workout log."""
import sys
import os
import json
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import workout_registry as reg


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, 'REGISTRY_PATH', tmp_path / "_garmin_workouts.jsonl")


class TestAppendOnly:
    def test_missing_file_reads_as_empty(self):
        assert reg.load_events() == []

    def test_append_keeps_every_line(self):
        reg.record_added("A", "2026-09-17", 111, schedule_id=222)
        reg.record_added("B", "2026-09-18", 333)

        events = reg.load_events()
        assert [e['workout_id'] for e in events] == [111, 333]
        assert all('ts' in e for e in events)

    def test_records_carry_a_timestamp(self):
        e = reg.record_added("A", "2026-09-17", 111)
        datetime.fromisoformat(e['ts'])  # raises if malformed

    def test_malformed_line_is_skipped_not_fatal(self):
        reg.record_added("A", "2026-09-17", 111)
        with open(reg.REGISTRY_PATH, 'a', encoding='utf-8') as f:
            f.write("{not json\n")
        reg.record_added("B", "2026-09-18", 222)

        assert [e['workout_id'] for e in reg.load_events()] == [111, 222]

    def test_unserializable_value_does_not_raise(self):
        """Bookkeeping must never break an upload that already reached Garmin."""
        reg.record_added("A", "2026-09-17", 111, schedule_id=object())
        assert reg.load_events()  # written thanks to default=str


class TestWriteStatus:
    @pytest.mark.parametrize('record, args', [
        (reg.record_added, ('A', '2026-09-17', 111)),
        (reg.record_deleted, (111,)),
        (reg.record_usage, (111, '2026-09-17')),
        (reg.record_updated, (111,)),
    ])
    def test_record_functions_return_entry_by_default_and_status_on_request(self, record, args):
        assert isinstance(record(*args), dict)
        result = record(*args, return_status=True)
        assert isinstance(result, reg.RegistryWriteResult)
        assert result.persisted is True

    def test_timestamp_error_is_reported_without_raising(self, monkeypatch):
        def broken_now():
            raise RuntimeError('clock unavailable')

        monkeypatch.setattr(reg, '_now', broken_now)
        result = reg._append({'event': 'added', 'workout_id': 111}, return_status=True)
        assert result.persisted is False
        assert result.error_code == 'timestamp_error'

    def test_serialization_error_is_reported_without_raising(self, monkeypatch):
        def broken_dumps(*args, **kwargs):
            raise TypeError('cannot serialize')

        monkeypatch.setattr(reg.json, 'dumps', broken_dumps)
        result = reg._append({'event': 'added', 'workout_id': 111}, return_status=True)
        assert result.persisted is False
        assert result.error_code == 'serialization_error'

    def test_io_error_is_reported_without_raising(self, monkeypatch):
        def broken_open(*args, **kwargs):
            raise OSError('disk unavailable')

        monkeypatch.setattr(reg, 'open', broken_open, raising=False)
        result = reg._append({'event': 'added', 'workout_id': 111}, return_status=True)
        assert result.persisted is False
        assert result.error_code == 'io_error'

    def test_write_metadata_is_not_stored_in_event(self):
        result = reg.record_added('A', '2026-09-17', 111, return_status=True)
        assert result.persisted is True
        event = reg.load_events()[0]
        assert 'persisted' not in event
        assert 'error_code' not in event

    def test_later_appends_preserve_earlier_file_bytes(self):
        reg.record_added('A', '2026-09-17', 111)
        first = reg.REGISTRY_PATH.read_bytes()
        reg.record_deleted(111)
        second = reg.REGISTRY_PATH.read_bytes()
        reg.record_usage(111, '2026-09-18')
        assert second.startswith(first)
        assert reg.REGISTRY_PATH.read_bytes().startswith(second)

    def test_schedule_fields_are_projected_without_changing_spec(self):
        reg.record_added('A', None, 111, spec={'kind': 'easy_run'},
                         intended_date='2026-10-05', schedule_status='pending')
        reg.record_updated(111, date='2026-10-05', schedule_status='confirmed')
        workout = reg.find_workout(111)
        assert workout['schedule_status'] == 'confirmed'
        assert workout['intended_date'] == '2026-10-05'
        assert workout['spec'] == {'kind': 'easy_run'}

    def test_historical_entry_without_schedule_fields_remains_active(self):
        reg._append({'event': 'added', 'workout_id': 111, 'name': 'A',
                     'ts': '2026-09-17T00:00:00'})
        workout = reg.find_workout(111)
        assert workout['status'] == 'active'
        assert 'schedule_status' not in workout


class TestState:
    def test_active_after_add(self):
        reg.record_added("A", "2026-09-17", 111, schedule_id=222)
        w = reg.find_workout(111)
        assert w['status'] == 'active'
        assert w['name'] == 'A'
        assert w['schedule_id'] == 222

    def test_deleted_after_remove_and_spec_survives(self):
        reg.record_added("A", "2026-09-17", 111, schedule_id=222,
                         spec={'kind': 'hr_zone_run', 'duration_min': 35})
        reg.record_deleted(111, reason='wykonany')

        assert reg.list_workouts('active') == []
        w = reg.find_workout(111)
        assert w['status'] == 'deleted'
        assert w['reason'] == 'wykonany'
        assert w['spec']['duration_min'] == 35
        assert w['schedule_id'] == 222

    def test_readd_after_delete_becomes_active_again(self):
        reg.record_added("A", "2026-09-17", 111)
        reg.record_deleted(111)
        reg.record_added("A", "2026-09-20", 111)

        assert reg.find_workout(111)['status'] == 'active'
        assert reg.find_workout(111)['date'] == '2026-09-20'

    def test_status_filter(self):
        reg.record_added("A", "2026-09-17", 111)
        reg.record_added("B", "2026-09-17", 222)
        reg.record_deleted(222)

        assert [w['workout_id'] for w in reg.list_workouts('active')] == [111]
        assert [w['workout_id'] for w in reg.list_workouts('deleted')] == [222]
        assert len(reg.list_workouts('all')) == 2


class TestUpdate:
    def test_update_replaces_name_and_definition(self):
        """The user reshapes workouts in Garmin; the entry on file must follow."""
        reg.record_added("Łatwy 32 min", "2026-09-25", 111,
                         definition={'estimatedDurationInSecs': 1920})
        reg.record_updated(111, name="Easy 30 min (Z2) + tempo",
                           definition={'estimatedDurationInSecs': 2700})

        w = reg.find_workout(111)
        assert w['name'] == "Easy 30 min (Z2) + tempo"
        assert w['definition']['estimatedDurationInSecs'] == 2700

    def test_update_keeps_the_upload_spec(self):
        """The builder spec describes the original upload, not the edits."""
        reg.record_added("A", "2026-09-25", 111, spec={'kind': 'easy_run_zoned'})
        reg.record_updated(111, name="B")
        assert reg.find_workout(111)['spec'] == {'kind': 'easy_run_zoned'}

    def test_update_leaves_omitted_fields_alone(self):
        reg.record_added("A", "2026-09-25", 111, schedule_id=999)
        reg.record_updated(111, name="B")
        assert reg.find_workout(111)['schedule_id'] == 999

    def test_update_keeps_the_workout_active(self):
        reg.record_added("A", "2026-09-25", 111)
        reg.record_updated(111, name="B")
        assert reg.find_workout(111)['status'] == 'active'

    def test_update_after_delete_does_not_resurrect(self):
        reg.record_added("A", "2026-09-25", 111)
        reg.record_deleted(111)
        reg.record_updated(111, name="B")
        assert reg.find_workout(111)['status'] == 'deleted'

    def test_update_for_unknown_workout_is_ignored(self):
        reg.record_updated(999, name="duch")
        assert reg.find_workout(999) is None

    def test_renamed_workout_matches_its_activity(self):
        """The whole point: a rename must not orphan the usage history."""
        reg.record_added("Łatwy 32 min", "2026-09-25", 111)
        reg.record_updated(111, name="Easy 30 min (Z2) + tempo = 42")
        w = reg.find_workout(111)
        assert reg.matches_activity(
            w['name'], "Wieliczka - Easy 30 min (Z2) + tempo = 42")


class TestRestore:
    def test_restore_entry_returns_definition(self):
        reg.record_added("A", "2026-09-17", 111, definition={'workoutName': 'A'})
        assert reg.restore_entry(111)['definition'] == {'workoutName': 'A'}

    def test_restore_entry_unknown_raises(self):
        with pytest.raises(KeyError):
            reg.restore_entry(999)

    def test_deleted_workout_keeps_what_is_needed_to_restore(self):
        reg.record_added("A", "2026-09-17", 111, spec={'kind': 'easy_run'})
        reg.record_deleted(111)
        entry = reg.restore_entry(111)
        assert entry['status'] == 'deleted'
        assert entry['spec'] == {'kind': 'easy_run'}


class TestMatchesActivity:
    def test_exact_name(self):
        assert reg.matches_activity("Luźne 11km", "Luźne 11km")

    def test_location_prefix(self):
        assert reg.matches_activity("Luźne 11km", "Wieliczka - Luźne 11km")

    def test_truncated_activity_name(self):
        # Garmin cuts activity names at 44 bytes and this one ends mid-word.
        activity = "Wieliczka - Regeneracja 35 min - strefa 2 (1"
        assert len(activity.encode('utf-8')) == reg.ACTIVITY_NAME_LIMIT
        assert reg.matches_activity("Regeneracja 35 min - strefa 2 (115-134)", activity)

    def test_truncated_name_with_polish_diacritics(self):
        """'Ł' costs two bytes, so truncation can land on 43 characters."""
        activity = "Wieliczka - Łatwy 45 min - 1km tempo + stre"
        assert len(activity) == 43
        assert len(activity.encode('utf-8')) == reg.ACTIVITY_NAME_LIMIT
        assert reg.matches_activity(
            "Łatwy 45 min - 1km tempo + strefa 2 + przebieżki", activity)

    def test_short_untruncated_name_is_not_a_prefix_match(self):
        # 15 bytes — nowhere near the limit, so no prefix matching
        assert not reg.matches_activity("Łatwy 45 min - 1km tempo + strefa 2", "Łatwy 45 min")

    def test_short_name_is_not_a_wildcard(self):
        assert not reg.matches_activity("Bieg", "Wieliczka Bieganie")
        assert not reg.matches_activity("Bieg", "Wieliczka - Bieg negative split")

    def test_unrelated_names_do_not_match(self):
        assert not reg.matches_activity("Luźne 11km", "Wieliczka - Tętno <150 5km")

    def test_empty_inputs_do_not_match(self):
        assert not reg.matches_activity("", "Wieliczka - Luźne 11km")
        assert not reg.matches_activity("Luźne 11km", "")


class TestCleanupCandidates:
    def test_freshly_created_workout_is_never_a_candidate(self):
        """No usage history yet must not look like 'unused for 90 days'."""
        reg.record_added("Jutrzejszy trening", "2026-09-17", 111)
        assert reg.cleanup_candidates(days=90) == []

    def test_old_and_never_used_is_a_candidate(self):
        reg._append({'event': 'added', 'workout_id': 111, 'name': 'Stary',
                     'ts': '2020-01-01T00:00:00'})
        assert [w['workout_id'] for w in reg.cleanup_candidates(days=90)] == [111]

    def test_old_but_recently_used_is_kept(self):
        reg._append({'event': 'added', 'workout_id': 111, 'name': 'Stary',
                     'ts': '2020-01-01T00:00:00'})
        reg.record_usage(111, datetime.now().strftime('%Y-%m-%d'))
        assert reg.cleanup_candidates(days=90) == []

    def test_plan_workout_is_never_a_candidate(self):
        reg._append({'event': 'added', 'workout_id': 111, 'name': 'Bieg',
                     'ts': '2020-01-01T00:00:00', 'atp_plan_id': 1655847204})
        assert reg.cleanup_candidates(days=90) == []

    def test_deleted_workout_is_never_a_candidate(self):
        reg._append({'event': 'added', 'workout_id': 111, 'name': 'A',
                     'ts': '2020-01-01T00:00:00'})
        reg.record_deleted(111)
        assert reg.cleanup_candidates(days=90) == []


class TestStale:
    def test_old_active_workout_is_stale(self):
        old = (datetime.now() - timedelta(days=200)).replace(microsecond=0).isoformat()
        reg.record_added("stary", None, 111)
        # rewrite the timestamp to simulate age
        events = reg.load_events()
        events[0]['ts'] = old
        with open(reg.REGISTRY_PATH, 'w', encoding='utf-8') as f:
            for e in events:
                f.write(json.dumps(e, default=str) + '\n')

        assert [w['workout_id'] for w in reg.stale_workouts(days=90)] == [111]

    def test_fresh_workout_is_not_stale(self):
        reg.record_added("nowy", "2026-09-17", 111)
        assert reg.stale_workouts(days=90) == []

    def test_deleted_workout_is_never_stale(self):
        reg.record_added("A", "2020-01-01", 111)
        reg.record_deleted(111)
        assert reg.stale_workouts(days=1) == []

    def test_training_plan_workout_is_never_stale(self):
        """Garmin hides plan workouts from the library — they are archive, not clutter."""
        reg._append({'event': 'added', 'workout_id': 111, 'name': 'Bieg',
                     'ts': '2020-01-01T00:00:00', 'atp_plan_id': 1655847204})
        assert reg.stale_workouts(days=1) == []

    def test_plan_id_survives_replay(self):
        reg._append({'event': 'added', 'workout_id': 111, 'name': 'Bieg',
                     'ts': '2020-01-01T00:00:00', 'atp_plan_id': 1655847204})
        assert reg.find_workout(111)['atp_plan_id'] == 1655847204
