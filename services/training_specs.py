# -*- coding: utf-8 -*-
"""Jedno źródło prawdy dla kategorii dystansów i parametrów treningowych.

Dzieli dystanse na dwie kategorie wysiłku:
- ``short`` (5 km, 10 km): krótszy taper, szybki powrót po starcie, sprawdzian 5 km;
- ``long`` (półmaraton, maraton): dłuższy taper, pełna regeneracja, limity czasu długiego biegu, test 10 km.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DistanceSpec:
    key: str
    category: str  # "short" | "long"
    km: float
    label: str
    distance_label: str
    taper_weeks: tuple[float, ...]
    race_week_long_share: float
    after_race_days: int
    min_long_km: int
    peaks_by_level: dict[str, tuple[int, int]]
    max_long_min_by_level: dict[str, int]
    test_distance: str  # "5k" | "10k"


DISTANCE_SPECS: dict[str, DistanceSpec] = {
    "5k": DistanceSpec(
        key="5k",
        category="short",
        km=5.0,
        label="5 km",
        distance_label="5 km",
        # Dzień startu wypada z limitu tygodnia i zastępuje długi bieg; 60% na dni przedstartowe daje ~40% tapera.
        taper_weeks=(0.6,),
        race_week_long_share=0.55,
        after_race_days=7,
        min_long_km=5,
        peaks_by_level={"poczatkujacy": (20, 6), "regularny": (30, 12), "zaawansowany": (45, 14)},
        max_long_min_by_level={},
        test_distance="5k",
    ),
    "10k": DistanceSpec(
        key="10k",
        category="short",
        km=10.0,
        label="10 km",
        distance_label="10 km",
        taper_weeks=(0.65, 0.85),
        race_week_long_share=0.6,
        after_race_days=7,
        min_long_km=10,
        peaks_by_level={"poczatkujacy": (25, 10), "regularny": (36, 16), "zaawansowany": (55, 18)},
        max_long_min_by_level={},
        test_distance="5k",
    ),
    "hm": DistanceSpec(
        key="hm",
        category="long",
        km=21.0975,
        label="półmaraton",
        distance_label="21,1 km",
        taper_weeks=(0.55, 0.8),
        race_week_long_share=1.0,
        after_race_days=7,
        min_long_km=16,
        peaks_by_level={"poczatkujacy": (32, 16), "regularny": (42, 20), "zaawansowany": (60, 24)},
        max_long_min_by_level={"poczatkujacy": 125},
        test_distance="10k",
    ),
    "marathon": DistanceSpec(
        key="marathon",
        category="long",
        km=42.195,
        label="maraton",
        distance_label="42,2 km",
        taper_weeks=(0.5, 0.7, 0.85),
        race_week_long_share=1.0,
        after_race_days=14,
        min_long_km=28,
        peaks_by_level={"poczatkujacy": (45, 28), "regularny": (56, 32), "zaawansowany": (80, 34)},
        max_long_min_by_level={"poczatkujacy": 180, "regularny": 180, "zaawansowany": 180},
        test_distance="10k",
    ),
}


def spec_for(goal: str | None) -> DistanceSpec | None:
    """Specyfikacja dystansu albo None dla celów niedystansowych."""
    return DISTANCE_SPECS.get(goal) if goal else None


def is_short_race(goal: str | None) -> bool:
    spec = spec_for(goal)
    return spec is not None and spec.category == "short"


def is_long_race(goal: str | None) -> bool:
    spec = spec_for(goal)
    return spec is not None and spec.category == "long"


def is_race_workout(workout: dict | None) -> bool:
    """Czy wpis planu reprezentuje dzień startu w zawodach."""
    return isinstance(workout, dict) and str(workout.get("name") or "").startswith("Start:")
