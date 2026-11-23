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

# Odpowiedź z kreatora → przybliżony staż w miesiącach.
RUNNING_SINCE = {"start": 0, "under6": 3, "6to24": 12, "over24": 30}
RUNNING_SINCE_LABELS = {"start": "dopiero zaczyna", "under6": "do 6 miesięcy", "6to24": "6–24 miesiące",
                        "over24": "ponad 2 lata"}
LEVEL_LABELS = {"poczatkujacy": "początkujący", "regularny": "regularny", "zaawansowany": "zaawansowany"}
DECISION_LABELS = {
    "regeneracja": "regeneracja — bardzo lekki tydzień (około 60% zwykłego tygodnia), tylko spokojne krótkie biegi",
    "odpusc": "odpuść — wyraźnie lżejszy tydzień (około 75% zwykłego tygodnia z ostatniego czasu)",
    "utrzymaj": "utrzymaj — podobna objętość jak ostatnio, bez dokładania",
    "doloz": "dołóż — objętość może wzrosnąć o 5–10%",
    "odbuduj": "odbuduj — powrót do znanej objętości, tydzień może być do 25% dłuższy niż ostatni, "
               "ale nie dłuższy niż zwykły tydzień sprzed 5–12 tygodni",
}
# Dwa lekkie stopnie: bez zapasu na prośbę biegacza i bez „nie niżej niż ostatni tydzień”.
LIGHT_DECISIONS = ("regeneracja", "odpusc")
# Twardy sufit, nie cel: mnożnik zwykłego tygodnia (week_reference), którego plan nie przekroczy.
# Cel opisują DECISION_LABELS (utrzymaj = podobnie jak ostatnio, czyli 1,0); sufit to tylko zapas.
WEEK_LIMIT = {"regeneracja": 0.6, "odpusc": 0.75, "utrzymaj": 1.1, "doloz": 1.15, "odbuduj": 1.15}
# Gdy biegacz zostawił trenerowi wiadomość na tydzień (np. „wydłuż niedzielę”), sufit tygodnia rośnie o tyle
# (a długi bieg może być o LONG_RUN_REQUEST_STEP_MIN dłuższy niż zwykle). Nie dotyczy „odpuść”
# (ból, zmęczenie, wiele opuszczonych treningów).
WEEK_REQUEST_LIMIT = 1.2
# Tydzień nigdy nie przekracza tylu średnich z czterech tygodni: chroni przed skokiem obciążenia
# zaraz po wyjątkowo dużym tygodniu.
WEEK_SPIKE_LIMIT = 1.3
# Powrót do objętości sprzed 5–12 tygodni: tydzień może urosnąć o tyle wobec ostatniego, ale nie ponad
# tamten zwykły tydzień. Znane już obciążenie odbudowuje się szybciej niż nowe.
COMEBACK_STEP = 1.25
EARLIER_WEEKS = range(4, 12)  # tygodnie wstecz od poniedziałku (0 = ostatni pełny tydzień)
EARLIER_MIN_WEEKS = 6  # z 8: dopiero regularne bieganie to wcześniejsza objętość
# Staż z kreatora od pół roku: poziom początkujący dopiero przy biegach krótszych niż to.
EXPERIENCED_SHORT_RUN_MIN = 30
# Garmin: efekt beztlenowy od 2,0 to trening z mocnymi odcinkami, nie bieg spokojny.
HARD_ANAEROBIC_EFFECT = 2.0
EASY_TYPES = ("easy", "recovery", "long")
# Długi bieg najwyżej tyle minut dłuższy niż najdłuższy niedawny bieg; łatwy nie dłuższy niż on.
LONG_RUN_STEP_MIN = 10
LONG_RUN_REQUEST_STEP_MIN = 15  # przy wiadomości od biegacza (nie dotyczy „odpuść”)
ADDRESS_FORMS = ("female", "male", "neutral")


def address_form(profile) -> str:
    """Forma zwracania się: wybór z kreatora, inaczej płeć z konta Garmin, inaczej bez form płciowych."""
    profile = profile or {}
    if profile.get("address_form") in ADDRESS_FORMS:
        return profile["address_form"]
    return profile.get("sex") if profile.get("sex") in ("female", "male") else "neutral"
WINDOW_DAYS = 28
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
    return bool(before) and (min(recent) - max(before)).days >= 21


def long_run_step(runner) -> int:
    """O ile minut długi bieg może przekroczyć najdłuższy niedawny; przy wiadomości od biegacza o 5 więcej."""
    runner = runner or {}
    asked = runner.get("user_request") and runner.get("decision") not in LIGHT_DECISIONS
    return LONG_RUN_REQUEST_STEP_MIN if asked else LONG_RUN_STEP_MIN


def week_reference(week_minutes: list[float]) -> float | None:
    """Zwykły tydzień z ostatnich czterech (od najstarszego do ostatniego) — podstawa limitu tygodnia.

    Ostatni tydzień albo mediana z czterech, co większe: jeden wyjątkowo duży tydzień sprzed miesiąca
    nie zawyża limitu, a stopniowo rosnący trening nie jest cofany. Brak biegów w tygodniu to 0 minut.
    """
    if not week_minutes or not any(week_minutes):
        return None
    ordered = sorted(week_minutes)
    middle = len(ordered) // 2
    median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return max(week_minutes[-1], median)


def earlier_week(week_minutes: list[float]) -> float | None:
    """Zwykły tydzień sprzed okna limitu (tygodnie EARLIER_WEEKS, puste jako 0): mediana wszystkich.

    Tylko przy regularnym bieganiu (co najmniej EARLIER_MIN_WEEKS tygodni z biegami); inaczej None.
    """
    if sum(1 for m in week_minutes if m) < EARLIER_MIN_WEEKS:
        return None
    ordered = sorted(week_minutes)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def week_cap(week_minutes: list[float], decision: str, earlier: float | None = None,
             comeback: bool = False, request: bool = False) -> int | None:
    """Limit minut planowanego tygodnia: zwykły tydzień razy mnożnik decyzji, bez skoku ponad średnią.

    Poza „odpuść” limit nie schodzi poniżej ostatniego tygodnia, o ile ten mieści się w znanym obciążeniu
    (najwyżej WEEK_SPIKE_LIMIT × największy wcześniejszy tydzień albo ``earlier``): pusty tydzień w oknie
    nie ścina planu, a tydzień-skok nie jest powtarzany. ``earlier``: zwykły tydzień sprzed 5–12 tygodni;
    przy ``comeback`` limit rośnie do niego szybciej (COMEBACK_STEP wobec ostatniego tygodnia).
    """
    reference = week_reference(week_minutes)
    if not reference:
        return None
    average = sum(week_minutes) / len(week_minutes)
    cap = min(reference * WEEK_LIMIT[decision], average * WEEK_SPIKE_LIMIT)
    if decision not in LIGHT_DECISIONS:
        last = week_minutes[-1]
        known = max([*week_minutes[:-1], earlier or 0])
        cap = max(cap, min(last, known * WEEK_SPIKE_LIMIT))
        if comeback and earlier and earlier > cap:
            cap = min(earlier, max(cap, last * COMEBACK_STEP))
        if request:
            boosted = cap * WEEK_REQUEST_LIMIT  # prośba biegacza: o 20% ponad sufit (nie dotyczy lekkich stopni)
            # Przy powrocie do znanej objętości prośba nie wyprowadza ponad zwykły tydzień sprzed 5–12 tygodni.
            cap = min(boosted, max(earlier, cap)) if comeback and earlier else boosted
    return round(cap)


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


def _level_rule(months, runs_per_week, km_per_week, longest, short_history) -> str:
    """Poziom z jednego okna 28 dni — progi bez zmian od wersji 0.8.0."""
    # Długość biegów mówi o stażu tylko wtedy, gdy biegacz go nie podał: przy pół roku i dłużej
    # krótkie biegi pod 5 km to wybór, a nie brak przygotowania.
    short_run = EXPERIENCED_SHORT_RUN_MIN if months is not None and months >= 6 else 45
    if short_history and months is not None:
        return "poczatkujacy" if months < 6 else "regularny"
    if (months is not None and months < 6) or runs_per_week < 2 or (longest or 0) < short_run:
        return "poczatkujacy"
    if (months is None or months >= 24) and runs_per_week >= 4 and ((longest or 0) >= 90 or km_per_week >= 40):
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
    points, ratings = [], []
    for k in range(LEVEL_HISTORY_WEEKS, -1, -1):  # o tydzień więcej: poziom ustalony tydzień wcześniej
        point = monday - timedelta(days=7 * k)
        if (point - run_days[0]).days < 21 or not any(point - timedelta(days=7) <= d < point for d in run_days):
            continue
        rpw, km, longest = _window_stats(runs, point, today if k == 0 else point)
        points.append(point)
        ratings.append(_level_rule(running_months(profile, point, first_run=run_days[0]), rpw, km, longest, False))
    if not ratings:
        return None, None, None
    level, index, _ = _settle_level(ratings[-LEVEL_HISTORY_WEEKS:])
    since = points[-LEVEL_HISTORY_WEEKS:][index] if index is not None else None
    _, announced = _history_level(ratings)
    return level, since, (announced if points[-1] == monday else None)


def _decimal(value) -> str:
    return f"{value:g}".replace(".", ",")


def _level_reason(runs_per_week, longest) -> str | None:
    """Jedno zdanie z liczbami tej osoby (czas teraźniejszy — bez form płciowych)."""
    if not runs_per_week:
        return None
    times = "raz" if runs_per_week == 1 else "razy"
    text = f"W ostatnich 4 tygodniach biegasz średnio {_decimal(round(runs_per_week, 1))} {times} w tygodniu"
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


RHR_REGENERATION_BPM = 8  # tętno spoczynkowe o tyle wyższe niż zwykle: tydzień regeneracji, nie tylko lżejszy
STEP_BACK_GROWTH = 1.03  # tydzień „rośnie”, gdy ma co najmniej 3% więcej minut niż poprzedni


def _rising_weeks(week_minutes: list[float]) -> bool:
    """Cztery tygodnie z rzędu rosła objętość (trzy wzrosty): czas na lżejszy tydzień cofnięcia."""
    if len(week_minutes) < 4 or not all(week_minutes):
        return False
    return all(week_minutes[i + 1] >= week_minutes[i] * STEP_BACK_GROWTH for i in range(len(week_minutes) - 1))


def _after_light_week(week_minutes: list[float]) -> bool:
    """Po wzroście przyszedł wyraźnie lżejszy tydzień (cofnięcie): najpierw ustabilizować, potem dokładać.

    Zwykłe wahania (raz cztery biegi, raz trzy) nie są cofnięciem: potrzebny wzrost przed spadkiem.
    """
    if len(week_minutes) < 3 or not week_minutes[-2] or not week_minutes[-3]:
        return False
    return week_minutes[-2] >= week_minutes[-3] * STEP_BACK_GROWTH and week_minutes[-1] <= 0.85 * week_minutes[-2]


def _race_days(target_date, today: date) -> int | None:
    """Ile dni do startu (ujemnie: dni po starcie); None bez daty celu."""
    try:
        return (date.fromisoformat(str(target_date or "")[:10]) - today).days
    except ValueError:
        return None


def build_runner_profile(*, activities, profile, today: date, rhr_trend=None, previous_plan=None,
                         pain=False, user_request=False) -> dict:
    """Profil do promptu i do bezpieczników planu.

    ``user_request``: biegacz zostawił trenerowi wiadomość na ten tydzień; limit tygodnia rośnie do WEEK_REQUEST_LIMIT.
    ``rhr_trend``: {"recent": średnia 7 dni, "average": średnia 12 tygodni} tętna spoczynkowego.
    ``previous_plan``: plan poprzedniego tygodnia (do policzenia wykonania).
    """
    profile = profile or {}
    monday = today - timedelta(days=today.weekday())
    runs = _runs(activities)
    window = [a for a in runs if monday - timedelta(days=WINDOW_DAYS) <= _run_day(a) < monday]
    weeks = {}  # 0 = ostatni pełny tydzień, 3 = najstarszy
    for activity in window:
        key = (monday - _run_day(activity)).days // 7
        week = weeks.setdefault(key, {"runs": 0, "km": 0.0, "minutes": 0.0})
        week["runs"] += 1
        week["km"] += _number(activity.get("distance_km")) or 0
        week["minutes"] += _number(activity.get("duration_min")) or 0
    # Najdłuższy bieg z 28 dni do dziś (z bieżącym tygodniem): ta sama liczba trafia do promptu i do bezpieczników.
    runs_per_week, km_per_week, longest = _window_stats(runs, monday, today)
    run_days = sorted(_run_day(a) for a in runs)
    # Zegarek z historią krótszą niż 3 tygodnie nie mówi jeszcze, jak ktoś biega.
    short_history = not run_days or (monday - run_days[0]).days < 21

    since = profile.get("running_since")
    level_now = _level_rule(running_months(profile, today, first_run=run_days[0] if run_days else today),
                            runs_per_week, km_per_week, longest, short_history)
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
    race_days = _race_days(profile.get("target_date"), today)
    taper = race_days is not None and 0 <= race_days < 21
    if pain:
        decision, cause = "regeneracja", "pain"
    elif rhr_up is not None and rhr_up >= RHR_REGENERATION_BPM:
        decision, cause = "regeneracja", "rhr_high"
    elif rhr_up is not None and rhr_up >= 5:
        decision, cause = "odpusc", "rhr_up"
    elif struggling:
        decision, cause = "odpusc", "struggling"
    elif race_days is not None and 0 <= race_days < 7:
        decision, cause = "odpusc", "race_week"
    elif race_days is not None and -7 < race_days < 0:
        decision, cause = "odpusc", "after_race"
    elif not short_history and _rising_weeks(week_minutes):
        decision, cause = "odpusc", "step_back"
    elif adherence is None or adherence < 0.9 or returning or hr_too_high:
        decision, cause = "utrzymaj", "low_adherence"
    elif taper:
        decision, cause = "utrzymaj", "taper"
    elif not short_history and _after_light_week(week_minutes):
        decision, cause = "utrzymaj", "stabilise"
    else:
        decision, cause = "doloz", "ready"

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
    reference = week_reference(week_minutes)
    weeks_to_race, phase = _phase(profile.get("target_date"), today)
    return {
        "level": "poczatkujacy" if returning else level,
        "level_auto": level_auto,
        "level_since": level_since.isoformat() if level_since else None,
        "level_changed": level_changed,
        "level_override": override,
        "level_reason": _level_reason(runs_per_week, longest),
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
        "user_request": bool(user_request),
        "week_cap_min": cap,
        "easy_runs_with_hr": len(with_hr),
        "runs_above_z2": too_hard,
        "rhr_up": rhr_up,
        "vo2max": _number(profile.get("vo2max_running")),
        "adherence": adherence,
        "done": done,
        "shortened": shortened,
        "pain": bool(pain),
        "decision": decision,
        "goal_distance": profile.get("target_distance"),
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

    Początkujący (także po powrocie od przerwy) nie dostaje mocnych akcentów w ogóle,
    niezależnie od ustawienia w kreatorze. Brak ustawienia znaczy jeden trening.
    """
    if (runner or {}).get("level") == "poczatkujacy":
        return 0
    if configured is None:
        return 1
    try:
        return max(int(configured), 0)
    except (TypeError, ValueError):
        return 1


_CAUSE_TEXT = {
    "step_back": "Trzy tygodnie z rzędu rosła objętość — czas na lżejszy tydzień, żeby ciało się dostosowało.",
    "race_week": "To tydzień startu: mniej biegania, żeby być świeżym.",
    "taper": "Zbliża się start — objętość już nie rośnie, żeby dotrzeć do niego wypoczętym.",
    "after_race": "Po starcie potrzebny jest lekki tydzień na regenerację.",
    "stabilise": "Poprzedni tydzień był wyraźnie lżejszy — najpierw wracasz do zwykłej objętości.",
}


def decision_reason(runner: dict) -> str:
    """Powód decyzji tygodnia prostym językiem — te same warunki, co w build_runner_profile."""
    decision, adherence = runner.get("decision"), runner.get("adherence")
    if runner.get("comeback") or decision == "odbuduj":
        return "Wracasz do objętości z wcześniejszych tygodni — tydzień może być trochę dłuższy niż ostatni."
    if runner.get("decision_cause") in _CAUSE_TEXT:
        return _CAUSE_TEXT[runner["decision_cause"]]
    if decision in LIGHT_DECISIONS:
        if runner.get("pain"):
            return "W dzienniku z ostatnich dni jest ból."
        if (runner.get("rhr_up") or 0) >= 5:
            return f"Tętno spoczynkowe jest o {runner['rhr_up']} bpm wyższe niż zwykle — to znak zmęczenia."
        return "Wykonano mniej niż 60% zaplanowanych treningów, a część z nich wyszła wyraźnie krótsza."
    if decision == "utrzymaj":
        if adherence is None:
            return "Za mało danych o wykonaniu planu, żeby dokładać."
        if adherence < 0.9:
            return "Nie wszystkie zaplanowane treningi zostały wykonane."
        if runner.get("returning"):
            return "Wracasz po dłuższej przerwie — najpierw regularność."
        return "Spokojne biegi wychodzą za mocno: tętno często powyżej strefy 2."
    return "Plan wykonany, a pomiary nie pokazują zmęczenia."


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
    lines.append(f"- DECYZJA TYGODNIA: {DECISION_LABELS[runner['decision']]}")
    limits = []
    if runner["longest_min"]:
        limits.append(f"długi bieg najwyżej {runner['longest_min'] + long_run_step(runner)} min, "
                      f"bieg łatwy i akcent najwyżej {runner['longest_min']} min")
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
