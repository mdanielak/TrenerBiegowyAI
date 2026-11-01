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
        result = compute_readiness_breakdown(data, rhr_baseline=48)
        assert result['score'] == 10.0
        assert result['raw_score'] == 10.0
        assert result['available_max_score'] == 10.0
        assert result['confidence'] == 'high'
        assert result['insufficient_data'] is False
        assert result['level'] == 'ready'

    def test_zero_score(self):
        # Bez normy snu i stresu obowiązują kategorie Garmina: poniżej 60 i powyżej 50 to 0 pkt.
        data = _make_data(rhr=56, hrv_status='LOW', hrv_last=55,
                          hrv_low=67, sleep_score=55, stress=55)
        result = compute_readiness_breakdown(data, rhr_baseline=48)
        assert result['score'] == 0
        assert result['level'] == 'not_ready'

    def test_partial_score_ready_with_reserves(self):
        data = _make_data(rhr=52, hrv_status='BALANCED', hrv_last=65,
                          hrv_low=67, sleep_score=80, stress=35)
        result = compute_readiness_breakdown(data, rhr_baseline=48)
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
        result = compute_readiness_breakdown(data, rhr_baseline=48)
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




def test_resting_heart_rate_is_judged_against_the_runners_own_norm():
    """Norma 62 bpm i pomiar 63 to „w normie” — stałe progi (≤ 49 bpm) dawały tu „podwyższone”."""
    from services.readiness import rhr_baseline
    history = [{"date": f"2026-10-{day:02d}", "rhr": 62} for day in range(1, 29)]
    assert rhr_baseline(history, "2026-10-29") == 62
    assert rhr_baseline(history[:6], "2026-10-29") is None  # za mało pomiarów
    assert rhr_baseline(history, "2026-10-15") == 62  # liczą się tylko dni przed oceną

    def verdict(rhr, norm):
        detail = compute_readiness_breakdown(_make_data(rhr=rhr), rhr_baseline=norm)["details"][0]
        return detail["status"], detail["message"]

    assert verdict(63, 62) == ("OK", "Tętno spoczynkowe w Twojej normie (63 bpm, norma 62)")
    assert verdict(66, 62)[0] == "WARN" and verdict(68, 62)[0] == "FAIL" and verdict(58, 62)[0] == "OK"
    unknown = compute_readiness_breakdown(_make_data(rhr=63))
    assert "rhr" in unknown["missing_metrics"] and "Za mało pomiarów" in unknown["details"][0]["message"]



def _history(days, **values):
    """Dni przed 2026-10-02 z tymi samymi wartościami (lista wartości = wahania)."""
    from datetime import date, timedelta
    out = []
    for i in range(days):
        day = (date(2026, 10, 2) - timedelta(days=i + 1)).isoformat()
        out.append({"date": day, **{k: (v[i % len(v)] if isinstance(v, list) else v) for k, v in values.items()}})
    return out


def _score(metric, health=None, sleep=None, history_health=None, history_sleep=None):
    from services.readiness import personal_norms, compute_readiness_breakdown
    data = {"daily_health": [{"date": "2026-10-02", **(health or {})}] + (history_health or []),
            "sleep": ([{"date": "2026-10-02", **sleep}] if sleep else []) + (history_sleep or []), "hrv": []}
    result = compute_readiness_breakdown(data, norms=personal_norms(data, "2026-10-02"))
    return next(d for d in result["details"] if d["metric"] == metric)


def test_stress_is_judged_against_the_persons_own_average():
    calm = _history(15, stress_avg=[20, 22, 24])     # osoba zwykle spokojna
    busy = _history(15, stress_avg=[36, 38, 40])     # osoba z wymagającą pracą
    assert _score("Stress", {"stress_avg": 34}, history_health=calm)["points"] < 2
    assert _score("Stress", {"stress_avg": 38}, history_health=busy)["points"] == 2


def test_garmin_floors_hold_regardless_of_the_norm():
    poor_sleeper = _history(14, score=[55, 58, 60], sleep_score=None)
    assert _score("Sleep", sleep={"score": 57}, history_sleep=poor_sleeper)["points"] == 0   # poniżej 60 zawsze słaby
    assert _score("Sleep", sleep={"score": 92}, history_sleep=_history(14, score=95))["points"] == 2.5  # 90+ zawsze dobry
    stressed = _history(14, stress_avg=[55, 58, 60])
    assert _score("Stress", {"stress_avg": 56}, history_health=stressed)["points"] == 0       # powyżej 50 zawsze 0


def test_without_a_week_of_data_garmin_categories_are_used():
    assert _score("Sleep", sleep={"score": 85})["points"] == 2.5
    assert _score("Sleep", sleep={"score": 70})["points"] == 1.5
    assert _score("Stress", {"stress_avg": 30})["points"] == 1


def test_resting_hr_tolerance_follows_the_persons_variability():
    steady = _history(14, rhr=50)                        # bardzo równe pomiary: wahania przyjmowane jako 2 bpm
    jumpy = _history(15, rhr=[46, 50, 54])               # duże wahania
    assert _score("RHR", {"rhr": 53}, history_health=steady)["points"] == 1.5
    assert _score("RHR", {"rhr": 53}, history_health=jumpy)["points"] == 2.5


def test_scoring_text_names_the_persons_own_numbers_and_matches_the_points():
    detail = _score("Stress", {"stress_avg": 30}, history_health=_history(15, stress_avg=[20, 22, 24]))
    assert "Twoja średnia 22" in detail["scoring"] and "2 pkt — do 26" in detail["scoring"]
    assert detail["points"] == 1 and "1 pkt — 27–32" in detail["scoring"]
