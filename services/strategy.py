# -*- coding: utf-8 -*-
"""Odczyt strategii długoterminowej: fazy periodyzacji i kryteria gotowości.

Źródłem jest Markdown pisany dla człowieka, więc parser jest celowo tolerancyjny:
czego nie da się odczytać, tego nie ma (None), a brak pliku nie jest błędem.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from trainer.config import PROJECT_ROOT

# Własna strategia zostaje na komputerze (git jej nie śledzi); do repozytorium trafia tylko przykład.
# Przykład nigdy nie zastępuje własnej strategii: plan AI układany na cudzych celach byłby mylący.
_LONG_TERM = PROJECT_ROOT / "training-plans" / "long-term"
# Neutralna nazwa dla każdego biegacza; dawny plik (nazwany od półmaratonu autora) działa, gdy nowego nie ma.
def strategy_path(long_term: Path) -> Path:
    """`strategia.md`, a gdy jej nie ma, a jest dawny `half-marathon-2027.md` — ten dawny."""
    current, legacy = long_term / "strategia.md", long_term / "half-marathon-2027.md"
    return legacy if legacy.exists() and not current.exists() else current


STRATEGY_PATH = strategy_path(_LONG_TERM)
STRATEGY_EXAMPLE_PATH = _LONG_TERM / "przyklad-strategii.md"

_DATE_RANGE = re.compile(
    r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\s*[—–-]+\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")
# „12-16 km” albo „ok. 42 km” (objętość stoi w miejscu przez całą fazę).
_LONG = re.compile(r"long(?:\s+maks\.)?\s+(?:ok\.\s+)?(\d+)(?:\s*-\s*(\d+))?\s*km")
_KM = re.compile(r"(\d+)(?:\s*-\s*(\d+))?\s*km")
_LONG_TARGET = re.compile(r"long run\w*\s+(?:ok\.\s+)?(\d+)(?:\s*-\s*(\d+))?\s*km")
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
    if not match:
        return None
    low = int(match.group(1))
    return low, int(match.group(2) or low)


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


def structured_path(path: Path) -> Path:
    """Plik JSON ze strukturą strategii zapisany obok tekstu (np. ``strategia.json`` obok ``strategia.md``)."""
    return path.with_suffix(".json")


def strategy_to_json(strategy: Strategy) -> str:
    return json.dumps(asdict(strategy), ensure_ascii=False, indent=2, default=str) + "\n"


def _pair(value) -> tuple[int, int] | None:
    return (int(value[0]), int(value[1])) if isinstance(value, (list, tuple)) and len(value) == 2 else None


def strategy_from_json(text: str) -> Strategy:
    """Struktura zapisana przez generator strategii; ValueError, gdy plik jest uszkodzony."""
    data = json.loads(text)
    try:
        phases = tuple(Phase(str(item["name"]), date.fromisoformat(item["start"]), date.fromisoformat(item["end"]),
                             _pair(item.get("km")), _pair(item.get("long_km"))) for item in data["phases"])
        return Strategy(title=str(data.get("title") or ""), phases=phases,
                        long_run_target=_pair(data.get("long_run_target")),
                        test_10k_seconds=_pair(data.get("test_10k_seconds")),
                        runs_per_week=_pair(data.get("runs_per_week")))
    except (KeyError, TypeError) as error:
        raise ValueError("Uszkodzony plik struktury strategii") from error


def load_strategy(path=None) -> Strategy | None:
    """Strategia z pliku albo None, gdy pliku nie ma lub nie zawiera faz.

    Strategia z generatora ma obok strukturę w JSON — czytamy ją, o ile tekst nie był potem edytowany ręcznie
    (wtedy tekst jest nowszy i wygrywa tolerancyjny odczyt Markdownu).
    """
    path = path or STRATEGY_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    sidecar = structured_path(path)
    try:
        if sidecar.stat().st_mtime >= path.stat().st_mtime:
            strategy = strategy_from_json(sidecar.read_text(encoding="utf-8"))
            if strategy.phases:
                return strategy
    except (OSError, UnicodeError, ValueError):
        pass  # brak albo uszkodzona struktura: odczyt z tekstu
    strategy = parse_strategy(text)
    return strategy if strategy.phases else None
