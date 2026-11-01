# -*- coding: utf-8 -*-
"""Nazwy faz ze strategii bez żargonu biegowego w widoku."""
from api.views.goal import _plain_phase_name


def test_jargon_is_translated():
    assert _plain_phase_name("Szczyt i taper") == "Szczyt formy i odpoczynek przed startem"
    assert _plain_phase_name("Specyfika HM") == "Przygotowanie startowe do półmaratonu"
    assert _plain_phase_name("Tapering") == "Odpoczynek przed startem"


def test_plain_names_stay_untouched():
    assert _plain_phase_name("Baza zimowa") == "Baza zimowa"
    assert _plain_phase_name("HMMMa") == "HMMMa"
