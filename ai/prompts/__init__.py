# -*- coding: utf-8 -*-
"""Prompty trenera AI: ogólna rola i moduły dobierane do profilu biegacza.

Teksty leżą w plikach .md obok tego modułu i nie zawierają danych żadnego konkretnego biegacza.
Prywatne dodatki (np. własna strategia autora) można dopisać w `local/moje-zasady-trenera.md`.
"""
from __future__ import annotations

from pathlib import Path

from trainer.config import SETTINGS

_DIR = Path(__file__).resolve().parent
PRIVATE_RULES = SETTINGS.local_dir / "moje-zasady-trenera.md"
GOAL_MODULES = {"5k": "cel/5km", "10k": "cel/10km", "hm": "cel/polmaraton", "marathon": "cel/maraton",
                "fitness": "cel/kondycja"}


def load(name: str) -> str:
    """Treść jednego modułu, np. 'trener' albo 'poziom/poczatkujacy'."""
    return (_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def modules_for(runner: dict | None) -> list[str]:
    """Moduły pasujące do profilu biegacza (z services.runner_profile)."""
    if not runner:
        return []
    names = [f"poziom/{runner['level']}"]
    if runner.get("goal_distance") in GOAL_MODULES:
        names.append(GOAL_MODULES[runner["goal_distance"]])
    if (runner.get("age") or 0) >= 50:
        names.append("zdrowie/wiek-50")
    if (runner.get("bmi") or 0) >= 30:
        names.append("zdrowie/wysoka-waga")
    if runner.get("health_notes"):
        names.append("zdrowie/kontuzje")
    if runner.get("returning"):
        names.append("zdrowie/powrot-po-przerwie")
    return names


def coach_prompt(runner: dict | None = None, *, private_path: Path = PRIVATE_RULES) -> str:
    """Prompt systemowy trenera: rola, moduły profilu i opcjonalne prywatne zasady."""
    parts = [load("trener")] + [load(name) for name in modules_for(runner)]
    try:
        private = private_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        private = ""
    if private:
        parts.append("## Dodatkowe zasady biegacza\n" + private)
    return "\n\n".join(parts)
