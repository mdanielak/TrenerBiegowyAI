# -*- coding: utf-8 -*-
"""Strategia długoterminowa ułożona z celu z kreatora i ostatnich biegów, bez AI.

Wynik to ten sam Markdown, który czyta services.strategy (strona Cel, Statystyki) i który trafia
do promptu planu tygodnia. Objętości rosną od tego, co biegacz faktycznie biega, nigdy od wzorca.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from services import strategy as strategy_service
from services.runner_profile import WINDOW_DAYS, _number, _run_day, _runs, goal_distance, short_pause_days
from trainer.files import write_atomic

# dystans: (km, nazwa, szczytowy tydzień km, docelowy długi bieg km, tygodnie odpoczynku przed startem)
# Szczyt dla poziomu „regularny”; dla innych poziomów nadpisuje go _PEAKS.
_DISTANCES = {
    "5k": (5.0, "5 km", 30, 12, 1),
    "10k": (10.0, "10 km", 36, 16, 2),  # taper 2 tygodnie, jak TAPER_WEEKS w services/week_decision.py
    "hm": (21.0975, "półmaraton", 42, 20, 2),
    "marathon": (42.195, "maraton", 56, 32, 3),
}
# (szczytowy tydzień km, docelowy długi bieg km) zależnie od poziomu: osoba zaczynająca przed pierwszym 5 km
# nie potrzebuje 30 km tygodniowo ani 12 km długiego biegu; zaawansowany maratończyk potrzebuje więcej.
_PEAKS = {
    "5k": {"poczatkujacy": (20, 6), "zaawansowany": (45, 14)},
    "10k": {"poczatkujacy": (25, 10), "zaawansowany": (55, 18)},
    "hm": {"poczatkujacy": (32, 16), "zaawansowany": (60, 24)},
    "marathon": {"poczatkujacy": (45, 28), "zaawansowany": (80, 34)},
}
MIN_WEEKS = 4
# Średni wzrost tygodnia w strategii: „dołóż” +5–10% i co czwarty tydzień cofnięcia dają w praktyce ok. 3%
# tygodniowo (ok. 12–15% w miesiącu) — tyle, ile pozwolą decyzje tygodnia w aplikacji.
_WEEKLY_GROWTH = 1.03
# Długi bieg rośnie w praktyce szybciej niż cały tydzień (+10% albo +5 min na tydzień, z tygodniami cofnięcia):
# średnio ok. 5% tygodniowo.
_LONG_GROWTH = 1.05
# Najkrótszy długi bieg, który zwykle wystarcza przed startem na danym dystansie (km); mniej — mówimy to wprost.
_MIN_LONG_BEFORE_RACE = {"5k": 5, "10k": 10, "hm": 16, "marathon": 28}
_DEFAULT_START_KM = 15
_PHASES = (
    ("Baza", "łatwa objętość i przebieżki; kilka tygodni bez bólu i z {runs} biegami/tydz."),
    ("Budowanie", "{build}"),
    ("Przygotowanie startowe", "{specific}"),
)
# Co dzieje się w fazach budowania i startowej zależy od poziomu (te same zasady co limit akcentów w aplikacji).
_LEVEL_HINTS = {
    "poczatkujacy": ("bez mocnych akcentów: przebieżki i luźny fartlek; akcent dopiero, gdy aplikacja uzna "
                     "poziom regularny", "spokojne biegi i przebieżki, oswojenie z dystansem startu"),
    "regularny": ("jeden akcent w tygodniu: odcinki progowe kontrolowane tętnem",
                  "odcinki w tempie startowym, zawsze jeden główny akcent"),
    "zaawansowany": ("jeden główny akcent (odcinki progowe); przy dwóch w ustawieniach drugi lekki bodziec",
                     "odcinki w tempie startowym jako główny akcent; drugi bodziec tylko lekki"),
}
_TAPER = ("Szczyt formy i odpoczynek przed startem", "krótkie utrzymanie tempa startowego")


def _weekly_volume(week: float, start_km: float, peak: int, growth: float | None = None) -> int:
    """Objętość tygodnia po danej liczbie tygodni: krzywa wzrostu, ograniczona szczytem.

    Faza dostaje tę objętość, do której biegacz dochodzi w swoim tempie, a nie co trzecią
    część różnicy między startem a szczytem. Dzięki temu pierwsza faza zaczyna się tam,
    gdzie biegacz jest dziś, zamiast skakać o kilkanaście kilometrów.
    """
    return min(peak, round(start_km * (growth or _WEEKLY_GROWTH) ** max(week, 0)))


_MONTHS = ("styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec", "sierpień", "wrzesień",
           "październik", "listopad", "grudzień")


def _km_range(low, high) -> str:
    """„12-16 km” albo „ok. 6 km”, gdy oba końce są równe."""
    return f"{low}-{high} km" if high > low else f"ok. {high} km"


def _minutes_note(low_km, high_km, pace) -> str:
    """„ (ok. 110–270 min)” przy tempie biegacza: limity tygodnia w aplikacji są w minutach, strategia w km."""
    if not pace:
        return ""
    low, high = round(low_km * pace / 5) * 5, round(high_km * pace / 5) * 5
    return f" (ok. {low} min)" if low == high else f" (ok. {low}–{high} min)"


def _monthly_steps(monday: date, until: date, start_km: float, peak: int) -> str:
    """Zwykły tydzień na początku kolejnych miesięcy, aż objętość dojdzie do szczytu; pusty, gdy nie ma czego rozpisać."""
    steps, day = [], date(monday.year + monday.month // 12, monday.month % 12 + 1, 1)
    while day < until:
        km = _weekly_volume((day - monday).days / 7, start_km, peak)
        steps.append(f"{_MONTHS[day.month - 1]} ok. {km} km")
        if km >= peak:
            break
        day = date(day.year + day.month // 12, day.month % 12 + 1, 1)
    return ", ".join(steps) + (" i tak do startu" if steps and steps[-1].endswith(f"{peak} km") else "") if len(steps) > 1 else ""


def recent_volume(activities, today: date) -> tuple[float | None, float | None]:
    """Średnie kilometry na tydzień i najdłuższy bieg (km) z ostatnich 28 dni; None bez biegów.

    Dni krótkiej przerwy (10–20 dni bez biegania) nie liczą się do średniej: po wyjeździe punkt wyjścia
    strategii to zwykłe bieganie, a nie średnia zaniżona pustymi tygodniami.
    """
    runs = _runs(activities)
    window = [a for a in runs if today - timedelta(days=WINDOW_DAYS) <= _run_day(a) <= today]
    distances = [_number(a.get("distance_km")) or 0 for a in window]
    if not any(distances):
        return None, None
    pause = short_pause_days(runs, today + timedelta(days=1))
    # Nowy zegarek: dzielimy przez tyle dni, ile obejmują dane, a nie przez całe 4 tygodnie.
    first = min(_run_day(a) for a in runs)
    days = min(WINDOW_DAYS, (today - first).days + 1)
    weeks = max((days - pause) / 7, 1)
    return sum(distances) / weeks, max(distances)


def recent_pace(activities, today: date) -> float | None:
    """Średnie tempo (min/km) z biegów ostatnich 28 dni — do przeliczenia kilometrów strategii na minuty."""
    window = [a for a in _runs(activities) if today - timedelta(days=WINDOW_DAYS) <= _run_day(a) <= today]
    km = sum(_number(a.get("distance_km")) or 0 for a in window)
    minutes = sum(_number(a.get("duration_min")) or 0 for a in window)
    return minutes / km if km and minutes else None


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
    """Zbuduj strategię (sam tekst) albo zgłoś ValueError z powodem zrozumiałym dla biegacza."""
    return build_strategy(profile=profile, activities=activities, today=today)[0]


def build_strategy(*, profile: dict, activities, today: date):
    """Strategia jako (Markdown dla człowieka, ``Strategy`` dla aplikacji) — obie postaci z tych samych liczb.

    Aplikacja czyta strukturę (zapisaną obok jako JSON), więc nie zależy od tego, jak wygląda tabela w tekście.
    """
    from services.strategy import Phase, Strategy

    profile = profile or {}
    distance = _DISTANCES.get(goal_distance(profile))
    if distance is None:
        raise ValueError("Fazy przygotowań układam dla 5 km, 10 km, półmaratonu i maratonu. "
                         "Przy innym celu plan tygodnia działa bez strategii.")
    kilometres, label, peak_target, long_target, taper_weeks = distance
    from services.runner_profile import build_runner_profile, goal_distance as _goal

    level = build_runner_profile(activities=activities, profile=profile, today=today)["level"]
    peak_target, long_target = _PEAKS.get(_goal(profile), {}).get(level, (peak_target, long_target))
    build_hint, specific_hint = _LEVEL_HINTS[level]
    run_pace = recent_pace(activities, today)
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

    rows, phases, long_range = [], [], (long_start, long_start + 2)
    for name, hint, start, end in stages:
        # Zakres fazy: od objętości na jej początku do objętości na końcu. Wcześniej wiersz pokazywał sam koniec,
        # więc długa faza bazy zaczynała się „od szczytu”, choć biegacz jest dziś daleko niżej.
        first, last = (start - monday).days / 7, (end - monday).days / 7
        low, top = _weekly_volume(first, start_km, peak), _weekly_volume(last, start_km, peak)
        long_cap = max(long_target, long_start)
        long_low = min(_weekly_volume(first, long_start, long_cap, _LONG_GROWTH), max(round(low * 0.5), 6))
        long_top = min(_weekly_volume(last, long_start, long_cap, _LONG_GROWTH), max(round(top * 0.5), 6))
        long_range = (max(long_low, 4), max(long_top, 6))
        # Format czyta parser strategii (services/strategy.py): „od-do km” albo „ok. N km”, gdy faza stoi w miejscu.
        volume = f"zwykle {low}-{top} km" if top > low else f"ok. {top} km"
        longs = (f"long {long_range[0]}-{long_range[1]} km" if long_range[1] > long_range[0]
                 else f"long ok. {long_range[1]} km")
        phases.append(Phase(name, start, end, (low, top), long_range))
        hint = hint.format(runs=runs, build=build_hint, specific=specific_hint)
        rows.append(f"| {name} | {_span(start, end)} | {volume}{_minutes_note(low, top, run_pace)}, "
                    f"{longs}{_minutes_note(long_range[0], long_range[1], run_pace)} | {hint} |")
    # Taper: długi bieg o ok. 20–40% krótszy (procentowo, nie o stałe km — przy krótkich długich biegach to była połowa).
    taper_long = (max(round(long_range[1] * 0.6), 4), max(round(long_range[1] * 0.8), 5))
    steps = _monthly_steps(monday, taper_start, start_km, peak)
    needed = _MIN_LONG_BEFORE_RACE.get(_goal(profile))
    realism = ""
    if needed and long_range[1] < needed:
        minutes = _minutes_note(long_range[1], long_range[1], run_pace).strip()
        realism = (f"**Uwaga na termin:** przy bezpiecznym tempie budowania najdłuższy bieg dojdzie do ok. {long_range[1]} km"
                   f"{' ' + minutes if minutes else ''}, a przed tym dystansem zwykle potrzeba ok. {needed} km. "
                   "Rozważ późniejszy start albo cel „ukończyć spokojnie”, z marszem w razie potrzeby — "
                   "nie przyspieszaj budowania, żeby zdążyć.")
    taper_hint = "krótkie spokojne biegi, bez nowych bodźców" if level == "poczatkujacy" else _TAPER[1]
    phases.append(Phase(_TAPER[0], taper_start, race, None, taper_long))
    rows.append(f"| {_TAPER[0]} | {_span(taper_start, race)} | redukcja objętości, "
                f"long maks. {taper_long[0]}-{taper_long[1]} km | {taper_hint} |")

    target = profile.get("target_time") or ""
    target_seconds = _seconds(target)
    title = " ".join(part for part in (label.capitalize(), target) if part) + f" — {race.year}"
    pace = f" (~{_clock(target_seconds / kilometres)}/km)" if target_seconds else ""
    test, test_seconds = "", None
    if target_seconds and kilometres > 10:
        # Wzór Riegla: czas rośnie z dystansem do potęgi 1,06.
        ten = target_seconds * (10 / kilometres) ** 1.06
        test = f" Potwierdzeniem powinien być test 10 km około **{_clock(ten - 30)}-{_clock(ten + 30)}**."
        test_seconds = (_seconds(_clock(ten - 30)), _seconds(_clock(ten + 30)))
    structured = Strategy(title="", phases=tuple(phases), long_run_target=long_range, test_10k_seconds=test_seconds,
                          runs_per_week=(max(frequency - 1, 1), frequency))
    basis = (f"ostatnie 4 tygodnie to średnio {str(round(weekly_km, 1)).replace('.', ',')} km tygodniowo, "
             f"najdłuższy bieg {str(round(longest_km, 1)).replace('.', ',')} km" if weekly_km
             else "zegarek nie ma jeszcze biegów z ostatnich 4 tygodni, więc punkt wyjścia jest ostrożny")
    text = "\n".join([
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
        "2. Łatwe, regeneracyjne i długie biegi prowadzimy po tętnie. "
        + ("Bez mocnych akcentów, dopóki aplikacja nie uzna poziomu regularnego." if level == "poczatkujacy"
           else "Jeden główny akcent tygodniowo."),
        *([f"3. Minuty w nawiasach liczone przy Twoim średnim tempie z ostatnich biegów "
           f"(ok. {_clock(run_pace * 60)}/km); limity tygodnia w aplikacji są w minutach."] if run_pace else []),
        "",
        f"## Periodyzacja: {monday.isoformat()}—{race.isoformat()}",
        "",
        "| Faza | Daty robocze | Objętość i long run | Akcenty / warunek przejścia |",
        "|---|---|---|---|",
        *rows,
        "",
        *([f"Kroki po drodze (zwykły tydzień): {steps}.", ""] if steps else []),
        "Objętość jest zakresem, nie obowiązkiem. Lżejszy tydzień aplikacja wstawia sama po trzech tygodniach wzrostu, "
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
        *([realism, ""] if realism else []),
        f"Cel pozostaje warunkowy. Potrzebne są: stabilne tygodnie w docelowym zakresie, regularne long runy "
        f"{_km_range(*long_range)}, brak narastającego bólu oraz kilka tygodni z rzędu z {runs} biegami/tydz.{test}",
        "",
    ])
    from dataclasses import replace
    return text, replace(structured, title=title)


def save_strategy(text: str, *, path: Path | None = None, now: datetime | None = None, structured=None) -> Path:
    """Zapisz strategię; dotychczasowa (np. pisana ręcznie) zostaje obok jako kopia, nigdy nie znika.

    ``structured`` (``Strategy`` z ``build_strategy``) trafia obok jako JSON: aplikacja czyta go zamiast tabeli
    z tekstu. Bez niego dawny JSON jest usuwany, żeby nie opisywał innej strategii niż tekst.
    """
    path = path or strategy_service.STRATEGY_PATH
    if path.exists():
        stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
        path.replace(path.with_name(f"{path.stem}-poprzednia-{stamp}.md"))
    write_atomic(path, text)
    sidecar = strategy_service.structured_path(path)
    if structured is not None:
        write_atomic(sidecar, strategy_service.strategy_to_json(structured))
    else:
        sidecar.unlink(missing_ok=True)
    return path
