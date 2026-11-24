# -*- coding: utf-8 -*-
"""Profil biegacza liczony przy każdym planie: poziom, objętość, tętno, ostatni tydzień, cel, ciało.

Czysta logika na przekazanych danych. Liczony co tydzień, więc plan sam się dostosowuje:
gdy biegacz biega więcej i regularniej, rośnie poziom; gdy tętno albo wykonanie planu
sygnalizują zmęczenie, decyzja tygodnia każe odpuścić.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from services.activity_matching import find_activity_for_workout
from services.training_specs import is_long_race
from services.week_decision import (
    FATIGUE_CAUSES, LIGHT_DECISIONS, WEEK_LIMIT, _hrv_low, _race_days, cause_label, decide_week,
    decision_reason, earlier_week, easy_run_limit, long_run_limit, week_cap, week_reference,
)

# Odpowiedź z kreatora → przybliżony staż w miesiącach.
RUNNING_SINCE = {"start": 0, "under6": 3, "6to24": 12, "over24": 30}
RUNNING_SINCE_LABELS = {"start": "dopiero zaczyna", "under6": "do 6 miesięcy", "6to24": "6–24 miesiące",
                        "over24": "ponad 2 lata"}
LEVEL_LABELS = {"poczatkujacy": "początkujący", "regularny": "regularny", "zaawansowany": "zaawansowany"}
EARLIER_WEEKS = range(4, 12)  # tygodnie wstecz od poniedziałku (0 = ostatni pełny tydzień)
# Staż z kreatora od pół roku: poziom początkujący dopiero przy biegach krótszych niż to.
EXPERIENCED_SHORT_RUN_MIN = 30
# Garmin: efekt beztlenowy od 2,0 to trening z mocnymi odcinkami, nie bieg spokojny.
HARD_ANAEROBIC_EFFECT = 2.0
REGULAR_SECOND_QUALITY_RUNS = 4  # poziom regularny: drugi akcent w tygodniu dopiero od tylu biegów tygodniowo
# Spokojny bieg ze średnim tętnem tyle bpm pod Z3 lub bliżej: „górna granica Z2”, sygnał dla trenera (bez zmiany decyzji).
Z2_TOP_MARGIN = 3
EASY_TYPES = ("easy", "recovery", "long")
ADDRESS_FORMS = ("female", "male", "neutral")


def address_form(profile) -> str:
    """Forma zwracania się: wybór z kreatora, inaczej płeć z konta Garmin, inaczej bez form płciowych."""
    profile = profile or {}
    if profile.get("address_form") in ADDRESS_FORMS:
        return profile["address_form"]
    return profile.get("sex") if profile.get("sex") in ("female", "male") else "neutral"
WINDOW_DAYS = 28
# Krótka przerwa (od tylu dni, ale krótsza niż 3 tygodnie powrotu) nie liczy się do częstotliwości przy ocenie poziomu.
SHORT_BREAK_DAYS = 10
RETURNING_GAP_DAYS = 21
# Tyle dni historii biegów z zegarka (pobierane jest 120) wystarcza, by uznać, że osoba biega od dawna.
RUNNING_SEEN_DAYS = 90


def _run_day(activity) -> date | None:
    try:
        return date.fromisoformat(str(activity.get("date") or "")[:10])
    except ValueError:
        return None


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _runs(activities):
    return [a for a in activities or [] if isinstance(a, dict) and str(a.get("type") or "").startswith("running")
            and _run_day(a) is not None]


def running_months(profile, on: date, first_run: date | None = None) -> int | None:
    """Staż w miesiącach w dniu ``on``: odpowiedź z kreatora plus czas od jej udzielenia.

    ``first_run``: pierwszy bieg widoczny na zegarku. Gdy zegarek pokazuje bieganie krócej niż
    RUNNING_SEEN_DAYS, staż rośnie najwyżej o tyle miesięcy, ile widać biegania — sam kalendarz bez
    biegania nie robi z nikogo osoby doświadczonej.
    """
    base = RUNNING_SINCE.get((profile or {}).get("running_since"))
    if base is None:
        return None
    answered = None
    for key in ("running_since_at", "onboarding_completed_at"):
        try:
            answered = date.fromisoformat(str((profile or {}).get(key) or "")[:10])
            break
        except ValueError:
            continue
    if answered is None:
        return base
    elapsed = _full_months(answered, on)
    if first_run is not None and (on - first_run).days < RUNNING_SEEN_DAYS:
        elapsed = min(elapsed, _full_months(first_run, on))
    return base + max(elapsed, 0)


def _full_months(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month - (end.day < start.day)


def _returning(run_days: list[date], today: date) -> bool:
    """Biega znowu (ostatnie 14 dni) po co najmniej trzech tygodniach bez biegania."""
    recent = [d for d in run_days if d >= today - timedelta(days=14)]
    if not recent:
        return False
    before = [d for d in run_days if d < min(recent)]
    return bool(before) and (min(recent) - max(before)).days >= RETURNING_GAP_DAYS


def _planned_easy_runs(previous_plan, activities) -> list:
    """Biegi, które w poprzednim planie miały być spokojne (łatwy, regeneracyjny, długi)."""
    runs = []
    for workout in (previous_plan or {}).get("workouts") or []:
        if isinstance(workout, dict) and workout.get("type") in EASY_TYPES:
            activity, _ = find_activity_for_workout(workout=workout, activities=activities)
            if activity is not None and activity not in runs:
                runs.append(activity)
    return runs


def _adherence(previous_plan, activities, today: date):
    """Ile treningów z poprzedniego tygodnia wykonano i ile z nich było wyraźnie krótszych.

    Liczą się dni, które już minęły, i dzisiejszy trening, jeśli jest już zrobiony: plan na przyszły tydzień układany w niedzielę ocenia
    bieżący tydzień bez dni, które dopiero nadejdą.
    """
    planned = [w for w in (previous_plan or {}).get("workouts") or []
               if isinstance(w, dict) and w.get("type") != "rest"
               and (str(w.get("date") or "") < today.isoformat()
                    or (str(w.get("date") or "") == today.isoformat()
                        and find_activity_for_workout(workout=w, activities=activities)[0] is not None))]
    if not planned:
        return None, 0, 0
    done = shortened = 0
    for workout in planned:
        activity, _ = find_activity_for_workout(workout=workout, activities=activities)
        if activity is None:
            continue
        done += 1
        planned_min, actual = _number(workout.get("duration_min")), _number(activity.get("duration_min"))
        if planned_min and actual is not None and actual < 0.8 * planned_min:
            shortened += 1
    return done / len(planned), done, shortened


def _frequency(text) -> int | None:
    """Liczba treningów w tygodniu z kreatora („3 treningi w tygodniu”)."""
    match = re.search(r"\d", str(text or ""))
    return int(match.group(0)) if match and 1 <= int(match.group(0)) <= 7 else None


def _phase(target_date, today: date):
    try:
        race = date.fromisoformat(str(target_date or "")[:10])
    except ValueError:
        return None, None
    weeks = (race - today).days // 7
    if weeks < 0:
        return None, None
    return weeks, ("taper" if weeks <= 2 else "budowanie" if weeks <= 12 else "baza")


LEVEL_ORDER = ("poczatkujacy", "regularny", "zaawansowany")
# Poziom z historii: tyle ostatnich poniedziałków, tyle ocen z rzędu do awansu i do spadku.
LEVEL_HISTORY_WEEKS = 12
LEVEL_UP_WEEKS = 3
LEVEL_DOWN_WEEKS = 4


def _window_stats(runs, monday: date, until: date):
    """Biegi i km na tydzień z 28 dni przed ``monday``; najdłuższy bieg z 28 dni przed ``until``."""
    window = [a for a in runs if monday - timedelta(days=WINDOW_DAYS) <= _run_day(a) < monday]
    durations = [_number(a.get("duration_min")) for a in runs
                 if until - timedelta(days=WINDOW_DAYS) <= _run_day(a) < until and _number(a.get("duration_min"))]
    km = sum(_number(a.get("distance_km")) or 0 for a in window)
    return len(window) / 4, km / 4, (round(max(durations)) if durations else None)


def short_pause_days(runs, monday: date, window_days: int = WINDOW_DAYS) -> int:
    """Ile dni okna przed ``monday`` zajęła krótka przerwa (SHORT_BREAK_DAYS–20 dni bez biegania); 0 bez przerwy."""
    start = monday - timedelta(days=window_days)
    days = sorted({_run_day(a) for a in runs if _run_day(a) < monday})
    pause = 0
    for before, after in zip(days, days[1:]):
        gap = (after - before).days
        if after >= start and SHORT_BREAK_DAYS <= gap < RETURNING_GAP_DAYS:
            pause = max(pause, (after - max(before, start)).days)
    return pause


def _level_stats(runs, monday: date, until: date):
    """Dane do oceny poziomu z okna 28 dni, bez dni krótkiej przerwy (SHORT_BREAK_DAYS–20 dni bez biegania).

    Dwa tygodnie przerwy (wyjazd, przeziębienie) nie zmieniają kogoś biegającego regularnie w początkującego:
    wytrenowana osoba po takiej przerwie traci niewiele. Rzadkie bieganie bez przerwy nadal obniża poziom,
    a przerwa od 3 tygodni to powrót (moduł powrotu i ostrożny plan), jak dotąd.
    """
    rpw, km, longest = _window_stats(runs, monday, until)
    pause = short_pause_days(runs, monday)
    if not pause:
        return rpw, km, longest
    weeks = max((WINDOW_DAYS - pause) / 7, 1)
    return rpw * 4 / weeks, km * 4 / weeks, longest


def _level_rule(months, runs_per_week, km_per_week, longest, short_history, goal: str | None = None) -> str:
    """Poziom z jednego okna 28 dni."""
    # Długość biegów mówi o stażu tylko wtedy, gdy biegacz go nie podał: przy pół roku i dłużej
    # krótkie biegi pod 5 km to wybór, a nie brak przygotowania.
    short_run = EXPERIENCED_SHORT_RUN_MIN if months is not None and months >= 6 else 45
    if short_history and months is not None:
        return "poczatkujacy" if months < 6 else "regularny"
    if (months is not None and months < 6) or runs_per_week < 2 or (longest or 0) < short_run:
        return "poczatkujacy"
    if (months is None or months >= 24) and runs_per_week >= 4 and (
        km_per_week >= 40
        or ((longest or 0) >= 90 and km_per_week >= 35)
        or (goal == "5k" and runs_per_week >= 5 and km_per_week >= 30)
    ):
        return "zaawansowany"
    return "regularny"


def _settle_level(ratings: list[str]):
    """Poziom z kolejnych ocen tygodni: (poziom, indeks ostatniej zmiany albo None, "up"/"down"/None)."""
    if not ratings:
        return None, None, None
    # Start od najniższej z pierwszych ocen: przesuwające się okno historii samo nie podnosi poziomu.
    level, since, changed = min(ratings[:LEVEL_UP_WEEKS], key=LEVEL_ORDER.index), None, None
    up = down = 0
    for index, rated in enumerate(ratings[1:], start=1):
        if rated == "poczatkujacy" and level != "poczatkujacy":
            # Bezpiecznik ważniejszy niż stabilność: bez regularnego biegania od razu bez akcentów.
            level, since, changed, up, down = rated, index, "down", 0, 0
            continue
        step = LEVEL_ORDER.index(rated) - LEVEL_ORDER.index(level)
        up, down = (up + 1, 0) if step > 0 else (0, down + 1) if step < 0 else (0, 0)
        if up >= LEVEL_UP_WEEKS or down >= LEVEL_DOWN_WEEKS:
            direction = 1 if up else -1
            level, since, changed = LEVEL_ORDER[LEVEL_ORDER.index(level) + direction], index, "up" if up else "down"
            up = down = 0
    return level, since, changed


def _history_level(ratings: list[str]):
    """Poziom z ostatnich LEVEL_HISTORY_WEEKS ocen i zmiana do ogłoszenia: (poziom, "up"/"down"/None).

    ``ratings`` może mieć jedną ocenę więcej (najstarszą): zmiana jest ogłaszana tylko wtedy, gdy
    w ostatniej ocenie poziom naprawdę różni się od ustalonego tydzień wcześniej — a nie dlatego,
    że okno historii przesunęło się o tydzień.
    """
    current = ratings[-LEVEL_HISTORY_WEEKS:]
    level, since, changed = _settle_level(current)
    if since != len(current) - 1:
        return level, None
    if len(ratings) > 1 and _settle_level(ratings[:-1][-LEVEL_HISTORY_WEEKS:])[0] == level:
        return level, None
    return level, changed


def _level_history(runs, profile, monday: date, today: date):
    """Poziom ustalony z ocen ostatnich tygodni: (poziom, poniedziałek ustalenia, "up"/"down"/None).

    Tydzień bez biegów (przerwa) i punkt z historią krótszą niż 3 tygodnie nie są oceniane.
    Bez żadnej oceny — (None, None, None).
    """
    run_days = sorted(_run_day(a) for a in runs)
    if not run_days:
        return None, None, None
    goal = goal_distance(profile)
    points, ratings = [], []
    for k in range(LEVEL_HISTORY_WEEKS, -1, -1):  # o tydzień więcej: poziom ustalony tydzień wcześniej
        point = monday - timedelta(days=7 * k)
        if (point - run_days[0]).days < 21 or not any(point - timedelta(days=7) <= d < point for d in run_days):
            continue
        rpw, km, longest = _level_stats(runs, point, today if k == 0 else point)
        points.append(point)
        ratings.append(_level_rule(running_months(profile, point, first_run=run_days[0]), rpw, km, longest, False,
                                   goal=goal))
    if not ratings:
        return None, None, None
    level, index, _ = _settle_level(ratings[-LEVEL_HISTORY_WEEKS:])
    since = points[-LEVEL_HISTORY_WEEKS:][index] if index is not None else None
    _, announced = _history_level(ratings)
    return level, since, (announced if points[-1] == monday else None)


def _decimal(value) -> str:
    return f"{value:g}".replace(".", ",")


def _level_reason(runs_per_week, longest, pause=False) -> str | None:
    """Jedno zdanie z liczbami tej osoby (czas teraźniejszy — bez form płciowych).

    ``pause``: w oknie była krótka przerwa, więc średnia liczy tylko tygodnie z bieganiem.
    """
    if not runs_per_week:
        return None
    times = "raz" if runs_per_week == 1 else "razy"
    when = "Poza krótką przerwą biegasz" if pause else "W ostatnich 4 tygodniach biegasz"
    text = f"{when} średnio {_decimal(round(runs_per_week, 1))} {times} w tygodniu"
    return text + (f", a najdłuższy bieg trwał {longest} min." if longest else ".")


_LEVEL_UP_TEXT = {"regularny": "Trener traktuje Cię teraz jak osobę biegającą regularnie.",
                  "zaawansowany": "Trener traktuje Cię teraz jak osobę zaawansowaną."}
_LEVEL_DOWN_TEXT = {
    "regularny": "Ostatnie tygodnie były lżejsze, więc trener planuje teraz jak dla osoby biegającej regularnie.",
    "poczatkujacy": ("Ostatnie tygodnie były lżejsze, więc trener na razie planuje ostrożniej"
                     " — jak dla osoby, która zaczyna biegać."),
}


def level_message(runner: dict) -> str | None:
    """Zdanie na Stronę główną w tygodniu zmiany poziomu; bez zmiany, przy ręcznym wyborze i po przerwie — None."""
    runner = runner or {}
    if runner.get("level_override") or runner.get("returning"):
        return None
    if runner.get("level_changed") == "up" and runner.get("level_auto") in _LEVEL_UP_TEXT:
        reason = runner.get("level_reason")
        return f"{reason} {_LEVEL_UP_TEXT[runner['level_auto']]}" if reason else _LEVEL_UP_TEXT[runner["level_auto"]]
    if runner.get("level_changed") == "down" and runner.get("level_auto") in _LEVEL_DOWN_TEXT:
        return _LEVEL_DOWN_TEXT[runner["level_auto"]]
    return None


def _race_date(target_date) -> date | None:
    try:
        return date.fromisoformat(str(target_date or "")[:10])
    except ValueError:
        return None


def _quality_dose(workout) -> str:
    """„bieg progowy 30 min” albo „odcinki 3 × 8 min (strefa 4)” — rodzaj i dawka ostatniego akcentu."""
    zone = f" (strefa {str(workout.get('hr_zone')).lstrip('Zz')})" if workout.get("hr_zone") else ""
    if workout.get("type") == "intervals" and workout.get("repetitions"):
        if workout.get("work_meters"):
            meters = int(workout["work_meters"])
            length = f"{meters // 1000} km" if meters % 1000 == 0 else f"{meters} m"
            return f"odcinki {workout['repetitions']} × {length}{zone}"
        if workout.get("work_seconds"):
            work = workout["work_seconds"]
            length = f"{work // 60} min" if work % 60 == 0 else f"{work} s"
            return f"odcinki {workout['repetitions']} × {length}{zone}"
    names = {"tempo": "bieg tempowy", "threshold": "bieg progowy", "intervals": "odcinki"}
    main = (workout.get("duration_min") or 0) - 20
    return f"{names[workout['type']]}" + (f" {main} min" if main > 0 and workout["type"] != "intervals" else "") + zone


def goal_distance(profile) -> str | None:
    """Dystans celu: z pola kreatora, a przy starszym profilu (samo „półmaraton” w nazwie celu) — z nazwy."""
    profile = profile or {}
    if profile.get("target_distance"):
        return profile["target_distance"]
    if not profile.get("target_race"):
        return None
    from services.wizard import _distance_key  # leniwie: wizard importuje ten moduł
    key = _distance_key(profile["target_race"])
    return None if key == "other" else key


def build_runner_profile(*, activities, profile, today: date, rhr_trend=None, previous_plan=None,
                         pain=False, user_request=False, hrv=None, plan_monday: date | None = None,
                         phase_peak_km: float | None = None) -> dict:
    """Profil do promptu i do bezpieczników planu.

    ``user_request``: biegacz zostawił trenerowi wiadomość na ten tydzień; limit tygodnia rośnie do WEEK_REQUEST_LIMIT.
    ``rhr_trend``: {"recent": średnia 7 dni, "average": średnia 12 tygodni} tętna spoczynkowego.
    ``previous_plan``: plan poprzedniego tygodnia (do policzenia wykonania).
    ``plan_monday``: poniedziałek planowanego tygodnia, gdy plan powstaje wcześniej (np. w niedzielę na kolejny
    tydzień) — od niego liczą się tygodnie historii i dni do startu, żeby taper nie przesunął się o tydzień.
    ``phase_peak_km``: docelowy zakres tygodnia w bieżącej fazie strategii; gdy biegacz już go osiągnął,
    tydzień dostaje stabilizację (``at_peak``) zamiast dokładania ponad szczyt fazy.
    """
    profile = profile or {}
    monday = today - timedelta(days=today.weekday())
    if plan_monday is not None and plan_monday > monday:
        monday = plan_monday
    runs = _runs(activities)
    race_day = _race_date(profile.get("target_date"))
    goal = goal_distance(profile)
    exclude_long_race = race_day is not None and race_day < monday and is_long_race(goal)
    window = [a for a in runs if monday - timedelta(days=WINDOW_DAYS) <= _run_day(a) < monday
              and not (exclude_long_race and _run_day(a) == race_day)]
    weeks = {}  # 0 = ostatni pełny tydzień, 3 = najstarszy
    for activity in window:
        key = (monday - _run_day(activity)).days // 7
        week = weeks.setdefault(key, {"runs": 0, "km": 0.0, "minutes": 0.0})
        week["runs"] += 1
        week["km"] += _number(activity.get("distance_km")) or 0
        week["minutes"] += _number(activity.get("duration_min")) or 0
    # Najdłuższy bieg z 28 dni do dziś (z bieżącym tygodniem): ta sama liczba trafia do promptu i do bezpieczników.
    runs_per_week, km_per_week, longest = _window_stats(runs, monday, today)
    if race_day is not None and race_day < monday:
        # Sam start nie jest „najdłuższym niedawnym biegiem”: po maratonie długi bieg nie rośnie od 3,5 h zawodów.
        longest = _window_stats([a for a in runs if _run_day(a) != race_day], monday, today)[2]
    run_days = sorted(_run_day(a) for a in runs)
    # Zegarek z historią krótszą niż 3 tygodnie nie mówi jeszcze, jak ktoś biega.
    short_history = not run_days or (monday - run_days[0]).days < 21

    since = profile.get("running_since")
    level_rpw, level_km, level_longest = _level_stats(runs, monday, today)
    level_now = _level_rule(running_months(profile, today, first_run=run_days[0] if run_days else today),
                            level_rpw, level_km, level_longest, short_history, goal=goal)
    level_auto, level_since, level_changed = _level_history(runs, profile, monday, today)
    if level_auto is None:
        level_auto = level_now
    elif level_now == "poczatkujacy" and level_auto != "poczatkujacy" and not short_history:
        # Tydzień bez biegania nie jest oceniany, ale bezpiecznik działa od razu: po przerwie, zanim
        # pojawi się pierwszy bieg, trener nie planuje akcentów.
        level_auto, level_since, level_changed = "poczatkujacy", None, None
    override = profile.get("level_override") if profile.get("level_override") in LEVEL_LABELS else None
    level = level_auto
    if override:
        # Ręcznie można obniżyć poziom dowolnie, podnieść najwyżej o stopień — i nie przy krótkiej historii.
        ceiling = level_auto if short_history else LEVEL_ORDER[min(LEVEL_ORDER.index(level_auto) + 1, 2)]
        level = min(override, ceiling, key=LEVEL_ORDER.index)

    floors = profile.get("hr_zone_floors") or {}
    z3 = _number(floors.get("z3"))
    last_two_weeks = [a for a in runs if _run_day(a) >= monday - timedelta(days=14)]
    # Tylko biegi spokojne: akcent ma wysokie tętno z założenia i nie świadczy o zbyt mocnych
    # spokojnych biegach. Z planem — dokładnie te biegi, które miały być spokojne; bez planu — biegi
    # z 2 tygodni bez mocnych odcinków (efekt beztlenowy z Garmina).
    easy_runs = (_planned_easy_runs(previous_plan, activities)
                 or [a for a in last_two_weeks if (_number(a.get("ate")) or 0) < HARD_ANAEROBIC_EFFECT])
    with_hr = [a for a in easy_runs if _number(a.get("avg_hr"))]
    too_hard = sum(1 for a in with_hr if z3 and _number(a.get("avg_hr")) >= z3)
    near_top = sum(1 for a in with_hr if z3 and z3 - Z2_TOP_MARGIN <= _number(a.get("avg_hr")) < z3)
    rhr_recent = _number((rhr_trend or {}).get("recent"))
    rhr_normal = _number((rhr_trend or {}).get("average"))
    rhr_up = round(rhr_recent - rhr_normal) if rhr_recent is not None and rhr_normal is not None else None

    adherence, done, shortened = _adherence(previous_plan, activities, today)
    returning = _returning(run_days, today)
    # Opuszczone treningi same w sobie nie są zmęczeniem (wyjazd, praca): lżejszy tydzień dopiero wtedy,
    # gdy także wykonane treningi wychodziły wyraźnie krótsze.
    struggling = adherence is not None and adherence < 0.6 and shortened > 0
    hr_too_high = len(with_hr) >= 2 and too_hard * 2 >= len(with_hr)
    week_minutes = [weeks.get(key, {}).get("minutes", 0.0) for key in (3, 2, 1, 0)]
    hrv_low, hrv_values = _hrv_low(hrv, today)
    at_volume_peak = bool(phase_peak_km and km_per_week >= phase_peak_km)
    week = decide_week(
        pain=pain, rhr_up=rhr_up, struggling=struggling, hrv_low=hrv_low, adherence=adherence, returning=returning,
        hr_too_high=hr_too_high, short_history=short_history, week_minutes=week_minutes,
        race_days=_race_days(profile.get("target_date"), monday), goal=goal, at_volume_peak=at_volume_peak)
    decision, cause, taper_factor, taper = week.decision, week.cause, week.taper_factor, week.taper

    weight, height = _number(profile.get("weight_kg")), _number(profile.get("height_cm"))
    max_week = round(max((w["minutes"] for w in weeks.values()), default=0)) or None
    older = dict.fromkeys(EARLIER_WEEKS, 0.0)
    for activity in runs:
        key = (monday - _run_day(activity)).days // 7
        if key in older:
            older[key] += _number(activity.get("duration_min")) or 0
    earlier = earlier_week(list(older.values()))
    # Szybki powrót tylko bez sygnałów ostrzegawczych: nie po przerwie, nie przy opuszczonych treningach
    # z planu i nie przy zbyt mocnych spokojnych biegach („utrzymaj” bez danych o planie albo „dołóż”).
    comeback_ok = bool(earlier) and not returning and not taper and (
        decision == "doloz" or (decision == "utrzymaj" and cause == "low_adherence"
                                and adherence is None and not hr_too_high))
    cap = (week_cap(week_minutes, decision, earlier, comeback=comeback_ok, request=user_request)
           if not short_history else None)
    comeback = bool(cap) and cap > (week_cap(week_minutes, decision, earlier, request=user_request) or 0)
    if comeback:
        decision, cause = "odbuduj", "comeback"
    if short_history:
        # Nowy zegarek: limit z tygodni, które już są w danych, bez dokładania (a przy bólu/zmęczeniu z lekkim limitem).
        known = [minutes for minutes in week_minutes if minutes]
        if known:
            factor = WEEK_LIMIT[decision] if decision in LIGHT_DECISIONS else WEEK_LIMIT["utrzymaj"]
            cap = round(max(known) * factor)
            if decision in ("doloz", "odbuduj"):
                decision, cause = "utrzymaj", "short_history"
    if cap and taper_factor is not None and week_reference(week_minutes):
        cap = round(week_reference(week_minutes) * taper_factor)
    reference = week_reference(week_minutes)
    weeks_to_race, phase = _phase(profile.get("target_date"), monday)  # ten sam poniedziałek co decyzja
    return {
        "level": "poczatkujacy" if returning else level,
        "level_auto": level_auto,
        "level_since": level_since.isoformat() if level_since else None,
        "level_changed": level_changed,
        "level_override": override,
        "level_reason": _level_reason(level_rpw, longest, pause=level_rpw != runs_per_week),
        "returning": returning,
        "running_since": since,
        "short_history": short_history,
        "runs_per_week": round(runs_per_week, 1),
        "km_per_week": round(km_per_week, 1),
        "longest_min": longest,
        "max_week_minutes": max_week,
        "week_reference_min": round(reference) if reference else None,
        "earlier_week_min": round(earlier) if earlier else None,
        "comeback": comeback,
        "decision_cause": cause,
        "taper_percent": round(taper_factor * 100) if taper_factor is not None else None,
        "user_request": bool(user_request),
        "last_quality_kinds": sorted({w.get("type") for w in (previous_plan or {}).get("workouts") or []
                                      if isinstance(w, dict) and w.get("type") in ("tempo", "threshold", "intervals")}),
        "last_quality": [_quality_dose(w) for w in (previous_plan or {}).get("workouts") or []
                         if isinstance(w, dict) and w.get("type") in ("tempo", "threshold", "intervals")],
        "week_cap_min": cap,
        "easy_runs_with_hr": len(with_hr),
        "runs_above_z2": too_hard,
        "runs_near_z2_top": near_top,
        "hrv_low": hrv_low,
        "hrv": hrv_values,
        "rhr_up": rhr_up,
        "vo2max": _number(profile.get("vo2max_running")),
        "adherence": adherence,
        "done": done,
        "shortened": shortened,
        "pain": bool(pain),
        "decision": decision,
        "goal_distance": goal_distance(profile),
        "frequency": _frequency(profile.get("training_frequency")),
        "weeks_to_race": weeks_to_race,
        "phase": phase,
        "age": _number(profile.get("age")),
        "sex": profile.get("sex"),
        "address_form": address_form(profile),
        "bmi": round(weight / (height / 100) ** 2, 1) if weight and height else None,
        "health_notes": str(profile.get("health_notes") or "").strip()[:300],
    }


def quality_sessions_limit(runner: dict, configured=None) -> int:
    """Limit treningów jakościowych w tygodniu — ta sama liczba w prompcie i w kodzie.

    Początkujący (także po powrocie od przerwy) nie dostaje mocnych akcentów w ogóle; regularny drugi akcent
    tylko przy co najmniej 4 biegach w tygodniu; zaawansowany tyle, ile ustawiono w kreatorze.
    Brak ustawienia znaczy jeden trening. Przy zmęczeniu, bólu i po starcie 0; w tygodniu cofnięcia i w taperze najwyżej 1.
    """
    level = (runner or {}).get("level")
    if level == "poczatkujacy" or (runner or {}).get("decision_cause") in FATIGUE_CAUSES:
        return 0  # początkujący, a także zmęczenie, ból i tydzień po starcie: bez akcentów
    if configured is None:
        return 1
    try:
        wanted = max(int(configured), 0)
    except (TypeError, ValueError):
        return 1
    # Drugi akcent na poziomie regularnym tylko przy co najmniej 4 biegach w tygodniu: przy trzech między mocnymi
    # dniami nie ma miejsca na spokojne biegi (tak też mówi moduł poziomu w prompcie).
    if level == "regularny" and (runner.get("runs_per_week") or 0) < REGULAR_SECOND_QUALITY_RUNS:
        return min(wanted, 1)
    if (runner or {}).get("decision_cause") in ("step_back", "taper", "race_week", "after_short_race"):
        return min(wanted, 1)  # tydzień cofnięcia i taper: najwyżej jeden krótszy akcent
    return wanted


def profile_lines(runner: dict, *, weekly: bool = True) -> list[str]:
    """Sekcja PROFIL BIEGACZA w wiadomości do AI; ``weekly`` dodaje decyzję i limity tygodnia (tylko plan)."""
    def value(number, unit=""):
        return "brak" if number is None else f"{str(number).replace('.', ',')}{unit}"

    lines = [f"- poziom: {LEVEL_LABELS[runner['level']]}"
             + (" (powrót po co najmniej 3 tygodniach przerwy)" if runner["returning"] else "")]
    if runner.get("running_since"):
        lines.append(f"- biega regularnie: {RUNNING_SINCE_LABELS.get(runner['running_since'], 'brak')}")
    if runner["short_history"]:
        lines.append("- historia z zegarka: krótsza niż 3 tygodnie, liczby poniżej są niepełne")
    lines.append(f"- ostatnie 4 tygodnie: średnio {value(runner['runs_per_week'])} biegu/tydz., "
                 f"{value(runner['km_per_week'], ' km')}/tydz., najdłuższy bieg {value(runner['longest_min'], ' min')}, "
                 f"zwykły tydzień {value(runner.get('week_reference_min'), ' min')}, "
                 f"największy tydzień {value(runner['max_week_minutes'], ' min')}")
    if runner.get("comeback"):
        lines.append(f"- wcześniej (5–12 tygodni temu) zwykły tydzień {runner['earlier_week_min']} min: "
                     "to znana już objętość, można do niej wracać stopniowo w granicach limitu tygodnia")
    if runner["easy_runs_with_hr"]:
        lines.append(f"- tętno na spokojnych biegach (bez akcentów): {runner['runs_above_z2']} z "
                     f"{runner['easy_runs_with_hr']} biegów ze średnim tętnem powyżej strefy 2")
        if runner.get("runs_near_z2_top", 0) * 2 >= runner["easy_runs_with_hr"]:
            lines.append(f"- {runner['runs_near_z2_top']} z {runner['easy_runs_with_hr']} spokojnych biegów przy samej "
                         "górnej granicy strefy 2: w opisach biegów łatwych przypomnij o wolniejszym tempie "
                         "i swobodnej rozmowie, żeby nie wejść w szarą strefę")
    if runner.get("hrv_low") and runner.get("hrv"):
        values = runner["hrv"]
        lines.append(f"- HRV: średnia z tygodnia {value(values.get('weekly_avg'), ' ms')}, poniżej zakresu tej osoby "
                     f"(od {value(values.get('baseline_low'), ' ms')}) — sygnał zmęczenia, bez dokładania")
    if runner["rhr_up"] is not None:
        lines.append(f"- tętno spoczynkowe: {runner['rhr_up']:+d} bpm wobec normy z 12 tygodni")
    if runner["adherence"] is not None:
        lines.append(f"- poprzedni tydzień: wykonano {round(runner['adherence'] * 100)}% treningów z planu"
                     + (f", {runner['shortened']} wyraźnie krótszych" if runner["shortened"] else ""))
    if runner["vo2max"]:
        lines.append(f"- VO2max z zegarka: {value(runner['vo2max'])}")
    if runner["weeks_to_race"] is not None:
        lines.append(f"- do startu: {runner['weeks_to_race']} tyg. (faza: {runner['phase']})")
    body = [f"wiek {value(runner['age'] and int(runner['age']))}"]
    if runner.get("sex") in ("female", "male"):
        body.append("kobieta" if runner["sex"] == "female" else "mężczyzna")
    if runner["bmi"]:
        body.append(f"BMI {value(runner['bmi'])}")
    lines.append("- ciało: " + ", ".join(body))
    if runner["health_notes"]:
        lines.append(f"- zdrowie (opis biegacza): {runner['health_notes']}")
    if not weekly:
        return lines
    lines.append(f"- DECYZJA TYGODNIA: {cause_label(runner)}")
    lines.append(f"- powód decyzji (napisz go biegaczowi jednym zdaniem w `summary`): {decision_reason(runner)}")
    limits = []
    if runner["longest_min"]:
        limits.append(f"długi bieg najwyżej {long_run_limit(runner, runner['longest_min'])} min, "
                      f"bieg łatwy i akcent najwyżej {easy_run_limit(runner, runner['longest_min'])} min")
    quality_names = {"tempo": "bieg tempowy", "threshold": "bieg progowy", "intervals": "odcinki"}
    if runner.get("last_quality_kinds") and runner.get("decision") in ("doloz", "odbuduj"):
        names = ", ".join(runner.get("last_quality") or [quality_names[k] for k in runner["last_quality_kinds"]])
        lines.append(f"- ostatnie akcenty: {names} — w tym tygodniu rośnie objętość, więc akcent zostaje tego samego "
                     "rodzaju i dawki; nowy, szybszy rodzaj (np. odcinki w tempie 5 km) w tygodniu bez wzrostu")
    if runner.get("frequency"):
        count = runner["frequency"]
        limits.append(f"najwyżej {count} " + ("trening" if count == 1 else "treningi" if count <= 4 else "treningów")
                      + " w tygodniu")
    if runner.get("week_cap_min"):
        limits.append(f"cały tydzień najwyżej {runner['week_cap_min']} min biegania")
    window = runner.get("window_cap_min")
    if window and (not runner.get("week_cap_min") or window < runner["week_cap_min"]):
        limits.append(f"w dniach, które biegacz ma dostępne, mieści się łącznie najwyżej {window} min")
    if runner["level"] == "poczatkujacy":
        limits.append("bez interwałów, biegu progowego i tempowego")
    if limits:
        lines.append("- LIMITY APLIKACJI (plan, który je przekroczy, zostanie przycięty): " + "; ".join(limits))
    return lines
