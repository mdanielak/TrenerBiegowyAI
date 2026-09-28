# -*- coding: utf-8 -*-
"""Tests for services/workouts.py and garmin_workout.py — workout builder."""
import sys
import os
import types
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock garminconnect before importing garmin_workout
_mock_garminconnect = types.ModuleType('garminconnect')
_mock_garminconnect.Garmin = MagicMock()
_mock_workout = types.ModuleType('garminconnect.workout')
_mock_workout.RunningWorkout = MagicMock
_mock_workout.WorkoutSegment = MagicMock
_mock_workout.ExecutableStep = MagicMock
_mock_workout.StepType = MagicMock()
_mock_workout.StepType.WARMUP = 3
_mock_workout.StepType.INTERVAL = 4
_mock_workout.StepType.COOLDOWN = 5
_mock_workout.StepType.RECOVERY = 6
_mock_workout.TargetType = MagicMock()
_mock_workout.TargetType.HEART_RATE_ZONE = 4
_mock_workout.TargetType.PACE_ZONE = 6
sys.modules['garminconnect'] = _mock_garminconnect
sys.modules['garminconnect.workout'] = _mock_workout

from garmin_workout import GarminWorkout


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    """Keep the workout registry out of the real training-plans directory."""
    monkeypatch.setattr('services.workout_registry.REGISTRY_PATH',
                        tmp_path / "_garmin_workouts.jsonl")


class TestPaceConversion:
    def test_pace_to_ms_five_min(self):
        assert GarminWorkout._pace_to_ms("5:00") == 3.3333

    def test_pace_to_ms_six_min(self):
        assert GarminWorkout._pace_to_ms("6:00") == 2.7778

    def test_pace_to_ms_with_spaces(self):
        assert GarminWorkout._pace_to_ms(" 5:00 ") == 3.3333

    def test_pace_to_ms_three_thirty(self):
        result = GarminWorkout._pace_to_ms("3:30")
        expected = round(1000.0 / 210, 4)
        assert result == expected


class TestMakeStep:
    def test_basic_step(self):
        step = GarminWorkout._make_step(1, 3, "warmup", 600)
        assert step.stepOrder == 1
        assert step.endConditionValue == 600.0

    def test_step_with_pace_target(self):
        step = GarminWorkout._make_step(
            1, 3, "interval", 300,
            target_type_id=6, target_type_key="pace.zone",
            target_value_one=3.33, target_value_two=3.0,
        )
        assert step.targetValueOne == 3.33
        assert step.targetValueTwo == 3.0


class TestGarminWorkoutInit:
    def test_init_with_params(self):
        gw = GarminWorkout(email="test@test.com", password="pass123")
        assert gw.email == "test@test.com"
        assert gw.password == "pass123"

    @patch('garmin_workout.GARMIN_EMAIL', 'env@test.com')
    @patch('garmin_workout.GARMIN_PASSWORD', 'envpass')
    def test_init_from_env(self):
        gw = GarminWorkout()
        assert gw.email == "env@test.com"
        assert gw.password == "envpass"

    def test_init_no_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            gw = GarminWorkout()
            assert gw.email == ""
            assert gw.password == ""


class TestLogin:
    def test_login_without_credentials_falls_back_to_token_store(self):
        """No env credentials -> use the cached GarminDB OAuth token store."""
        adapter = MagicMock()
        adapter.client = MagicMock()
        fake_module = types.ModuleType('garmindb.garmin_connect_auth_adapter')
        fake_module.GarminConnectAuthAdapter = MagicMock(return_value=adapter)
        fake_config = types.ModuleType('garmindb.garmin_connect_config_manager')
        fake_config.GarminConnectConfigManager = MagicMock(return_value=MagicMock())

        with patch.dict(sys.modules, {
            'garmindb.garmin_connect_auth_adapter': fake_module,
            'garmindb.garmin_connect_config_manager': fake_config,
        }):
            gw = GarminWorkout(email=None, password=None)
            result = gw.login()

        adapter.login.assert_called_once()
        assert gw.api is adapter.client
        assert result is gw

    def test_login_success(self):
        mock_api = MagicMock()
        _mock_garminconnect.Garmin.return_value = mock_api

        gw = GarminWorkout(email="test@test.com", password="pass")
        result = gw.login()

        _mock_garminconnect.Garmin.assert_called_with("test@test.com", "pass")
        mock_api.login.assert_called_once()
        assert result is gw


class TestWorkoutBuilders:
    @pytest.fixture
    def mock_gw(self):
        gw = GarminWorkout(email="test@test.com", password="pass")
        gw.api = MagicMock()
        gw.api.upload_running_workout.return_value = {"workoutId": 12345}
        return gw

    def test_easy_run(self, mock_gw):
        wid = mock_gw.easy_run("Test", 30, "2026-09-20")
        assert wid == 12345
        mock_gw.api.upload_running_workout.assert_called_once()
        mock_gw.api.schedule_workout.assert_called_once_with(12345, "2026-09-20")

    def test_long_run(self, mock_gw):
        wid = mock_gw.long_run("Long", 60, "2026-09-21")
        assert wid == 12345

    def test_tempo_run(self, mock_gw):
        wid = mock_gw.tempo_run("Tempo", 20, "5:00", "5:10", date_str="2026-09-19")
        assert wid == 12345

    def test_threshold_intervals(self, mock_gw):
        wid = mock_gw.threshold_intervals("5x3min", 5, 180, 120, "5:00", "5:10",
                                           date_str="2026-09-18")
        assert wid == 12345

    def test_strides(self, mock_gw):
        wid = mock_gw.strides("Biegi", 20, 4, "2026-09-17")
        assert wid == 12345

    def test_upload_failure_raises(self, mock_gw):
        mock_gw.api.upload_running_workout.side_effect = Exception("API Error")
        with pytest.raises(Exception, match="API Error"):
            mock_gw.easy_run("Fail", 30, "2026-09-20")


class TestZoneRunWarmup:
    """Reguła biegacza: bieg w strefie 2 ZAWSZE otwiera rozgrzewka na tempo,

    bez alarmu strefy. Na starcie tętno jest fizjologicznie niskie, więc alarm
    wyłby o "za niskim tętnie", zanim organizm wdroży pracę.
    """

    @pytest.fixture
    def mock_gw(self):
        gw = GarminWorkout(email="test@test.com", password="pass")
        gw.api = MagicMock()
        gw.api.upload_running_workout.return_value = {"workoutId": 12345}
        self.steps = []
        real = gw._make_step

        def spy(*args, **kwargs):
            self.steps.append((args, kwargs))
            return real(*args, **kwargs)

        gw._make_step = spy
        return gw

    def test_hr_zone_run_opens_with_pace_warmup(self, mock_gw):
        mock_gw.hr_zone_run("Długie 90 min", 90, 2, "2026-10-04")
        args, kwargs = self.steps[0]
        assert kwargs['target_type_key'] == 'pace.zone'
        assert args[3] == 360                      # 6 minut
        assert kwargs['target_value_one'] == GarminWorkout._pace_to_ms('7:00')
        assert kwargs['target_value_two'] == GarminWorkout._pace_to_ms('8:30')

    def test_warmup_carries_no_zone_alarm(self, mock_gw):
        mock_gw.hr_zone_run("Długie 90 min", 90, 2, "2026-10-04")
        _, kwargs = self.steps[0]
        assert 'zone_number' not in kwargs

    def test_zone_step_gets_the_remaining_time(self, mock_gw):
        mock_gw.hr_zone_run("Długie 90 min", 90, 2, "2026-10-04")
        args, kwargs = self.steps[1]
        assert kwargs['zone_number'] == 2
        assert args[3] == (90 - 6) * 60

    def test_total_time_is_unchanged_by_the_warmup(self, mock_gw):
        """`duration_min` to cały czas na nogach — rozgrzewka jest w nim, nie obok."""
        mock_gw.hr_zone_run("Długie 90 min", 90, 2, "2026-10-04")
        total = sum(a[3] for a, _ in self.steps)
        assert total == 90 * 60

    def test_warmup_can_be_disabled(self, mock_gw):
        mock_gw.hr_zone_run("Długie 90 min", 90, 2, "2026-10-04", warmup_min=0)
        assert len(self.steps) == 1
        assert self.steps[0][1]['zone_number'] == 2

    def test_easy_run_zoned_opens_with_warmup_and_adds_it_on_top(self, mock_gw):
        mock_gw.easy_run_zoned("Łatwy 45 min", "2026-09-28", main_min=39)
        args, kwargs = self.steps[0]
        assert kwargs['target_type_key'] == 'pace.zone'
        assert args[3] == 360
        assert self.steps[1][0][3] == 39 * 60       # część na tętno
        assert self.steps[1][1]['zone_number'] == 2

    def test_easy_run_zoned_reports_the_full_duration(self, mock_gw):
        mock_gw.easy_run_zoned("Łatwy 45 min", "2026-09-28", main_min=39)
        w = mock_gw.api.upload_running_workout.call_args[0][0]
        assert w.estimatedDurationInSecs == 45 * 60

    def test_legacy_warmup_km_still_builds_a_distance_step(self, mock_gw):
        """Stare wpisy rejestru mają `warmup_km` i muszą się dalej odtwarzać."""
        mock_gw.easy_run_zoned(
            "Stary trening", "2026-09-28", main_min=28,
            warmup_km=1.0, warmup_pace_faster="6:30", warmup_pace_slower="7:30")
        _, kwargs = self.steps[0]
        assert kwargs['distance_m'] == 1000
        assert self.steps[0][0][3] == 0             # krok kilometrowy, nie czasowy
        assert kwargs['target_value_one'] == GarminWorkout._pace_to_ms('6:30')
