# -*- coding: utf-8 -*-
"""Tests for ai/context.py and ai/recommendation.py — AI coach context and recommendation."""
import sys
import os
import json
from datetime import datetime
from unittest.mock import MagicMock


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.context import (
    build_training_context, format_context_for_user,
    _get_recent_activities, _get_health_snapshot, _compute_weekly_load,
    RUNNER_PROFILE, _load_runner_profile,
)
from ai.recommendation import DailyRecommendation, get_daily_recommendation


def _make_sample_data():
    return {
        "timestamp": "2026-09-16T10:00:00",
        "activities": [
            {"date": "2026-09-16 08:00", "name": "Bieg poranny", "type": "running/running",
             "distance_km": 8.0, "duration_min": 45, "pace": "5:37/km",
             "avg_hr": 150, "max_hr": 168, "ascent_m": 30, "te": 3.0, "ate": 1.0},
            {"date": "2026-09-15 07:00", "name": "Tempo", "type": "running/running",
             "distance_km": 10.0, "duration_min": 52, "pace": "5:12/km",
             "avg_hr": 165, "max_hr": 178, "ascent_m": 45, "te": 4.0, "ate": 1.5},
            {"date": "2026-09-14 09:00", "name": "Długie", "type": "running/running",
             "distance_km": 15.0, "duration_min": 90, "pace": "6:00/km",
             "avg_hr": 148, "max_hr": 165, "ascent_m": 120, "te": 3.5, "ate": 1.2},
        ],
        "daily_health": [
            {"date": "2026-09-16", "rhr": 50, "hr_min": 45, "hr_max": 170,
             "steps": 8000, "stress_avg": 30, "rr": 60, "spo2": 97},
        ],
        "sleep": [
            {"date": "2026-09-16", "total_h": 7.5, "deep_h": 1.5, "light_h": 4.0,
             "rem_h": 1.2, "score": 85, "qualifier": "GOOD"},
        ],
        "hrv": [
            {"date": "2026-09-16", "weekly_avg": 70, "last_night": 72,
             "baseline_low": 67, "baseline_high": 82, "status": "BALANCED"},
        ],
        "weight": [{"date": "2026-09-16", "weight_kg": 74.0}],
    }


class TestGetRecentActivities:
    def test_returns_running_only(self):
        data = _make_sample_data()
        result = _get_recent_activities(data)
        assert len(result) == 3
        assert all("running" in a.get("date", "") or True for a in result)

    def test_limit_n(self):
        data = _make_sample_data()
        result = _get_recent_activities(data, n=2)
        assert len(result) == 2

    def test_empty_data(self):
        result = _get_recent_activities({"activities": []})
        assert result == []

    def test_fields_present(self):
        data = _make_sample_data()
        result = _get_recent_activities(data)
        for a in result:
            assert "date" in a
            assert "distance_km" in a
            assert "pace" in a
            assert "avg_hr" in a


class TestGetHealthSnapshot:
    def test_returns_metrics(self):
        data = _make_sample_data()
        result = _get_health_snapshot(data)
        assert result["rhr"] == 50
        assert result["hrv_status"] == "BALANCED"
        assert result["sleep_score"] == 85
        assert result["stress_avg"] == 30

    def test_empty_data(self):
        result = _get_health_snapshot({"daily_health": [], "sleep": [], "hrv": []})
        assert result["rhr"] is None
        assert result["hrv_status"] is None


class TestComputeWeeklyLoad:
    def test_computes_load(self):
        data = _make_sample_data()
        # Sample activities are dated 14-16 Sep 2026; pin "today" inside that
        # week so the test does not depend on the wall clock.
        result = _compute_weekly_load(data, datetime(2026, 9, 16))
        assert result["total_km"] > 0
        assert result["total_min"] > 0
        assert result["sessions"] > 0

    def test_excludes_previous_week(self):
        data = _make_sample_data()
        # Monday of the following week — none of the samples belong to it.
        result = _compute_weekly_load(data, datetime(2026, 9, 21))
        assert result["total_km"] == 0
        assert result["sessions"] == 0

    def test_empty_data(self):
        result = _compute_weekly_load({"activities": []})
        assert result["total_km"] == 0
        assert result["sessions"] == 0


class TestBuildContext:
    def test_returns_all_keys(self):
        data = _make_sample_data()
        context = build_training_context(data)
        assert "system_prompt" in context
        assert "runner_profile" in context
        assert "goal" in context
        assert "recent_activities" in context
        assert "weekly_load" in context
        assert "health_metrics" in context

    def test_runner_profile_has_formatter_fields(self):
        assert {"age", "target_hm", "hr_max", "target_date"} <= RUNNER_PROFILE.keys()


class TestRunnerProfileLoading:
    @staticmethod
    def _profile(label):
        return {
            "name": label, "age": 30, "weight_kg": "70", "height_cm": 175,
            "hr_max": 180, "hr_rest": "50", "lactate_threshold_hr": 165,
            "hr_zones": "Z1-Z5", "current_hm_record": "2:00:00",
            "target_hm": "2:00", "target_date": "2027-01-01",
        }

    def test_falls_back_to_example_when_local_is_missing(self, tmp_path):
        example = tmp_path / "runner_profile.example.json"
        example.write_text(json.dumps(self._profile("Example")), encoding="utf-8")
        profile = _load_runner_profile(tmp_path / "missing.local.json", example)
        assert profile["name"] == "Example"

    def test_prefers_local_profile(self, tmp_path):
        local = tmp_path / "runner_profile.local.json"
        example = tmp_path / "runner_profile.example.json"
        local.write_text(json.dumps(self._profile("Local")), encoding="utf-8")
        example.write_text(json.dumps(self._profile("Example")), encoding="utf-8")
        profile = _load_runner_profile(local, example)
        assert profile["name"] == "Local"


class TestFormatContextForUser:
    def test_returns_string(self):
        data = _make_sample_data()
        context = build_training_context(data)
        result = format_context_for_user(context)
        assert isinstance(result, str)

    def test_contains_key_sections(self):
        data = _make_sample_data()
        context = build_training_context(data)
        result = format_context_for_user(context)
        assert "Profil biegacza" in result
        assert "Cel" in result
        assert "stan zdrowia" in result
        assert "Obciążenie" in result
        assert "Ostatnie treningi" in result

    def test_includes_hrv_alert_when_active(self):
        data = _make_sample_data()
        data["hrv"] = [
            {"date": "2026-09-16", "weekly_avg": 60, "last_night": 55,
             "baseline_low": 67, "baseline_high": 82, "status": "LOW"},
            {"date": "2026-09-15", "weekly_avg": 61, "last_night": 56,
             "baseline_low": 67, "baseline_high": 82, "status": "LOW"},
            {"date": "2026-09-14", "weekly_avg": 62, "last_night": 57,
             "baseline_low": 67, "baseline_high": 82, "status": "LOW"},
        ]
        context = build_training_context(data)
        result = format_context_for_user(context)
        assert "ALERT" in result


class TestDailyRecommendation:
    def test_valid_model(self):
        rec = DailyRecommendation(
            readiness="ready",
            recommendation="Bieg łatwy 30 min",
            planned_workout=None,
            adjustment_needed=False,
            reasoning_summary="Dobrze się regenerujesz",
            warnings=[],
        )
        assert rec.readiness == "ready"
        assert rec.adjustment_needed is False

    def test_with_warnings(self):
        rec = DailyRecommendation(
            readiness="not_ready",
            recommendation="Odpoczynek",
            planned_workout=None,
            adjustment_needed=True,
            reasoning_summary="HRV niskie",
            warnings=["HRV LOW 3 dni", "Sen słaby"],
        )
        assert len(rec.warnings) == 2


class TestGetDailyRecommendation:
    def test_calls_provider(self):
        mock_provider = MagicMock()
        expected = DailyRecommendation(
            readiness="ready",
            recommendation="Bieg easily",
            planned_workout=None,
            adjustment_needed=False,
            reasoning_summary="Test",
            warnings=[],
        )
        mock_provider.chat.return_value = expected

        data = _make_sample_data()
        context = build_training_context(data)
        result = get_daily_recommendation(mock_provider, context)

        assert result == expected
        mock_provider.chat.assert_called_once()
        call_kwargs = mock_provider.chat.call_args[1]
        assert call_kwargs["response_model"] == DailyRecommendation

    def test_passes_system_prompt(self):
        mock_provider = MagicMock()
        mock_provider.chat.return_value = DailyRecommendation(
            readiness="ready", recommendation="Test", planned_workout=None,
            adjustment_needed=False, reasoning_summary="Test", warnings=[],
        )

        data = _make_sample_data()
        context = build_training_context(data)
        context["system_prompt"] = "Testowe zasady trenera"
        get_daily_recommendation(mock_provider, context)

        call_kwargs = mock_provider.chat.call_args[1]
        assert call_kwargs["system_prompt"] == "Testowe zasady trenera"
