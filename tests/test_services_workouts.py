# -*- coding: utf-8 -*-
"""Tests for services/workouts.py and trainer.workouts — workout builder."""
import sys
import os
import types
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock garminconnect before importing trainer.workouts
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

from trainer import garmin_auth
from trainer.workouts import GarminWorkout, WorkoutSchedulingError
from services import workout_registry as registry


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

    @patch('trainer.workouts.GARMIN_EMAIL', 'env@test.com')
    @patch('trainer.workouts.GARMIN_PASSWORD', 'envpass')
    def test_init_from_env(self):
        gw = GarminWorkout()
        assert gw.email == "env@test.com"
        assert gw.password == "envpass"

    # Czyszczenie os.environ nic tu nie daje: GARMIN_EMAIL i GARMIN_PASSWORD są
    # stałymi modułu związanymi przy imporcie, więc podmieniamy je wprost.
    @patch('trainer.workouts.GARMIN_EMAIL', '')
    @patch('trainer.workouts.GARMIN_PASSWORD', '')
    def test_init_no_credentials(self):
        gw = GarminWorkout()
        assert gw.email == ""
        assert gw.password == ""


class TestLogin:
    """Logowanie idzie przez trainer.garmin_auth.ensure_token.

    Magazyn tokenów jest przekierowany na katalog tymczasowy przez autouse
    fixture w tests/conftest.py, więc testy nigdy nie czytają prawdziwego
    ~/.GarminDb z katalogu domowego.
    """

    @pytest.fixture
    def client(self, monkeypatch):
        """Podmień klienta tam, gdzie go naprawdę używamy.

        Atrapa z sys.modules nie wystarcza: trainer.garmin_auth wiąże nazwę
        Garmin przy imporcie, więc przy innej kolejności zbierania testów
        trzymałby prawdziwą klasę.
        """
        factory = MagicMock(return_value=MagicMock())
        monkeypatch.setattr(garmin_auth, "Garmin", factory)
        return factory

    def test_login_without_credentials_uses_saved_token(self, client):
        """Zapisany token wystarcza, hasło nie jest potrzebne."""
        path = garmin_auth.token_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"di_token": "x"}', encoding="utf-8")

        gw = GarminWorkout(email=None, password=None)
        result = gw.login()

        client.assert_called_once_with()
        client.return_value.login.assert_called_once_with(str(path))
        assert gw.api is client.return_value
        assert result is gw

    def test_login_success_saves_token_for_next_run(self, client):
        """Logowanie hasłem MUSI przekazać ścieżkę tokenstore, inaczej token nie powstanie."""
        gw = GarminWorkout(email="test@test.com", password="pass")
        result = gw.login()

        client.assert_called_with("test@test.com", "pass")
        client.return_value.login.assert_called_once_with(str(garmin_auth.token_path()))
        assert result is gw

    def test_login_without_token_and_without_password_raises(self):
        """Brak tokena i brak hasła to jasny błąd, nie cicha degradacja."""
        monkeypatched = patch.multiple(garmin_auth, GARMIN_EMAIL="", GARMIN_PASSWORD="")
        with monkeypatched:
            gw = GarminWorkout(email=None, password=None)
            with pytest.raises(garmin_auth.GarminAuthError, match="GARMIN_PASSWORD"):
                gw.login()


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


class TestUploadSchedulingConsistency:
    @pytest.fixture
    def mock_gw(self):
        gw = GarminWorkout(email='test@test.com', password='pass')
        gw.api = MagicMock()
        gw.api.upload_running_workout.return_value = {'workoutId': 12345}
        gw.api.schedule_workout.return_value = {'id': 67890}
        gw.api.delete_workout.side_effect = AssertionError('no compensation')
        gw.api.unschedule_workout.side_effect = AssertionError('no compensation')
        return gw

    def test_added_entry_exists_before_scheduling(self, mock_gw):
        def check_registry(*args):
            workout = registry.find_workout(12345)
            assert workout['date'] is None
            assert workout['schedule_status'] == 'pending'
            return {'id': 67890}

        mock_gw.api.schedule_workout.side_effect = check_registry
        assert mock_gw.easy_run('Test', 30, '2026-09-20') == 12345

    def test_upload_without_id_does_not_schedule_or_register(self, mock_gw, capsys):
        mock_gw.api.upload_running_workout.return_value = {}
        with pytest.raises(KeyError):
            mock_gw.easy_run('Test', 30, '2026-09-20')
        mock_gw.api.schedule_workout.assert_not_called()
        assert registry.load_events() == []
        assert 'wynik uploadu może być nieznany' in capsys.readouterr().out

    def test_upload_failure_does_not_schedule_or_register(self, mock_gw):
        mock_gw.api.upload_running_workout.side_effect = RuntimeError('upload failed')
        with pytest.raises(RuntimeError, match='upload failed'):
            mock_gw.easy_run('Test', 30, '2026-09-20')
        mock_gw.api.schedule_workout.assert_not_called()
        assert registry.load_events() == []

    def test_scheduling_error_records_unknown_status_and_cause(self, mock_gw):
        failure = TimeoutError('timeout')
        mock_gw.api.schedule_workout.side_effect = failure
        with pytest.raises(WorkoutSchedulingError) as caught:
            mock_gw.easy_run('Test', 30, '2026-09-20')
        error = caught.value
        workout = registry.find_workout(12345)
        assert workout['date'] is None
        assert workout['schedule_status'] == 'unknown'
        assert error.workout_id == 12345
        assert error.intended_date == '2026-09-20'
        assert error.registry_persisted is True
        assert error.__cause__ is failure

    def test_lookup_failure_does_not_undo_confirmed_schedule(self, mock_gw, monkeypatch):
        mock_gw.api.schedule_workout.return_value = MagicMock()
        monkeypatch.setattr(mock_gw, '_lookup_schedule_id',
                            lambda *args: (_ for _ in ()).throw(RuntimeError('calendar')))
        assert mock_gw.easy_run('Test', 30, '2026-09-20') == 12345
        workout = registry.find_workout(12345)
        assert workout['schedule_status'] == 'confirmed'
        assert workout['date'] == '2026-09-20'

    def test_failed_initial_registry_write_is_recovered_by_full_added(self, mock_gw, monkeypatch):
        real_added = registry.record_added
        calls = 0

        def fail_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return registry.RegistryWriteResult(kwargs, False, 'io_error')
            return real_added(*args, **kwargs)

        monkeypatch.setattr('trainer.workouts.record_added', fail_once)
        assert mock_gw.easy_run('Test', 30, '2026-09-20') == 12345
        workout = registry.find_workout(12345)
        assert workout['status'] == 'active'
        assert workout['date'] == '2026-09-20'
        assert workout['schedule_status'] == 'confirmed'

    def test_failed_final_registry_write_still_returns_id(self, mock_gw, monkeypatch):
        monkeypatch.setattr(
            'trainer.workouts.record_updated',
            lambda *args, **kwargs: registry.RegistryWriteResult({}, False, 'io_error'),
        )
        assert mock_gw.easy_run('Test', 30, '2026-09-20') == 12345

    def test_restore_scheduling_failure_keeps_definition_and_source(self, mock_gw):
        definition = {'workoutName': 'Odtworzony', 'estimatedDurationInSecs': 1800}
        mock_gw.api.schedule_workout.side_effect = TimeoutError('timeout')
        with pytest.raises(WorkoutSchedulingError):
            mock_gw._upload_definition(definition, '2026-09-20')
        workout = registry.find_workout(12345)
        assert workout['definition'] == definition
        assert workout['source'] == 'restore'
        assert workout['schedule_status'] == 'unknown'

    def test_success_keeps_id_and_existing_output(self, mock_gw, capsys):
        assert mock_gw.easy_run('Test', 30, '2026-09-20') == 12345
        assert '2026-09-20 Test: ID=12345' in capsys.readouterr().out


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
