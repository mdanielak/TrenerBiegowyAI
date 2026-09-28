# -*- coding: utf-8 -*-
"""Central configuration for Trener Biegowy AI."""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _positive_int_env(name, default):
    """Read a positive integer environment setting, falling back safely."""
    try:
        value = int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class AppSettings:
    """Immutable runtime configuration; secrets are deliberately hidden in repr."""

    project_root: Path
    local_dir: Path
    data_latest: Path
    runner_profile_local: Path
    memory_dir: Path
    workout_registry: Path
    training_plans_dir: Path
    important_prompt: Path
    runner_profile_example: Path
    health_data_dir: Path
    snapshot_ttl_seconds: int
    garmindb_sync_timeout: int
    garmindb_fresh_timeout: int
    garmin_email: str = field(repr=False)
    garmin_password: str = field(repr=False)
    ai_base_url: str
    ai_api_key: str = field(repr=False)
    ai_model: str
    ai_data_export_enabled: bool


ROOT = Path(__file__).parent
LOCAL_DIR = ROOT / "local"
SETTINGS = AppSettings(
    project_root=ROOT,
    local_dir=LOCAL_DIR,
    data_latest=LOCAL_DIR / "data_latest.json",
    runner_profile_local=LOCAL_DIR / "profile.json",
    memory_dir=LOCAL_DIR / "memory",
    workout_registry=LOCAL_DIR / "workout-registry.jsonl",
    training_plans_dir=ROOT / "training-plans",
    important_prompt=ROOT / "IMPORTANT_PROMPT.txt",
    runner_profile_example=ROOT / "runner_profile.example.json",
    health_data_dir=Path(os.environ.get("HEALTH_DATA_DIR") or Path.home() / "HealthData").expanduser(),
    snapshot_ttl_seconds=_positive_int_env("SNAPSHOT_TTL_SECONDS", 24 * 60 * 60),
    garmindb_sync_timeout=600,
    garmindb_fresh_timeout=900,
    garmin_email=os.environ.get("GARMIN_EMAIL", ""),
    garmin_password=os.environ.get("GARMIN_PASSWORD", ""),
    ai_base_url=os.environ.get("AI_BASE_URL", "https://api.openai.com/v1"),
    ai_api_key=os.environ.get("AI_API_KEY", ""),
    ai_model=os.environ.get("AI_MODEL", "gpt-4o"),
    ai_data_export_enabled=os.environ.get("AI_DATA_EXPORT_ENABLED", "").strip().lower()
    in {"1", "true", "yes", "on"},
)

# Backward-compatible exports for existing callers.
PROJECT_ROOT = SETTINGS.project_root
DATA_LATEST = SETTINGS.data_latest
TRAINING_PLANS_DIR = SETTINGS.training_plans_dir
IMPORTANT_PROMPT = SETTINGS.important_prompt
RUNNER_PROFILE_LOCAL = SETTINGS.runner_profile_local
RUNNER_PROFILE_EXAMPLE = SETTINGS.runner_profile_example
HEALTH_DATA_DIR = SETTINGS.health_data_dir
ACT_DB = HEALTH_DATA_DIR / "DBs" / "garmin_activities.db"
MAIN_DB = HEALTH_DATA_DIR / "DBs" / "garmin.db"
SNAPSHOT_TTL_SECONDS = SETTINGS.snapshot_ttl_seconds
GARMINDB_SYNC_TIMEOUT = SETTINGS.garmindb_sync_timeout
GARMINDB_FRESH_TIMEOUT = SETTINGS.garmindb_fresh_timeout
GARMIN_EMAIL = SETTINGS.garmin_email
GARMIN_PASSWORD = SETTINGS.garmin_password
AI_BASE_URL = SETTINGS.ai_base_url
AI_API_KEY = SETTINGS.ai_api_key
AI_MODEL = SETTINGS.ai_model
AI_DATA_EXPORT_ENABLED = SETTINGS.ai_data_export_enabled
