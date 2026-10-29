# -*- coding: utf-8 -*-
"""Testy czystej logiki dopasowywania aktywności."""

from services.activity_matching import assign_activities, find_activity_for_workout


def match_activity_for_workout(*, workout, activities):
    """Identyfikator dopasowanej aktywności i metoda — z funkcji, której używa aplikacja."""
    activity, method = find_activity_for_workout(workout=workout, activities=activities)
    return (activity or {}).get('activity_id'), method


def _workout(**overrides):
    workout = {
        'date': '2026-09-15',
        'name': 'Easy run',
        'distance_km': 10.0,
    }
    workout.update(overrides)
    return workout


def _activity(activity_id, **overrides):
    activity = {
        'activity_id': activity_id,
        'date': '2026-09-15 08:00',
        'type': 'running/running',
        'name': 'Bieg',
        'distance_km': 10.0,
    }
    activity.update(overrides)
    return activity


def test_matches_explicit_activity_id():
    activity_id, method = match_activity_for_workout(
        workout=_workout(matched_activity_id='42'),
        activities=[_activity(42), _activity(7)],
    )

    assert (activity_id, method) == (42, 'id')


def test_ignores_non_running_activity():
    activity_id, method = match_activity_for_workout(
        workout=_workout(),
        activities=[_activity(1, type='walking/generic'), _activity(2, distance_km=11)],
    )

    assert (activity_id, method) == (2, 'heuristic')


def test_ignores_activity_from_another_date():
    activity_id, method = match_activity_for_workout(
        workout=_workout(),
        activities=[_activity(1, date='2026-09-14 08:00')],
    )

    assert (activity_id, method) == (None, 'unmatched')


def test_prefers_closer_distance():
    activity_id, method = match_activity_for_workout(
        workout=_workout(),
        activities=[_activity(1, distance_km=8), _activity(2, distance_km=10.5)],
    )

    assert (activity_id, method) == (2, 'heuristic')


def test_name_match_breaks_distance_tie():
    activity_id, method = match_activity_for_workout(
        workout=_workout(),
        activities=[_activity(1, name='Inny bieg'), _activity(2, name='Easy run')],
    )

    assert (activity_id, method) == (2, 'heuristic')


def test_returns_ambiguous_for_equally_ranked_activities():
    activity_id, method = match_activity_for_workout(
        workout=_workout(),
        activities=[_activity(1), _activity(2)],
    )

    assert (activity_id, method) == (None, 'ambiguous')


def test_returns_unmatched_when_no_activity_exists_that_day():
    activity_id, method = match_activity_for_workout(
        workout=_workout(),
        activities=[_activity(1, date='2026-09-16 08:00')],
    )

    assert (activity_id, method) == (None, 'unmatched')


def test_returns_unmatched_for_empty_activity_list():
    activity_id, method = match_activity_for_workout(workout=_workout(), activities=[])

    assert (activity_id, method) == (None, 'unmatched')


def test_assignments_do_not_reuse_one_activity_for_two_workouts():
    assignments = assign_activities(
        workouts=[_workout(distance_km=10), _workout(distance_km=10)],
        activities=[_activity(1)],
    )

    assert assignments[0][1] == assignments[1][1] == 'ambiguous'
