"""Testy komendy ``trainer profile``: czytelny wydruk i mapowanie pól Garmina."""
from types import SimpleNamespace

from trainer.commands import profile as profile_cmd

_FULL = {
    "name": "Maciej",
    "age": 36,
    "weight_kg": 75,
    "height_cm": 188,
    "hr_max": 192,
    "hr_rest": 50,
    "lactate_threshold_hr": 174,
    "hr_zones": "Z1 96-121, Z2 122-136, Z3 137-154, Z4 155-172, Z5 173-192",
    "hr_zones_source": "Garmin Connect",
    "device": "Garmin Fenix 7S Pro Solar",
}


class _Workout:
    def login(self):
        return SimpleNamespace(api=object())


def test_render_is_human_readable_not_a_dict_dump(monkeypatch, capsys):
    monkeypatch.setattr(profile_cmd.profile_store, "load_profile", lambda: dict(_FULL))
    assert profile_cmd.main() == 0
    out = capsys.readouterr().out
    assert "=== Profil biegacza ===" in out
    assert "Tętno maksymalne:" in out and "192 bpm" in out
    assert "{'" not in out and "weight_kg" not in out


def test_render_flags_range_values_and_suggests_sync(monkeypatch, capsys):
    monkeypatch.setattr(profile_cmd.profile_store, "load_profile",
                        lambda: dict(_FULL, weight_kg="75-76", hr_rest="48-52"))
    assert profile_cmd.main() == 0
    out = capsys.readouterr().out
    assert "nie są liczbami" in out
    assert "Waga" in out and "Tętno spoczynkowe" in out
    assert "profile --sync" in out


def test_render_shows_structured_goal_and_hides_composed_field(monkeypatch, capsys):
    monkeypatch.setattr(profile_cmd.profile_store, "load_profile",
                        lambda: dict(_FULL, target_race="półmaraton", target_time="1:49",
                                     target_hm="półmaraton 1:49"))
    assert profile_cmd.main() == 0
    out = capsys.readouterr().out
    assert "Docelowy bieg:" in out and "półmaraton" in out
    assert "Zakładany czas:" in out and "1:49" in out
    # Złożone "target_hm" nie powinno dublować pól składowych ani trafiać do worka.
    assert "Cel:" not in out
    assert "Pozostałe pola" not in out


def test_render_keeps_legacy_goal_field_when_structured_missing(monkeypatch, capsys):
    monkeypatch.setattr(profile_cmd.profile_store, "load_profile",
                        lambda: dict(_FULL, target_hm="1:49 (5:10/km)"))
    assert profile_cmd.main() == 0
    out = capsys.readouterr().out
    assert "Cel:" in out and "1:49 (5:10/km)" in out


def test_render_lists_unknown_fields(monkeypatch, capsys):
    monkeypatch.setattr(profile_cmd.profile_store, "load_profile",
                        lambda: {"name": "Maciej", "ulubiony_szlak": "Las"})
    assert profile_cmd.main() == 0
    assert "ulubiony_szlak" in capsys.readouterr().out


def test_sync_maps_garmin_keys_and_skips_preference_fields(monkeypatch, capsys):
    saved: dict = {}
    zones: dict = {}
    snapshot = {
        "age": 36, "weight": 75, "height": 188, "hr_rest": 50,
        "lactate_threshold_hr": 174, "vo2max_running": 50.0,
        "hr_max": 192, "hr_zone_floors": {"z1": 96, "z2": 122, "z3": 137, "z4": 155, "z5": 173},
        "available_training_days": ["tue", "thu", "fri"], "long_training_days": ["sun"],
    }
    monkeypatch.setattr(profile_cmd.profile_store, "load_profile", lambda: dict(_FULL))
    monkeypatch.setattr(profile_cmd.profile_store, "update_profile", lambda **kw: saved.update(kw))
    monkeypatch.setattr(profile_cmd.profile_store, "set_hr_zones",
                        lambda floors, hr_max, source: zones.update(floors=floors, hr_max=hr_max))
    monkeypatch.setattr(profile_cmd, "fetch_snapshot", lambda api: dict(snapshot))
    import trainer.workouts
    monkeypatch.setattr(trainer.workouts, "GarminWorkout", _Workout)

    assert profile_cmd.main(sync=True) == 0
    # Waga i wzrost muszą trafić pod nazwy używane przez profil.
    assert saved["weight_kg"] == 75 and saved["height_cm"] == 188
    assert "weight" not in saved and "height" not in saved
    # Dni treningowe należą do preferencji, nie do profilu.
    assert "available_training_days" not in saved and "long_training_days" not in saved
    assert zones["hr_max"] == 192 and zones["floors"]["z5"] == 173
    assert "zaktualizowany" in capsys.readouterr().out


def test_sync_reports_error_when_garmin_fails(monkeypatch, capsys):
    class Failing:
        def login(self):
            raise RuntimeError("429")
    monkeypatch.setattr(profile_cmd.profile_store, "load_profile", lambda: dict(_FULL))
    import trainer.workouts
    monkeypatch.setattr(trainer.workouts, "GarminWorkout", Failing)
    assert profile_cmd.main(sync=True) == 1
    assert "nie udało się pobrać" in capsys.readouterr().out


def test_sync_reports_error_on_empty_snapshot(monkeypatch, capsys):
    monkeypatch.setattr(profile_cmd.profile_store, "load_profile", lambda: dict(_FULL))
    monkeypatch.setattr(profile_cmd, "fetch_snapshot", lambda api: {})
    import trainer.workouts
    monkeypatch.setattr(trainer.workouts, "GarminWorkout", _Workout)
    assert profile_cmd.main(sync=True) == 1
    assert "nie zwrócił" in capsys.readouterr().out


def test_missing_profile_points_to_setup(monkeypatch, capsys):
    def boom():
        raise FileNotFoundError
    monkeypatch.setattr(profile_cmd.profile_store, "load_profile", boom)
    assert profile_cmd.main() == 5
    assert "trainer setup" in capsys.readouterr().out
