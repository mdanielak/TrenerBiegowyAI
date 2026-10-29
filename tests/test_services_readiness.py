# -*- coding: utf-8 -*-
"""Tests for services/readiness.py — readiness assessment and plan comparison."""
import sys
import os
from datetime import datetime


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.readiness import (
    compare_plan_vs_actual,
    compute_readiness_breakdown,
    readiness_for_day,
    signal_trends,
)


def _make_data(rhr: object = 50, hrv_status: object = 'BALANCED', hrv_last: object = 75,
               hrv_low: object = 67, hrv_high: object = 82, sleep_score: object = 85,
               sleep_total: object = 7.5, stress: object = 30):
    return {
        'daily_health': [{'rhr': rhr, 'stress_avg': stress}],
        'sleep': [{'score': sleep_score, 'total_h': sleep_total}],
        'hrv': [{'status': hrv_status, 'last_night': hrv_last,
                 'baseline_low': hrv_low, 'baseline_high': hrv_high}],
    }


class TestReadinessBreakdown:
    def test_perfect_score(self):
        data = _make_data(rhr=48, hrv_status='BALANCED', hrv_last=78,
                          hrv_low=67, sleep_score=92, stress=25)
        result = compute_readiness_breakdown(data)
        assert result['score'] == 10.0
        assert result['raw_score'] == 10.0
        assert result['available_max_score'] == 10.0
        assert result['confidence'] == 'high'
        assert result['insufficient_data'] is False
        assert result['level'] == 'ready'

    def test_zero_score(self):
        data = _make_data(rhr=56, hrv_status='LOW', hrv_last=55,
                          hrv_low=67, sleep_score=65, stress=45)
        result = compute_readiness_breakdown(data)
        assert result['score'] == 0
        assert result['level'] == 'not_ready'

    def test_partial_score_ready_with_reserves(self):
        data = _make_data(rhr=52, hrv_status='BALANCED', hrv_last=65,
                          hrv_low=67, sleep_score=80, stress=35)
        result = compute_readiness_breakdown(data)
        assert 0 < result['score'] < 10
        assert result['level'] in ('ready', 'ready_with_reserves')

    def test_one_missing_metric_normalizes_score(self):
        data = _make_data(rhr=None, hrv_status='BALANCED', hrv_last=78,
                          hrv_low=67, sleep_score=92, stress=25)
        result = compute_readiness_breakdown(data)
        assert result['raw_score'] == 7.5
        assert result['available_max_score'] == 7.5
        assert result['score'] == 10.0
        assert result['missing_metrics'] == ['rhr']
        assert result['available_metrics'] == ['hrv', 'sleep', 'stress']
        assert result['data_coverage'] == 0.75
        assert result['confidence'] == 'medium'

    def test_multiple_missing_metrics(self):
        data = _make_data(rhr=None, hrv_status=None, hrv_last=None,
                          hrv_low=None, hrv_high=None, sleep_score=92, stress=None)
        result = compute_readiness_breakdown(data)
        assert result['score'] == 10.0
        assert result['missing_metrics'] == ['rhr', 'hrv', 'stress']
        assert result['confidence'] == 'low'

    def test_empty_data(self):
        data = {'daily_health': [], 'sleep': [], 'hrv': []}
        result = compute_readiness_breakdown(data)
        assert result['score'] == 0
        assert result['level'] == 'no_data'  # brak pomiarów to nie zła ocena
        assert {d['status'] for d in result['details']} == {'UNKNOWN'}
        assert result['missing_metrics'] == ['rhr', 'hrv', 'sleep', 'stress']
        assert result['available_max_score'] == 0
        assert result['data_coverage'] == 0
        assert result['confidence'] == 'none'

    def test_fail_is_an_available_metric(self):
        data = _make_data(rhr=56, hrv_status='LOW', hrv_last=55,
                          hrv_low=67, sleep_score=65, stress=45)
        result = compute_readiness_breakdown(data)
        assert result['available_metrics'] == ['rhr', 'hrv', 'sleep', 'stress']
        assert result['missing_metrics'] == []
        assert result['insufficient_data'] is False

    def test_details_has_all_metrics(self):
        data = _make_data()
        result = compute_readiness_breakdown(data)
        metrics = {d['metric'] for d in result['details']}
        assert metrics == {'RHR', 'HRV', 'Sleep', 'Stress'}

    def test_max_score_is_10(self):
        data = _make_data()
        result = compute_readiness_breakdown(data)
        assert result['max_score'] == 10


class TestReadinessForDay:
    def test_uses_all_records_for_requested_day(self):
        data = {
            'daily_health': [
                {'date': '2026-10-02', 'rhr': 48, 'stress_avg': 25},
                {'date': '2026-10-01', 'rhr': 56, 'stress_avg': 45},
            ],
            'sleep': [
                {'date': '2026-10-02', 'score': 92, 'total_h': 8.0},
                {'date': '2026-10-01', 'score': 65, 'total_h': 5.0},
            ],
            'hrv': [
                {'date': '2026-10-02', 'status': 'BALANCED', 'last_night': 78,
                 'baseline_low': 67, 'baseline_high': 82},
            ],
        }

        result = readiness_for_day(data, '2026-10-02')

        assert result['score'] == 10.0
        assert result['level'] == 'ready'

    def test_returns_none_without_health_record(self):
        data = _make_data()
        assert readiness_for_day(data, '2026-10-02') is None

    def test_marks_sleep_missing_when_health_record_exists(self):
        data = {
            'daily_health': [{'date': '2026-10-02', 'rhr': 48, 'stress_avg': 25}],
            'sleep': [],
            'hrv': [{'date': '2026-10-02', 'status': 'BALANCED', 'last_night': 78,
                     'baseline_low': 67, 'baseline_high': 82}],
        }

        result = readiness_for_day(data, '2026-10-02')

        assert result['sleep_score_val'] is None
        assert 'sleep' in result['missing_metrics']


class TestSignalTrends:
    def test_reports_rising_falling_and_flat_signals(self):
        data = {
            'daily_health': [
                {'date': '2026-10-02', 'rhr': 48, 'stress_avg': 30},
                {'date': '2026-10-01', 'rhr': 50, 'stress_avg': 30},
            ],
            'sleep': [
                {'date': '2026-10-02', 'score': 90},
                {'date': '2026-10-01', 'score': 80},
            ],
        }

        result = signal_trends(data, '2026-10-02')

        assert result['rhr'] == {
            'current': 48, 'previous': 50, 'direction': 'down', 'favorable': True,
        }
        assert result['stress_avg']['direction'] == 'flat'
        assert result['stress_avg']['favorable'] is None
        assert result['sleep_score'] == {
            'current': 90, 'previous': 80, 'direction': 'up', 'favorable': True,
        }

    def test_returns_none_direction_without_previous_day(self):
        data = {
            'daily_health': [{'date': '2026-10-02', 'rhr': 48, 'stress_avg': 25}],
            'sleep': [{'date': '2026-10-02', 'score': 90}],
        }

        result = signal_trends(data, '2026-10-02')

        assert result['rhr'] == {
            'current': 48, 'previous': None, 'direction': None, 'favorable': None,
        }


class TestComparePlanVsActual:
    def _make_plan(self, workouts):
        return {
            'start_date': '2026-09-14',
            'end_date': '2026-09-20',
            'priority': 'Test',
            'workouts': workouts,
        }

    def _make_activity(self, date, name='Bieg', distance=10.0, pace='5:30/km',
                       avg_hr=150, max_hr=170):
        return {
            'date': f'{date} 08:00',
            'name': name,
            'type': 'running/running',
            'distance_km': distance,
            'pace': pace,
            'avg_hr': avg_hr,
            'max_hr': max_hr,
        }

    def test_all_done(self):
        plan = self._make_plan([
            {'date': '2026-09-15', 'day': 'Wt', 'type': 'easy', 'name': 'Easy',
             'distance_km': 10},
        ])
        activities = [self._make_activity('2026-09-15')]
        results = compare_plan_vs_actual(plan, activities, datetime(2026, 9, 16))
        assert len(results) == 1
        assert results[0]['status'] == 'OK'

    def test_missing_workout(self):
        plan = self._make_plan([
            {'date': '2026-09-15', 'day': 'Wt', 'type': 'easy', 'name': 'Easy',
             'distance_km': 10},
        ])
        results = compare_plan_vs_actual(plan, [], datetime(2026, 9, 16))
        assert results[0]['status'] == 'MISSING'

    def test_rest_day_ok(self):
        plan = self._make_plan([
            {'date': '2026-09-15', 'day': 'Wt', 'type': 'rest', 'name': 'Rest',
             'distance_km': 0},
        ])
        results = compare_plan_vs_actual(plan, [], datetime(2026, 9, 16))
        assert results[0]['status'] == 'OK'

    def test_rest_violation(self):
        plan = self._make_plan([
            {'date': '2026-09-15', 'day': 'Wt', 'type': 'rest', 'name': 'Rest',
             'distance_km': 0},
        ])
        activities = [self._make_activity('2026-09-15')]
        results = compare_plan_vs_actual(plan, activities, datetime(2026, 9, 16))
        assert results[0]['status'] == 'REST_VIOLATION'

    def test_scheduled_future(self):
        plan = self._make_plan([
            {'date': '2026-09-20', 'day': 'Nd', 'type': 'long', 'name': 'Long',
             'distance_km': 15},
        ])
        results = compare_plan_vs_actual(plan, [], datetime(2026, 9, 16))
        assert results[0]['status'] == 'SCHEDULED'

    def test_is_today_flag(self):
        plan = self._make_plan([
            {'date': '2026-09-16', 'day': 'Sr', 'type': 'easy', 'name': 'Easy',
             'distance_km': 8},
        ])
        results = compare_plan_vs_actual(plan, [], datetime(2026, 9, 16))
        assert results[0]['is_today'] is True

    def test_not_today_flag(self):
        plan = self._make_plan([
            {'date': '2026-09-15', 'day': 'Wt', 'type': 'easy', 'name': 'Easy',
             'distance_km': 8},
        ])
        results = compare_plan_vs_actual(plan, [], datetime(2026, 9, 16))
        assert results[0]['is_today'] is False


