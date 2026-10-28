"""Testy danych raportu tygodniowego bez dostępu do plików lokalnych."""
from datetime import datetime
from typing import Any

import pytest

from services.data_extract import SnapshotReadResult, SnapshotStatus
from services.week import build_week_report


def _entry(workout_id=1, date: Any = '2026-12-28', **overrides):
    entry = {'workout_id': workout_id, 'date': date, 'name': 'Plan',
             'spec': {'kind': 'easy_run'}, 'status': 'active'}
    entry.update(overrides)
    return entry


def _activity(activity_id=10, date='2026-12-28 08:00', **overrides):
    activity = {'activity_id': activity_id, 'date': date, 'type': 'running/generic',
                'name': 'Plan', 'distance_km': 10.0, 'duration_min': 50.0}
    activity.update(overrides)
    return activity


def _report(entries=(), activities=(), status=SnapshotStatus.FRESH, now=datetime(2026, 12, 30)):
    snapshot = SnapshotReadResult(status, {'timestamp': '2026-12-30T08:00:00+00:00', 'activities': list(activities)})
    return build_week_report(snapshot=snapshot, registry_entries=list(entries), registry_status='ok',
                             availability={}, now=now)


def _day(report, date):
    return next(day for day in report.days if day.date == date)


def test_week_has_seven_days_across_year_boundary():
    report = _report()
    assert (report.week_start, report.week_end, len(report.days)) == ('2026-12-28', '2027-01-03', 7)


def test_two_runs_match_two_distinct_workouts():
    report = _report([_entry(1, name='Pięć'), _entry(2, name='Dziesięć')],
                     [_activity(10, name='Pięć', distance_km=5), _activity(11, name='Dziesięć', distance_km=10)])
    day = _day(report, '2026-12-28')
    assert {workout.matched_activity_id for workout in day.workouts} == {10, 11}


def test_one_run_for_two_workouts_is_uncertain_without_double_match():
    report = _report([_entry(1), _entry(2)], [_activity()])
    day = _day(report, '2026-12-28')
    assert day.status == 'uncertain'
    assert [workout.matched_activity_id for workout in day.workouts] == [None, None]


def test_walk_stays_visible_but_never_matches_run():
    report = _report([_entry()], [_activity(10), _activity(11, type='walking/generic')])
    day = _day(report, '2026-12-28')
    assert day.workouts[0].matched_activity_id == 10
    assert {activity.sport for activity in day.activities} == {'running/generic', 'walking/generic'}


def test_activity_without_plan_is_activity_only():
    assert _day(_report(activities=[_activity()]), '2026-12-28').status == 'activity_only'


def test_registry_activity_id_from_another_date_is_ignored():
    report = _report([_entry(activity_id=10)], [_activity(10, date='2026-12-29 08:00')])
    assert _day(report, '2026-12-28').workouts[0].matched_activity_id is None


def test_today_without_activity_is_planned_and_past_is_no_record():
    report = _report([_entry(1, '2026-12-30'), _entry(2, '2026-12-28')])
    assert _day(report, '2026-12-30').status == 'planned'
    assert _day(report, '2026-12-28').status == 'no_record'


@pytest.mark.parametrize('status', [SnapshotStatus.MISSING, SnapshotStatus.INVALID, SnapshotStatus.STALE])
def test_bad_or_stale_snapshot_keeps_plan_visible(status):
    report = _report([_entry()], status=status)
    assert _day(report, '2026-12-28').workouts
    if status == SnapshotStatus.STALE:
        assert 'snapshot_stale' in report.warnings


def test_filters_atp_undated_and_outside_entries_but_keeps_missing_schedule_id():
    report = _report([_entry(1, atp_plan_id=7), _entry(2, **{'date': None}),
                      _entry(3, '2027-01-04'), _entry(4, schedule_id=None)])
    workouts = _day(report, '2026-12-28').workouts
    assert [(workout.workout_id, workout.schedule_id) for workout in workouts] == [(4, None)]


def test_duplicate_workout_id_does_not_break_report_and_default_availability_is_unconfigured():
    report = _report([_entry(1), _entry(1)])
    day = _day(report, '2026-12-28')
    assert len(day.workouts) == 2
    assert day.availability is None


def test_zero_default_availability_is_unconfigured():
    report = build_week_report(snapshot=SnapshotReadResult(SnapshotStatus.FRESH, {'activities': []}),
                               registry_entries=[], registry_status='ok',
                               availability={'mon': {'available': False, 'min_minutes': 0, 'max_minutes': 0}},
                               now=datetime(2026, 12, 30))
    availability = _day(report, '2026-12-28').availability
    assert availability is not None
    assert availability.configured is False


def test_week_summary_includes_activity_totals_heart_rate_and_workout_counts():
    report = _report(
        [_entry(1, spec={'kind': 'hr_zone_run', 'duration_min': 30, 'zone_number': 2}),
         _entry(2, name='Niedopasowany')],
        [_activity(10, distance_km=5.5, duration_min=31.0, avg_hr=140),
         _activity(11, name='Spacer', type='walking/generic', distance_km=2.0,
                   duration_min=20.0, avg_hr=120)],
    )
    workout = _day(report, '2026-12-28').workouts[0]

    assert (workout.planned_duration_min, workout.hr_zone) == (30, 'Z2')
    assert report.summary is not None
    assert (report.summary.total_distance_km, report.summary.total_duration_min,
            report.summary.average_hr, report.summary.completed_workouts,
            report.summary.planned_workouts) == (7.5, 51.0, 130, 1, 2)
    assert _day(report, '2026-12-28').activities[0].avg_hr == 140


def test_week_shows_planned_duration_and_zone_from_the_registry_spec():
    report = _report([_entry(1, spec={'kind': 'hr_zone_run', 'duration_min': 40, 'zone_number': 2})])

    workout = _day(report, '2026-12-28').workouts[0]
    assert (workout.planned_duration_min, workout.hr_zone) == (40, 'Z2')


def test_week_counts_interval_time_from_warmup_work_rest_and_cooldown():
    report = _report([_entry(1, spec={'kind': 'threshold_intervals', 'num_intervals': 3,
                                      'work_sec': 360, 'rest_sec': 120,
                                      'warmup_min': 10, 'cooldown_min': 8})])

    assert _day(report, '2026-12-28').workouts[0].planned_duration_min == 40


def test_week_without_numbers_in_the_spec_keeps_the_block_empty():
    report = _report([_entry(1, spec={})])

    workout = _day(report, '2026-12-28').workouts[0]
    assert (workout.planned_duration_min, workout.hr_zone) == (None, None)


def test_week_summary_without_heart_rate_keeps_average_as_none():
    report = _report(activities=[_activity(avg_hr=None)])

    assert report.summary is not None
    assert (report.summary.total_distance_km, report.summary.total_duration_min,
            report.summary.average_hr) == (10.0, 50.0, None)


def test_empty_week_summary_uses_none_for_activity_totals():
    report = _report()

    assert report.summary is not None
    assert (report.summary.total_distance_km, report.summary.total_duration_min,
            report.summary.average_hr, report.summary.completed_workouts,
            report.summary.planned_workouts) == (None, None, None, 0, 0)


@pytest.mark.parametrize('schedule_status', ['pending', 'unknown'])
def test_unconfirmed_schedule_is_not_a_planned_week_workout(schedule_status):
    report = _report([_entry(date=None, intended_date='2026-12-28',
                             schedule_status=schedule_status)])

    assert _day(report, '2026-12-28').workouts == []


def test_confirmed_schedule_remains_a_planned_week_workout():
    report = _report([_entry(date='2026-12-28', intended_date='2026-12-28',
                             schedule_status='confirmed')])

    assert [workout.workout_id for workout in _day(report, '2026-12-28').workouts] == [1]


def test_incomplete_warning_depends_on_snapshot_format():
    from services.week import _activities_may_be_truncated
    activities = [{}] * 60
    assert _activities_may_be_truncated({'window': {'activity_days': 120}}, activities) is False
    assert _activities_may_be_truncated({}, activities) is True
    assert _activities_may_be_truncated({}, [{}] * 10) is False
