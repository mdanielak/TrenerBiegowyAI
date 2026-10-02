# -*- coding: utf-8 -*-
import pytest

from ai.workout_review import WorkoutComment, build_comment_message, get_workout_comment


def data():
    return {
        "planned": {"name": "Bieg", "spec": {"duration_min": 40, "zone_number": 2}},
        "execution": {"happened": True, "match_method": "id", "duration_min": 40, "distance_km": 6.5, "avg_hr": 130, "max_hr": 150},
        "score": {"zgodnosc_z_planem": 10, "dopasowanie_do_formy": 10, "pewnosc": "wysoka", "odchylenie_czasu_proc": 0, "odchylenie_tetna_bpm": 0, "strefa_wykonania": 2, "strefa_docelowa": 2, "zakres_docelowy": (122, 136)},
        "readiness": {"score": 6, "rhr": 50, "hrv_last": 55, "hrv_baseline": "50-60", "hrv_status": "normalna", "sleep_score_val": 80, "sleep_total": 7.5, "stress": 25},
        "hr_zones_text": "Z1: 96-121 bpm",
    }


def test_message_is_deterministic():
    values = data()
    assert build_comment_message(**values) == build_comment_message(**values)


def test_missing_values_render_as_brak_without_none():
    values = data()
    values.update(planned={}, execution={}, score={}, readiness={}, hr_zones_text=None)
    message = build_comment_message(**values)
    assert "brak" in message
    assert "None" not in message


def test_none_none_hrv_baseline_renders_as_brak():
    values = data()
    values["readiness"]["hrv_baseline"] = "None-None"
    assert "zakres bazowy brak" in build_comment_message(**values)


def test_get_comment_passes_deterministic_parameters():
    class Provider:
        def __init__(self): self.kwargs = None
        def chat(self, *args, **kwargs):
            self.kwargs = kwargs
            return WorkoutComment(komentarz="Pierwsze zdanie. Drugie zdanie.")
    provider = Provider()
    result = get_workout_comment(provider, **data())
    assert isinstance(result, WorkoutComment)
    assert provider.kwargs["temperature"] == 0.0
    assert provider.kwargs["seed"] == 7
    assert provider.kwargs["response_model"] is WorkoutComment


def test_provider_exception_is_not_suppressed():
    class Provider:
        def chat(self, *args, **kwargs): raise RuntimeError("provider failed")
    with pytest.raises(RuntimeError, match="provider failed"):
        get_workout_comment(Provider(), **data())
