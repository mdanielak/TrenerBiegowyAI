# -*- coding: utf-8 -*-
"""
Central configuration for Trener Biegowy AI.

All paths are pathlib.Path objects. Secrets come from environment variables.
Import as: from config import DATA_LATEST, AI_BASE_URL, etc.
"""
import os
from pathlib import Path

# --- Paths ---
PROJECT_ROOT = Path(__file__).parent
DATA_LATEST = PROJECT_ROOT / "data_latest.json"
TRAINING_PLANS_DIR = PROJECT_ROOT / "training-plans"
IMPORTANT_PROMPT = PROJECT_ROOT / "IMPORTANT_PROMPT.txt"
RUNNER_PROFILE_LOCAL = PROJECT_ROOT / "runner_profile.local.json"
RUNNER_PROFILE_EXAMPLE = PROJECT_ROOT / "runner_profile.example.json"

# --- GarminDB paths ---
HEALTH_DATA_DIR = Path.home() / "HealthData"
ACT_DB = HEALTH_DATA_DIR / "DBs" / "garmin_activities.db"
MAIN_DB = HEALTH_DATA_DIR / "DBs" / "garmin.db"

# --- GarminDB CLI ---
GARMINDB_SYNC_TIMEOUT = 600   # seconds (incremental)
GARMINDB_FRESH_TIMEOUT = 900  # seconds (full)

# --- Garmin credentials (env vars) ---
GARMIN_EMAIL = os.environ.get("GARMIN_EMAIL", "")
GARMIN_PASSWORD = os.environ.get("GARMIN_PASSWORD", "")

# --- AI Provider settings (env vars) ---
AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://api.openai.com/v1")
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL", "gpt-4o")
AI_DATA_EXPORT_ENABLED = os.environ.get("AI_DATA_EXPORT_ENABLED", "").strip().lower() in {
    "1", "true", "yes", "on",
}
