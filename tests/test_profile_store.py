import json
from types import SimpleNamespace

import pytest

from trainer import profile_store


def test_load_profile_missing_has_polish_message(tmp_path, monkeypatch):
    monkeypatch.setattr(profile_store, "SETTINGS", SimpleNamespace(runner_profile_local=tmp_path / "profile.json"))
    with pytest.raises(FileNotFoundError, match="Nie znaleziono"):
        profile_store.load_profile()


def test_set_hr_zones_preserves_unknown_and_required_fields(tmp_path, monkeypatch):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"age": 30, "hr_zones": "old", "custom": "zachowaj"}), encoding="utf-8")
    monkeypatch.setattr(profile_store, "SETTINGS", SimpleNamespace(runner_profile_local=path))
    result = profile_store.set_hr_zones({"z1": 96, "z2": 122, "z3": 137, "z4": 155, "z5": 173}, 192, "test")
    assert result["hr_zones"] == "Z1 96-121, Z2 122-136, Z3 137-154, Z4 155-172, Z5 173-192"
    assert json.loads(path.read_text(encoding="utf-8"))["custom"] == "zachowaj"


def test_update_profile_merges_fields(tmp_path, monkeypatch):
    path = tmp_path / "profile.json"
    path.write_text('{"old": 1}\n', encoding="utf-8")
    monkeypatch.setattr(profile_store, "SETTINGS", SimpleNamespace(runner_profile_local=path))
    assert profile_store.update_profile(new=2) == {"old": 1, "new": 2}
