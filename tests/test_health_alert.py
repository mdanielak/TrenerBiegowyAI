# -*- coding: utf-8 -*-
"""Baner zdrowia na stronie głównej."""
from types import SimpleNamespace

from api.views.today import _health_alert


def _report(level="ready", score=7.0, hrv_alert=None):
    return SimpleNamespace(readiness={"level": level, "score": score, "max_score": 10.0}, hrv_alert=hrv_alert)


def test_no_banner_when_signals_are_fine():
    assert _health_alert(_report()) is None


def test_hrv_alert_alone_is_a_warning():
    alert = _health_alert(_report(hrv_alert={"days": 5}))

    assert alert["tone"] == "warn"
    assert alert["reasons"] == ["HRV niskie lub niezrównoważone od 5 dni z rzędu."]


def test_low_readiness_or_pain_asks_for_rest():
    alert = _health_alert(_report(level="not_ready", score=1.0),
                          [{"date": "2026-10-28", "pain": ["calf", "knee"]}])

    assert alert["tone"] == "bad" and alert["title"] == "Dziś lepiej odpuścić trening"
    assert alert["reasons"][0] == "Gotowość 1 z 10 — organizm jeszcze się regeneruje."
    assert alert["reasons"][1] == "W dzienniku zapisano ból: łydka, kolano (28 października 2026)."
