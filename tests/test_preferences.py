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


def test_planned_pauses_add_get_and_remove(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "SETTINGS", SimpleNamespace(local_dir=tmp_path))
    assert preferences.get_active_pause("2026-10-30") is None
    preferences.add_planned_pause("2026-10-30", "2026-11-01", "Zabieg", "medical")

    active = preferences.get_active_pause("2026-10-31")
    assert active is not None
    assert active["reason"] == "Zabieg"
    assert preferences.get_active_pause("2026-11-02") is None

    pauses = preferences.list_planned_pauses()
    assert len(pauses) == 1

    assert preferences.remove_planned_pause("2026-10-30", "2026-11-01") is True
    assert preferences.list_planned_pauses() == []
