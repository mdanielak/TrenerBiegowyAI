# -*- coding: utf-8 -*-
"""
Workout services — re-exports GarminWorkout for the services layer.

Importable from CLI, tests, and future API:
    from services.workouts import GarminWorkout
"""
from trainer.workouts import GarminWorkout

__all__ = ['GarminWorkout']
