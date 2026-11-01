# -*- coding: utf-8 -*-
"""Prompty trenera AI: rola, zasady wspólne, moduły dobierane do biegacza i tryb wywołania.

Kolejność składania: trener → forma zwracania się → core/01–05 → poziom → cel → zdrowie → tryb
(→ przykłady w trybie planu) → prywatne zasady. Pliki .md nie zawierają danych żadnego biegacza;
dane idą osobno w wiadomości użytkownika. Prywatne dodatki: `local/moje-zasady-trenera.md`.
"""
from __future__ import annotations

from pathlib import Path

from trainer.config import SETTINGS

_DIR = Path(__file__).resolve().parent
PRIVATE_RULES = SETTINGS.local_dir / "moje-zasady-trenera.md"
CORE = ("core/01-bezpieczenstwo", "core/02-dane-i-niepewnosc", "core/03-gotowosc", "core/04-planowanie",
        "core/05-odpowiedz-i-kontrola")
GOAL_MODULES = {"5k": "cel/5km", "10k": "cel/10km", "hm": "cel/polmaraton", "marathon": "cel/maraton",
                "fitness": "cel/kondycja"}
LEVELS = ("poczatkujacy", "regularny", "zaawansowany")
MODES = {"plan": "tryby/plan-tygodnia", "dzien": "tryby/komentarz-dnia", "trening": "tryby/analiza-treningu"}
LANGUAGE = {"male": "jezyk/meski", "female": "jezyk/zenski", "neutral": "jezyk/neutralny"}


def load(name: str) -> str:
    """Treść jednego modułu, np. 'trener' albo 'poziom/poczatkujacy'."""
    return (_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def modules_for(runner: dict | None) -> list[str]:
    """Moduły poziomu, celu i zdrowia pasujące do profilu biegacza (z services.runner_profile)."""
    if not runner:
        return []
    level = runner.get("level") if runner.get("level") in LEVELS else "poczatkujacy"
    names = [f"poziom/{level}"]
    if runner.get("goal_distance") in GOAL_MODULES:
        names.append(GOAL_MODULES[runner["goal_distance"]])
    if (runner.get("age") or 0) >= 50:
        names.append("zdrowie/wiek-50")
    # Samo BMI nie mówi o kondycji: moduł tylko u osoby, która dopiero buduje bazę.
    if (runner.get("bmi") or 0) >= 30 and (level == "poczatkujacy" or runner.get("short_history")):
        names.append("zdrowie/wysoka-waga")
    if runner.get("health_notes") or runner.get("pain"):
        names.append("zdrowie/kontuzje")
    if runner.get("returning"):
        names.append("zdrowie/powrot-po-przerwie")
    if runner.get("decision") == "odpusc":
        names.append("zdrowie/regeneracja-i-przemeczenie")
    return names


def coach_prompt(runner: dict | None = None, *, mode: str | None = None, address_form: str | None = None,
                 private_path: Path = PRIVATE_RULES) -> str:
    """Prompt systemowy trenera dla trybu 'plan', 'dzien' albo 'trening'.

    Forma zwracania się: z argumentu, z profilu biegacza albo bez form płciowych.
    """
    form = address_form or (runner or {}).get("address_form")
    names = ["trener", LANGUAGE.get(form, LANGUAGE["neutral"]), *CORE, *modules_for(runner)]
    if mode == "plan":
        names.append("zdrowie/prewencja-i-sila")
    if mode in MODES:
        names.append(MODES[mode])
    if mode == "plan":
        names.append("przyklady")
    parts = [load(name) for name in names]
    try:
        private = private_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        private = ""
    if private:
        parts.append("# Dodatkowe zasady biegacza\n" + private)
    return "\n\n".join(parts)
