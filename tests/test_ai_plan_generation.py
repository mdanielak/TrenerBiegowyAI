# -*- coding: utf-8 -*-
"""Testy dla ai/plan_generation.py — prompt i wywołanie providera."""
import pytest

from ai.plan_generation import (
    PlanWorkout,
    WeekPlanResponse,
    build_plan_message,
    build_system_prompt,
    generate_week_plan,
)
from services.strategy import STRATEGY_EXAMPLE_PATH


WEEK = [
    ("mon", "2026-10-26"),
    ("tue", "2026-10-27"),
    ("wed", "2026-10-28"),
    ("thu", "2026-10-29"),
    ("fri", "2026-10-30"),
    ("sat", "2026-10-31"),
    ("sun", "2026-11-01"),
]


def _context():
    week_days = [{
        "date": date,
        "day": day,
        "weekday": "poniedziałek",
        "available": True,
        "min_minutes": 35,
        "max_minutes": 45,
        "pause_reason": None,
        "readiness_score": 7.5,
        "readiness_level": "ready",
    } for day, date in WEEK]
    return {
        "week_start": "2026-10-26",
        "week_end": "2026-11-01",
        "week_days": week_days,
        "max_quality_sessions": 1,
        "hr_zone_floors": {"z1": 96, "z2": 122, "z3": 137, "z4": 155, "z5": 173},
        "profile": {
            "age": 36, "weight_kg": 75, "height_cm": 188, "hr_max": 192,
            "hr_rest": 50, "lactate_threshold_hr": 174, "hr_zones": "Z1 96-121, Z2 122-136",
        },
        "goal": {"target": "półmaraton 1:49:00", "deadline": "2027-10-17", "current_record": "1:58:30"},
        "recent_activities": [{
            "date": "2026-10-20", "name": "Bieg poranny", "distance_km": 8.0,
            "duration_min": 44, "pace": "5:30", "avg_hr": 140, "max_hr": 155,
        }],
        "weekly_load": {"total_km": 24.0, "total_min": 130, "sessions": 3},
        "previous_weekly_load": {"total_km": 30.0, "total_min": 160, "sessions": 4},
        "readiness_history": [{"date": "2026-10-25", "score": 7.0, "level": "ready"}],
        "health_metrics": {
            "rhr": 48, "hrv_last_night": 55, "hrv_status": "BALANCED", "hrv_baseline": "50-60",
            "sleep_score": 85, "sleep_total_h": 7.5, "sleep_deep_h": None, "stress_avg": 22,
        },
        "hrv_alert": None,
        "snapshot_status": "fresh",
        "snapshot_timestamp": "2026-10-26T06:00:00+00:00",
    }


class _Provider:
    def __init__(self):
        self.args = None
        self.kwargs = None

    def chat(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        return WeekPlanResponse(
            start_date="2026-10-26", end_date="2026-11-01", focus="Baza", summary="Baza tygodnia",
            workouts=[PlanWorkout(date="2026-10-26", kind="easy", name="Bieg łatwy", duration_min=40)],
        )


def test_generate_week_plan_uses_deterministic_parameters():
    provider = _Provider()
    result = generate_week_plan(provider, _context())

    assert isinstance(result, WeekPlanResponse)
    assert provider.kwargs["response_model"] is WeekPlanResponse
    assert provider.kwargs["temperature"] == 0.0
    assert provider.kwargs["seed"] == 7
    assert provider.args[0] == build_system_prompt()
    assert provider.args[1] == build_plan_message(_context())


def test_message_contains_every_section_and_all_seven_dates():
    message = build_plan_message(_context())

    for section in ("PROFIL", "CEL", "DOSTĘPNOŚĆ W TYGODNIU", "LIMITY TYGODNIA",
                    "OSTATNIE BIEGI", "OBCIĄŻENIE", "GOTOWOŚĆ", "STAN ZDROWIA", "ZAKRES DAT"):
        assert section in message
    for _day, date in WEEK:
        assert date in message
    assert "maksymalna liczba treningów jakościowych w tygodniu: 1" in message


def test_missing_values_are_written_as_brak():
    message = build_plan_message(_context())

    assert "brak" in message
    assert "None" not in message


def test_system_prompt_reports_missing_strategy_and_keeps_rules(tmp_path):
    prompt = build_system_prompt(strategy_path=tmp_path / "brak.md")

    assert "Strategia długoterminowa nie jest dostępna" in prompt
    assert "ZASADY UKŁADANIA TYGODNIA" in prompt


def test_system_prompt_contains_tracked_rules_and_strategy():
    # Przykład, a nie własna strategia: tamta jest nieśledzona i na czystej kopii jej nie ma.
    prompt = build_system_prompt(strategy_path=STRATEGY_EXAMPLE_PATH)

    assert "ZASADY UKŁADANIA TYGODNIA" in prompt
    assert "półmaraton" in prompt.lower()


def test_system_prompt_states_the_exact_response_schema():
    prompt = build_system_prompt()

    for key in ("start_date", "end_date", "focus", "summary", "workouts",
                "date", "kind", "name", "description", "duration_min",
                "distance_km", "hr_zone", "pace_target", "repetitions",
                "work_seconds", "rest_seconds", "notes"):
        assert f'"{key}"' in prompt
    assert "Nie używaj `days`" in prompt


def test_provider_exception_is_not_suppressed():
    class Failing:
        def chat(self, *args, **kwargs):
            raise RuntimeError("provider failed")

    with pytest.raises(RuntimeError, match="provider failed"):
        generate_week_plan(Failing(), _context())


def test_message_reports_trends_and_journal_pain_first():
    context = _context()
    context["trends"] = {
        "metrics": {"hrv": {"recent": 60.9, "average": 68.1, "direction": "down"},
                    "rhr": {"recent": 52.6, "average": 49.6, "direction": "up"}},
        "weekly_km": [33.4, 28.4, 35.1, 8.0],
    }
    context["journal"] = {
        "days_with_entries": 3, "feelings": {"świetnie": 0, "dobrze": 2, "słabo": 1}, "average_rpe": 4.5,
        "pain_days": [{"date": "2026-10-28", "areas": ["kolano"], "note": "po biegu"}], "notes": [],
    }
    message = build_plan_message(context)

    assert "TRENDY (średnia z 7 dni wobec 12 tygodni)" in message
    assert "- HRV ostatniej nocy: 60,9 ms wobec 68,1 ms (niżej)" in message
    assert "- gotowość: brak pomiarów" in message
    assert "33,4; 28,4; 35,1; 8" in message
    assert "- BÓL 2026-10-28: kolano (po biegu)" in message
    assert "średnie RPE: 4,5" in message


def test_message_without_trends_or_journal_says_so():
    message = build_plan_message(_context())

    assert "DZIENNIK (ostatnie 7 dni)\n- brak wpisów" in message


def test_system_prompt_puts_journal_pain_before_metrics():
    assert "Ból zgłoszony w sekcji DZIENNIK ma pierwszeństwo przed metrykami" in build_system_prompt()
