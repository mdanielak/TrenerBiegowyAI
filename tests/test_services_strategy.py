# -*- coding: utf-8 -*-
"""Testy odczytu strategii długoterminowej z Markdownu."""
from datetime import date

from services.strategy import STRATEGY_EXAMPLE_PATH, load_strategy, parse_strategy

SAMPLE = """# Plan: HM 1:49

## Periodyzacja: 2026-09-28—2027-10-17

| Faza | Daty robocze | Objętość i long run | Akcent |
|---|---|---|---|
| Stabilizacja | 28.09—20.12.2026 | zwykle 28-38 km, long 12-16 km | 3-4 tygodnie z 4-5 biegami/tydz. |
| Baza zimowa | 21.12.2026—14.02.2027 | zwykle 32-42 km, long 14-18 km | progi |
| Taper | 20.09—17.10.2027 | redukcja objętości, long maks. 16-18 km | świeżość |

## Kryteria gotowości do celu 1:49

Potrzebne są regularne long runy 18-24 km. Potwierdzeniem test 10 km około **49:30-50:30**.
"""


def test_phases_are_read_with_dates_and_ranges():
    strategy = parse_strategy(SAMPLE)

    assert [phase.name for phase in strategy.phases] == ["Stabilizacja", "Baza zimowa", "Taper"]
    first, winter, taper = strategy.phases
    assert (first.start, first.end, first.km, first.long_km) == (date(2026, 9, 28), date(2026, 12, 20), (28, 38), (12, 16))
    assert winter.start == date(2026, 12, 21)
    assert taper.km is None and taper.long_km == (16, 18)


def test_criteria_are_read_from_their_section():
    strategy = parse_strategy(SAMPLE)

    assert strategy.long_run_target == (18, 24)
    assert strategy.test_10k_seconds == (49 * 60 + 30, 50 * 60 + 30)
    assert strategy.runs_per_week == (4, 5)


def test_phase_for_a_day():
    strategy = parse_strategy(SAMPLE)

    assert strategy.phase_for(date(2026, 10, 28)).name == "Stabilizacja"
    assert strategy.phase_for(date(2027, 6, 1)) is None


def test_missing_or_unstructured_file_gives_none(tmp_path):
    assert load_strategy(tmp_path / "brak.md") is None
    other = tmp_path / "inny.md"
    other.write_text("# Notatki\n\nBez tabeli.\n", encoding="utf-8")
    assert load_strategy(other) is None


def test_the_public_example_strategy_parses():
    strategy = load_strategy(STRATEGY_EXAMPLE_PATH)

    assert strategy is not None and len(strategy.phases) >= 5
    assert strategy.long_run_target and strategy.test_10k_seconds
