# -*- coding: utf-8 -*-
"""Profil biegacza dla stron aplikacji: ten sam, z którego korzystają prompt i bezpieczniki planu."""
from __future__ import annotations

import logging
from datetime import date

from services.runner_profile import build_runner_profile

logger = logging.getLogger(__name__)


def current_runner(*, snapshot_provider, profile_provider, today: date) -> dict | None:
    """Profil biegacza z danych z zegarka; bez danych albo przy błędzie odczytu — None."""
    try:
        data = getattr(snapshot_provider(), "data", None)
        if not isinstance(data, dict):
            return None
        return build_runner_profile(activities=data.get("activities"), profile=profile_provider() or {},
                                    today=today)
    except Exception:  # noqa: BLE001 - strona działa bez sekcji poziomu
        logger.warning("Could not build the runner level")
        return None
