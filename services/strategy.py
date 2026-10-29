# -*- coding: utf-8 -*-
"""Odczyt strategii długoterminowej: fazy periodyzacji i kryteria gotowości.

Źródłem jest Markdown pisany dla człowieka, więc parser jest celowo tolerancyjny:
czego nie da się odczytać, tego nie ma (None), a brak pliku nie jest błędem.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from trainer.config import PROJECT_ROOT

# Własna strategia zostaje na komputerze (git jej nie śledzi); do repozytorium trafia tylko przykład.
# Przykład nigdy nie zastępuje własnej strategii: plan AI układany na cudzych celach byłby mylący.
STRATEGY_PATH = PROJECT_ROOT / "training-plans" / "long-term" / "half-marathon-2027.md"
STRATEGY_EXAMPLE_PATH = PROJECT_ROOT / "training-plans" / "long-term" / "przyklad-strategii.md"

_DATE_RANGE = re.compile(
    r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\s*[—–-]+\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")
_LONG = re.compile(r"long(?:\s+maks\.)?\s+(\d+)\s*-\s*(\d+)\s*km")
_KM = re.compile(r"(\d+)\s*-\s*(\d+)\s*km")
_LONG_TARGET = re.compile(r"long run\w*\s+(\d+)\s*-\s*(\d+)\s*km")
_TEST_10K = re.compile(r"test 10 km[^0-9]*(\d+):(\d{2})\s*-\s*(\d+):(\d{2})")
_RUNS_PER_WEEK = re.compile(r"(\d)\s*-\s*(\d)\s*biegami/tydz")


@dataclass(frozen=True)
class Phase:
    name: str
    start: date
    end: date
    km: tuple[int, int] | None
    long_km: tuple[int, int] | None


@dataclass(frozen=True)
class Strategy:
    title: str
    phases: tuple[Phase, ...]
    long_run_target: tuple[int, int] | None
    test_10k_seconds: tuple[int, int] | None
    runs_per_week: tuple[int, int] | None

    def phase_for(self, day: date) -> Phase | None:
        return next((phase for phase in self.phases if phase.start <= day <= phase.end), None)


def _range(match) -> tuple[int, int] | None:
    return (int(match.group(1)), int(match.group(2))) if match else None


def _parse_phase(cells) -> Phase | None:
    if len(cells) < 3:
        return None
    dates = _DATE_RANGE.search(cells[1])
    if not dates:
        return None
    start_day, start_month, start_year, end_day, end_month, end_year = dates.groups()
    end = date(int(end_year), int(end_month), int(end_day))
    year = int(start_year) if start_year else end.year
    start = date(year, int(start_month), int(start_day))
    if start > end and not start_year:
        start = start.replace(year=year - 1)
    volume = cells[2]
    long_km = _LONG.search(volume)
    weekly = _KM.search(_LONG.sub("", volume))
    return Phase(cells[0].strip(), start, end, _range(weekly), _range(long_km))


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^##\s+{re.escape(heading)}.*?$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    return match.group(1) if match else ""


def parse_strategy(text: str) -> Strategy:
    """Wyciągnij z Markdownu fazy i progi; każda nierozpoznana część zostaje pusta."""
    title_match = re.search(r"^#\s+(.+)$", text, re.M)
    phases = []
    for line in _section(text, "Periodyzacja").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        phase = _parse_phase(cells)
        if phase is not None:
            phases.append(phase)

    criteria = _section(text, "Kryteria gotowości").replace("*", "")
    test = _TEST_10K.search(criteria)
    return Strategy(
        title=title_match.group(1).strip() if title_match else "",
        phases=tuple(phases),
        long_run_target=_range(_LONG_TARGET.search(criteria)),
        test_10k_seconds=((int(test.group(1)) * 60 + int(test.group(2)),
                           int(test.group(3)) * 60 + int(test.group(4))) if test else None),
        runs_per_week=_range(_RUNS_PER_WEEK.search(text)),
    )


def load_strategy(path=None) -> Strategy | None:
    """Strategia z pliku albo None, gdy pliku nie ma lub nie zawiera faz."""
    try:
        text = (path or STRATEGY_PATH).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    strategy = parse_strategy(text)
    return strategy if strategy.phases else None
