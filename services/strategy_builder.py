# -*- coding: utf-8 -*-
"""Strategia długoterminowa ułożona z celu z kreatora i ostatnich biegów, bez AI.

Wynik to ten sam Markdown, który czyta services.strategy (strona Cel, Statystyki) i który trafia
do promptu planu tygodnia. Objętości rosną od tego, co biegacz faktycznie biega, nigdy od wzorca.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from services import strategy as strategy_service
from services.runner_profile import WINDOW_DAYS, _number, _run_day, _runs
from trainer.files import write_atomic

# dystans: (km, nazwa, szczytowy tydzień km, docelowy długi bieg km, tygodnie odpoczynku przed startem)
_DISTANCES = {
    "5k": (5.0, "5 km", 30, 12, 1),
    "10k": (10.0, "10 km", 36, 16, 1),
    "hm": (21.0975, "półmaraton", 42, 20, 2),
    "marathon": (42.195, "maraton", 56, 32, 3),
}
MIN_WEEKS = 4
_WEEKLY_GROWTH = 1.08  # sufit wzrostu tygodnia: szczyt nie może uciec od obecnego biegania
_DEFAULT_START_KM = 15
_PHASES = (
    ("Baza", "łatwa objętość i przebieżki; kilka tygodni bez bólu i z {runs} biegami/tydz."),
    ("Budowanie", "jeden akcent w tygodniu: odcinki progowe kontrolowane tętnem"),
    ("Przygotowanie startowe", "odcinki w tempie startowym, zawsze jeden główny akcent"),
)
_TAPER = ("Szczyt formy i odpoczynek przed startem", "krótkie utrzymanie tempa startowego")


def _weekly_volume(week: float, start_km: float, peak: int) -> int:
    """Objętość tygodnia po danej liczbie tygodni: krzywa wzrostu, ograniczona szczytem.

    Faza dostaje tę objętość, do której biegacz dochodzi w swoim tempie, a nie co trzecią
    część różnicy między startem a szczytem. Dzięki temu pierwsza faza zaczyna się tam,
    gdzie biegacz jest dziś, zamiast skakać o kilkanaście kilometrów.
    """
    return min(peak, round(start_km * _WEEKLY_GROWTH ** max(week, 0)))


def recent_volume(activities, today: date) -> tuple[float | None, float | None]:
    """Średnie kilometry na tydzień i najdłuższy bieg (km) z ostatnich 28 dni; None bez biegów."""
    window = [a for a in _runs(activities) if today - timedelta(days=WINDOW_DAYS) <= _run_day(a) <= today]
    distances = [_number(a.get("distance_km")) or 0 for a in window]
    if not any(distances):
        return None, None
    return sum(distances) / 4, max(distances)


def _seconds(text) -> int | None:
    parts = str(text or "").split(":")
    if not 2 <= len(parts) <= 3 or not all(part.isdigit() for part in parts):
        return None
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return total


def _clock(seconds: float) -> str:
    seconds = int(round(seconds / 30) * 30)
    return f"{seconds // 60}:{seconds % 60:02d}"


def _span(start: date, end: date) -> str:
    return f"{start:%d.%m.%Y}—{end:%d.%m.%Y}"


def build_strategy_markdown(*, profile: dict, activities, today: date) -> str:
    """Zbuduj strategię albo zgłoś ValueError z powodem zrozumiałym dla biegacza."""
    profile = profile or {}
    distance = _DISTANCES.get(profile.get("target_distance"))
    if distance is None:
        raise ValueError("Fazy przygotowań układam dla 5 km, 10 km, półmaratonu i maratonu. "
                         "Przy innym celu plan tygodnia działa bez strategii.")
    kilometres, label, peak_target, long_target, taper_weeks = distance
    try:
        race = date.fromisoformat(str(profile.get("target_date") or "")[:10])
    except ValueError:
        raise ValueError("Najpierw ustaw datę zawodów w celu i dniach treningowych.") from None
    monday = today - timedelta(days=today.weekday())
    if (race - today).days < MIN_WEEKS * 7:
        raise ValueError(f"Do startu zostało mniej niż {MIN_WEEKS} tygodnie — na fazy przygotowań jest za późno. "
                         "Trzymaj się planu tygodnia.")

    taper_start = race - timedelta(days=taper_weeks * 7 - 1)
    weeks = (taper_start - monday).days // 7
    specific = min(6, weeks // 3)
    build = min(8, (weeks - specific) // 2)
    specific_start = taper_start - timedelta(days=specific * 7)
    build_start = specific_start - timedelta(days=build * 7)
    spans = [(monday, build_start - timedelta(days=1)), (build_start, specific_start - timedelta(days=1)),
             (specific_start, taper_start - timedelta(days=1))]
    stages = [(name, hint, start, end) for (name, hint), (start, end) in zip(_PHASES, spans) if end >= start]

    weekly_km, longest_km = recent_volume(activities, today)
    start_km = max(round(weekly_km), 8) if weekly_km else _DEFAULT_START_KM
    peak = max(start_km, min(peak_target, round(start_km * _WEEKLY_GROWTH ** max(weeks, 1))))
    long_start = max(round(longest_km), 5) if longest_km else max(round(start_km * 0.3), 5)
    frequency = next((int(ch) for ch in str(profile.get("training_frequency") or "") if ch.isdigit()), 4)
    runs = f"{max(frequency - 1, 1)}-{frequency}"

    rows, long_range = [], (long_start, long_start + 2)
    for name, hint, start, end in stages:
        # Tyle tygodni minęło od początku planu do końca fazy — tyle wynosi objętość.
        week = (end - monday).days / 7
        top = _weekly_volume(week, start_km, peak)
        long_top = min(_weekly_volume(week, long_start, max(long_target, long_start)),
                       max(round(top * 0.5), 6))
        long_range = (max(long_top - 3, 4), max(long_top, 6))
        rows.append(f"| {name} | {_span(start, end)} | zwykle {max(round(top * 0.8), 6)}-{top} km, "
                    f"long {long_range[0]}-{long_range[1]} km | {hint.format(runs=runs)} |")
    taper_long = (max(long_range[1] - 6, 4), max(long_range[1] - 4, 6))
    rows.append(f"| {_TAPER[0]} | {_span(taper_start, race)} | redukcja objętości, "
                f"long maks. {taper_long[0]}-{taper_long[1]} km | {_TAPER[1]} |")

    target = profile.get("target_time") or ""
    target_seconds = _seconds(target)
    title = " ".join(part for part in (label.capitalize(), target) if part) + f" — {race.year}"
    pace = f" (~{_clock(target_seconds / kilometres)}/km)" if target_seconds else ""
    test = ""
    if target_seconds and kilometres > 10:
        # Wzór Riegla: czas rośnie z dystansem do potęgi 1,06.
        ten = target_seconds * (10 / kilometres) ** 1.06
        test = f" Potwierdzeniem powinien być test 10 km około **{_clock(ten - 30)}-{_clock(ten + 30)}**."
    basis = (f"ostatnie 4 tygodnie to średnio {str(round(weekly_km, 1)).replace('.', ',')} km tygodniowo, "
             f"najdłuższy bieg {str(round(longest_km, 1)).replace('.', ',')} km" if weekly_km
             else "zegarek nie ma jeszcze biegów z ostatnich 4 tygodni, więc punkt wyjścia jest ostrożny")
    return "\n".join([
        f"# {title}",
        "",
        f"**Strategia ułożona automatycznie {today.isoformat()} z celu zapisanego w kreatorze i ostatnich biegów.** "
        "Zakresy są orientacyjne i rosną od tego, co biegasz teraz. To nie jest porada medyczna.",
        "",
        "## Źródła i ograniczenia danych",
        "",
        f"Punkt wyjścia: {basis}. Strefy tętna aplikacja bierze z konta Garmin.",
        "",
        "## Diagnoza, cele i priorytety",
        "",
        f"1. **Cel główny:** {label}{' ' + target if target else ''}{pace}, **{race.isoformat()}**.",
        "2. Łatwe, regeneracyjne i długie biegi prowadzimy po tętnie. Maksymalnie jeden główny akcent tygodniowo.",
        "",
        f"## Periodyzacja: {monday.isoformat()}—{race.isoformat()}",
        "",
        "| Faza | Daty robocze | Objętość i long run | Jeden akcent / warunek przejścia |",
        "|---|---|---|---|",
        *rows,
        "",
        "Objętość jest zakresem, nie obowiązkiem. Po 2-3 tygodniach budowania zaplanuj lżejszy tydzień, "
        "a po chorobie, bólu lub przerwie wróć o co najmniej jeden krok fazy.",
        "",
        "## Reguły modyfikacji",
        "",
        "- Narastający ból, tętno spoczynkowe wyraźnie ponad własny trend albo słaby sen przez 2 noce: "
        "zamień akcent na łatwy bieg albo odpoczynek.",
        "- Jeden opuszczony trening nie wymaga odrabiania.",
        "",
        "## Kryteria gotowości do celu",
        "",
        f"Cel pozostaje warunkowy. Potrzebne są: stabilne tygodnie w docelowym zakresie, regularne long runy "
        f"{long_range[0]}-{long_range[1]} km, brak narastającego bólu oraz kilka tygodni z rzędu z {runs} biegami/tydz.{test}",
        "",
    ])


def save_strategy(text: str, *, path: Path | None = None, now: datetime | None = None) -> Path:
    """Zapisz strategię; dotychczasowa (np. pisana ręcznie) zostaje obok jako kopia, nigdy nie znika."""
    path = path or strategy_service.STRATEGY_PATH
    if path.exists():
        stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
        path.replace(path.with_name(f"{path.stem}-poprzednia-{stamp}.md"))
    write_atomic(path, text)
    return path
