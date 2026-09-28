# -*- coding: utf-8 -*-
"""
Workout services — re-exports GarminWorkout for the services layer.

Importable from CLI, tests, and future API:
    from services.workouts import GarminWorkout
"""
from garmin_workout import GarminWorkout

__all__ = ['GarminWorkout']
