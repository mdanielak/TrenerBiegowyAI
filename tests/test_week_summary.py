# -*- coding: utf-8 -*-
"""Podsumowanie tygodnia: plan a wykonanie i propozycja na kolejny tydzień."""
from datetime import date

from services.runner_profile import decision_reason
from services.week_summary import build_week_summary

PLAN = {"start_date": "2026-09-28", "workouts": [
    {"date": "2026-09-28", "type": "easy", "name": "Bieg łatwy 40 min", "duration_min": 40},
    {"date": "2026-09-29", "type": "rest", "name": "Odpoczynek"},
    {"date": "2026-09-30", "type": "tempo", "name": "Tempo 3×8 min", "duration_min": 50},
    {"date": "2026-10-02", "type": "easy", "name": "Bieg łatwy 30 min", "duration_min": 30},
    {"date": "2026-10-04", "type": "long", "name": "Długi bieg 90 min", "duration_min": 90},
]}
RUNS = [
    {"date": "2026-09-28T07:00:00", "type": "running", "duration_min": 41, "distance_km": 6.8},
    {"date": "2026-10-02T07:00:00", "type": "running", "duration_min": 20, "distance_km": 3.0},
]


def test_nothing_to_summarise_before_the_first_workout_passes():
    assert build_week_summary(PLAN, RUNS, today=date(2026, 9, 28)) is None
    assert build_week_summary(None, RUNS, today=date(2026, 10, 1)) is None


def test_counts_done_missed_and_shortened_only_for_days_already_past():
    summary = build_week_summary(PLAN, RUNS, today=date(2026, 10, 3), runner={"decision": "utrzymaj", "adherence": 0.67})
    assert (summary["due"], summary["done"], summary["shortened"]) == (3, 2, 1)
    assert summary["missed"] == ["środa — Tempo 3×8 min"]
    assert (summary["planned_min"], summary["done_min"], summary["km"], summary["runs"]) == (120, 61, 9.8, 2)
    assert summary["over"] is False
    assert summary["proposal"]["key"] == "utrzymaj" and "Nie wszystkie" in summary["proposal"]["reason"]


def test_proposal_waits_for_friday_and_disappears_after_the_week():
    runner = {"decision": "doloz", "adherence": 1.0}
    assert build_week_summary(PLAN, RUNS, today=date(2026, 10, 1), runner=runner)["proposal"] is None
    finished = build_week_summary(PLAN, RUNS, today=date(2026, 10, 7), runner=runner)
    assert finished["over"] is True and finished["proposal"] is None and finished["due"] == 4


def test_reason_follows_the_decision_rules():
    assert "ból" in decision_reason({"decision": "odpusc", "pain": True})
    assert "7 bpm" in decision_reason({"decision": "odpusc", "rhr_up": 7})
    assert "60%" in decision_reason({"decision": "odpusc", "adherence": 0.5})
    assert "przerwie" in decision_reason({"decision": "utrzymaj", "adherence": 1.0, "returning": True})
    assert "Plan wykonany" in decision_reason({"decision": "doloz", "adherence": 1.0})
