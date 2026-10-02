import json
import sqlite3

from trainer.errors import describe_error, env_hint


def test_missing_dependency_has_stable_advice():
    advice = describe_error(ModuleNotFoundError("brak"))
    assert advice.exit_code == 3
    assert "pip install -r requirements.txt" in advice.hint


def test_profile_and_database_errors_are_classified():
    assert describe_error(FileNotFoundError("local/profile.json")).exit_code == 5
    assert describe_error(sqlite3.OperationalError("locked")).exit_code == 7


def test_json_error_and_secret_are_safe():
    error = json.JSONDecodeError("bad", "profile.json", 0)
    assert describe_error(error).exit_code == 5
    generic = describe_error(RuntimeError("password=very-secret"))
    assert "very-secret" not in generic.hint


def test_garmin_auth_error_is_not_reported_as_unexpected():
    from trainer.garmin_auth import GarminAuthError

    advice = describe_error(GarminAuthError("Brakuje hasła Garmin (GARMIN_PASSWORD)."))
    assert advice.exit_code == 8
    assert "nieoczekiwany" not in advice.message.lower()
    assert "Garmin Connect" in advice.message
    assert "GARMIN_PASSWORD" in advice.hint


def test_env_hint_matches_current_platform():
    hint = env_hint("MY_VALUE", "abc")
    assert ("$env:MY_VALUE" if __import__("sys").platform == "win32" else "export MY_VALUE") in hint
