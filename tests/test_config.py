# -*- coding: utf-8 -*-
"""Tests for trainer.config centralized configuration."""
import sys
import os
from pathlib import Path
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trainer.config import (
    SETTINGS, PROJECT_ROOT, DATA_LATEST, TRAINING_PLANS_DIR,
    HEALTH_DATA_DIR, ACT_DB, MAIN_DB,
    GARMINDB_SYNC_TIMEOUT, GARMINDB_FRESH_TIMEOUT, resolve_database_dir,
)


class TestPaths:
    def test_project_root_is_path(self):
        from pathlib import Path
        assert isinstance(PROJECT_ROOT, Path)

    def test_key_runtime_paths_remain_in_repository_root(self):
        assert PROJECT_ROOT == Path(__file__).resolve().parents[1]
        assert SETTINGS.local_dir == PROJECT_ROOT / "local"
        assert TRAINING_PLANS_DIR == PROJECT_ROOT / "training-plans"
        assert SETTINGS.runner_profile_local == PROJECT_ROOT / "local" / "profile.json"

    def test_data_latest_is_path(self):
        from pathlib import Path
        assert isinstance(DATA_LATEST, Path)

    def test_data_latest_filename(self):
        assert DATA_LATEST.name == "data_latest.json"

    def test_private_runtime_paths_are_under_local(self):
        assert DATA_LATEST == PROJECT_ROOT / "local" / "data_latest.json"
        assert SETTINGS.runner_profile_local == PROJECT_ROOT / "local" / "profile.json"
        assert SETTINGS.workout_registry == PROJECT_ROOT / "local" / "workout-registry.jsonl"

    def test_training_plans_dir(self):
        from pathlib import Path
        assert isinstance(TRAINING_PLANS_DIR, Path)
        assert TRAINING_PLANS_DIR.name == "training-plans"

    def test_health_data_dir(self):
        from pathlib import Path
        assert isinstance(HEALTH_DATA_DIR, Path)

    def test_act_db_path(self):
        assert str(ACT_DB).endswith("garmin_activities.db")

    def test_main_db_path(self):
        assert str(MAIN_DB).endswith("garmin.db")


class TestDatabaseDirectoryResolution:
    def test_prefers_exact_case_dbs(self, tmp_path):
        health_data = tmp_path / 'HealthData'
        databases = health_data / 'DBs'
        databases.mkdir(parents=True)

        assert resolve_database_dir(health_data) == databases

    def test_falls_back_to_exact_case_lowercase_dbs(self, tmp_path):
        health_data = tmp_path / 'HealthData'
        databases = health_data / 'dbs'
        databases.mkdir(parents=True)

        assert resolve_database_dir(health_data) == databases

    def test_missing_directories_use_canonical_dbs_path(self, tmp_path):
        health_data = tmp_path / 'HealthData'

        assert resolve_database_dir(health_data) == health_data / 'DBs'


class TestTimeouts:
    def test_sync_timeout_positive(self):
        assert GARMINDB_SYNC_TIMEOUT > 0

    def test_fresh_timeout_positive(self):
        assert GARMINDB_FRESH_TIMEOUT > 0

    def test_fresh_timeout_greater_than_sync(self):
        assert GARMINDB_FRESH_TIMEOUT >= GARMINDB_SYNC_TIMEOUT


class TestEnvVars:
    def test_garmin_email_is_string(self):
        from trainer.config import GARMIN_EMAIL
        assert isinstance(GARMIN_EMAIL, str)

    def test_garmin_password_is_not_configuration(self):
        from trainer import config
        assert not hasattr(config, 'GARMIN_PASSWORD')
        assert not hasattr(config.SETTINGS, 'garmin_password')

    def test_configuration_excludes_password_when_loading_env(self, monkeypatch):
        import importlib
        from trainer import config, env_file
        calls = []
        def load(path, **kwargs):
            calls.append(kwargs)
            return {}
        with monkeypatch.context() as patched:
            patched.setenv('GARMIN_PASSWORD', 'ignored-secret')
            patched.setattr(env_file, 'load_env_file', load)
            importlib.reload(config)
            assert calls == [{'override': False, 'exclude': {'GARMIN_PASSWORD'}}]
            assert not hasattr(config.SETTINGS, 'garmin_password')
            assert 'ignored-secret' not in repr(config.SETTINGS)
        importlib.reload(config)

    def test_ai_base_url_is_string(self):
        from trainer.config import AI_BASE_URL
        assert isinstance(AI_BASE_URL, str)

    def test_ai_model_is_string(self):
        from trainer.config import AI_MODEL
        assert isinstance(AI_MODEL, str)

    def test_ai_data_export_is_disabled_by_default(self, monkeypatch):
        """Brak zmiennej musi oznaczać wyłączony eksport danych.

        Stała jest budowana przy imporcie, a trainer/config.py wczytuje wtedy
        projektowy .env. Dlatego default sprawdzamy przeładowując moduł
        z neutralnym środowiskiem, a na końcu przywracamy stan rzeczywisty.
        """
        import importlib
        import trainer.config as config_module
        import trainer.env_file as env_file_module

        with monkeypatch.context() as patched:
            patched.delenv("AI_DATA_EXPORT_ENABLED", raising=False)
            patched.setattr(env_file_module, "load_env_file", lambda *a, **k: {})
            reloaded = importlib.reload(config_module)
            assert reloaded.AI_DATA_EXPORT_ENABLED is False
        importlib.reload(config_module)

    def test_settings_are_immutable_and_hide_secrets_in_repr(self):
        from dataclasses import FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            setattr(SETTINGS, "ai_api_key", "changed")
        assert "ai_api_key" not in repr(SETTINGS)
        assert "garmin_password" not in repr(SETTINGS)
