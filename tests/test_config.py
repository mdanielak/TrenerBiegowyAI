# -*- coding: utf-8 -*-
"""Tests for config.py centralized configuration."""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    SETTINGS, PROJECT_ROOT, DATA_LATEST, TRAINING_PLANS_DIR, IMPORTANT_PROMPT,
    HEALTH_DATA_DIR, ACT_DB, MAIN_DB,
    GARMINDB_SYNC_TIMEOUT, GARMINDB_FRESH_TIMEOUT,
)


class TestPaths:
    def test_project_root_is_path(self):
        from pathlib import Path
        assert isinstance(PROJECT_ROOT, Path)

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

    def test_important_prompt(self):
        from pathlib import Path
        assert isinstance(IMPORTANT_PROMPT, Path)
        assert IMPORTANT_PROMPT.name == "IMPORTANT_PROMPT.txt"

    def test_health_data_dir(self):
        from pathlib import Path
        assert isinstance(HEALTH_DATA_DIR, Path)

    def test_act_db_path(self):
        assert str(ACT_DB).endswith("garmin_activities.db")

    def test_main_db_path(self):
        assert str(MAIN_DB).endswith("garmin.db")


class TestTimeouts:
    def test_sync_timeout_positive(self):
        assert GARMINDB_SYNC_TIMEOUT > 0

    def test_fresh_timeout_positive(self):
        assert GARMINDB_FRESH_TIMEOUT > 0

    def test_fresh_timeout_greater_than_sync(self):
        assert GARMINDB_FRESH_TIMEOUT >= GARMINDB_SYNC_TIMEOUT


class TestEnvVars:
    def test_garmin_email_is_string(self):
        from config import GARMIN_EMAIL
        assert isinstance(GARMIN_EMAIL, str)

    def test_garmin_password_is_string(self):
        from config import GARMIN_PASSWORD
        assert isinstance(GARMIN_PASSWORD, str)

    def test_ai_base_url_is_string(self):
        from config import AI_BASE_URL
        assert isinstance(AI_BASE_URL, str)

    def test_ai_model_is_string(self):
        from config import AI_MODEL
        assert isinstance(AI_MODEL, str)

    def test_ai_data_export_is_disabled_by_default(self):
        from config import AI_DATA_EXPORT_ENABLED
        assert AI_DATA_EXPORT_ENABLED is False

    def test_settings_are_immutable_and_hide_secrets_in_repr(self):
        from dataclasses import FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            setattr(SETTINGS, "ai_api_key", "changed")
        assert "ai_api_key" not in repr(SETTINGS)
        assert "garmin_password" not in repr(SETTINGS)
