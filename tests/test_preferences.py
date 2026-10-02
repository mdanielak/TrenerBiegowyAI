import json
from types import SimpleNamespace

from trainer import preferences


def test_missing_preferences_return_safe_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "SETTINGS", SimpleNamespace(local_dir=tmp_path))
    data = preferences.load_preferences()
    assert data["version"] == 1
    assert set(data["days"]) == {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def test_legacy_days_and_unknown_fields_are_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "SETTINGS", SimpleNamespace(local_dir=tmp_path))
    (tmp_path / "training_preferences.json").write_text(json.dumps({"days": {"mon": True}, "private": "keep"}), encoding="utf-8")
    data = preferences.load_preferences()
    assert data["days"]["mon"]["available"] is True
    preferences.save_preferences(data)
    assert json.loads((tmp_path / "training_preferences.json").read_text(encoding="utf-8"))["private"] == "keep"


def test_set_weekly_availability_writes_one_day(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "SETTINGS", SimpleNamespace(local_dir=tmp_path))
    assert preferences.set_weekly_availability("wed", True, 30, 60)["max_minutes"] == 60
    assert preferences.get_weekly_availability("wed")["available"] is True
