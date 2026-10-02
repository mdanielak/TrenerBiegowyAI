from types import SimpleNamespace

from trainer.commands import zones


def test_local_zones_warn_when_source_missing(monkeypatch, capsys):
    monkeypatch.setattr(zones.profile_store, "load_profile", lambda: {"hr_zones": "Z1 90-110"})
    assert zones.main() == 0
    assert "Ostrzeżenie" in capsys.readouterr().out


def test_sync_uses_mocked_garmin_and_saves_zones(monkeypatch, capsys):
    before = {"hr_zones": "old", "hr_zones_source": "old source"}
    saved = {}
    class Workout:
        api = SimpleNamespace(get_heart_rate_zones=lambda: [{"sport": "DEFAULT", "zone1Floor": 96, "zone2Floor": 122, "zone3Floor": 137, "zone4Floor": 155, "zone5Floor": 173, "maxHeartRateUsed": 192}])
        def login(self):
            return self
    monkeypatch.setattr(zones.profile_store, "load_profile", lambda: before)
    monkeypatch.setattr(zones.profile_store, "set_hr_zones", lambda floors, hr_max, source: saved.update(floors=floors, hr_max=hr_max, source=source) or {"hr_zones": "new", "hr_zones_source": source})
    import trainer.workouts
    monkeypatch.setattr(trainer.workouts, "GarminWorkout", Workout)
    assert zones.main(sync=True) == 0
    assert saved["floors"]["z5"] == 173
    assert "Strefy po" in capsys.readouterr().out


def test_sync_empty_response_is_error(monkeypatch, capsys):
    class Workout:
        api = SimpleNamespace(get_heart_rate_zones=lambda: None)
        def login(self): return self
    monkeypatch.setattr(zones.profile_store, "load_profile", lambda: {})
    import trainer.workouts
    monkeypatch.setattr(trainer.workouts, "GarminWorkout", Workout)
    assert zones.main(sync=True) == 1
    assert "nie zwrócił" in capsys.readouterr().out
