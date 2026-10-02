from datetime import date

from trainer import garmin_profile


DEFAULT = {"sport": "DEFAULT", "maxHeartRateUsed": 192, "zone1Floor": 96, "zone2Floor": 122, "zone3Floor": 137, "zone4Floor": 155, "zone5Floor": 173}


def test_parse_hr_zones_list_and_dict():
    expected = ({"z1": 96, "z2": 122, "z3": 137, "z4": 155, "z5": 173}, 192)
    assert garmin_profile.parse_hr_zones([DEFAULT]) == expected
    assert garmin_profile.parse_hr_zones(DEFAULT) == expected


def test_parse_hr_zones_prefers_running_and_rejects_bad_data():
    running = {**DEFAULT, "sport": "RUNNING", "zone1Floor": 99}
    preferred = garmin_profile.parse_hr_zones([DEFAULT, running])
    assert preferred is not None and preferred[0]["z1"] == 99
    assert garmin_profile.parse_hr_zones([]) is None
    assert garmin_profile.parse_hr_zones([{"sport": "DEFAULT"}]) is None
    assert garmin_profile.parse_hr_zones(["nie słownik"]) is None


def test_fetch_snapshot_normalizes_values_and_survives_summary_failure(monkeypatch):
    class Api:
        def get_user_profile(self): return {"userData": {"birthDate": "1990-05-13", "weight": 75349.0, "height": 188.0, "lactateThresholdHeartRate": 174, "vo2MaxRunning": 50, "availableTrainingDays": ["TUESDAY"], "preferredLongTrainingDays": ["SUNDAY"]}}
        def get_user_summary(self, day): raise RuntimeError()
        def get_heart_rate_zones(self): return [DEFAULT]
    class FrozenDate(date):
        @classmethod
        def today(cls): return cls(2026, 10, 2)
    monkeypatch.setattr(garmin_profile, 'date', FrozenDate)
    result = garmin_profile.fetch_snapshot(Api())
    assert result['age'] == 36 and result['weight'] == 75 and result['height'] == 188
    assert 'hr_rest' not in result and result['available_training_days'] == ['tue'] and result['long_training_days'] == ['sun']


def test_fetch_snapshot_rejects_out_of_range_values(monkeypatch):
    """Garmin przy braku pomiaru zwraca zera; nie wolno ich zapisać do profilu."""
    class Api:
        def get_user_profile(self):
            return {"userData": {"weight": 0, "height": 0, "lactateThresholdHeartRate": 0, "vo2MaxRunning": 0}}
        def get_user_summary(self, day): return {"lastSevenDaysAvgRestingHeartRate": 0, "restingHeartRate": 0}
        def get_heart_rate_zones(self): return [DEFAULT]
    result = garmin_profile.fetch_snapshot(Api())
    for key in ("weight", "height", "lactate_threshold_hr", "vo2max_running", "hr_rest"):
        assert key not in result, key
    # Strefy nadal muszą się pobrać, bo pochodzą z innego endpointu.
    assert result["hr_max"] == 192


def test_fetch_snapshot_falls_back_to_resting_when_average_missing():
    class Api:
        def get_user_profile(self): return {}
        def get_user_summary(self, day): return {"restingHeartRate": 51}
        def get_heart_rate_zones(self): return []
    assert garmin_profile.fetch_snapshot(Api())["hr_rest"] == 51


def test_age_before_birthday(monkeypatch):
    class Api:
        def get_user_profile(self): return {"userData": {"birthDate": "1990-12-03"}}
        def get_user_summary(self, day): return {}
        def get_heart_rate_zones(self): return []
    class FrozenDate(date):
        @classmethod
        def today(cls): return cls(2026, 10, 2)
    monkeypatch.setattr(garmin_profile, 'date', FrozenDate)
    assert garmin_profile.fetch_snapshot(Api())['age'] == 35
