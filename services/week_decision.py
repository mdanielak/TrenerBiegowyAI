# -*- coding: utf-8 -*-
"""Decyzja tygodnia: pięć stopni, limity minut tygodnia i długiego biegu, taper i powody prostym językiem.

Czysta logika liczb (bez danych z zegarka w surowej postaci). Profil biegacza (``services.runner_profile``)
zbiera dane i woła te funkcje; te same liczby trafiają do promptu (LIMITY APLIKACJI) i do bezpieczników planu.
Uzasadnienie progów: ``docs/wiedza-trenerska.md``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


DECISION_LABELS = {
    "regeneracja": "regeneracja — bardzo lekki tydzień (około 60% zwykłego tygodnia), tylko spokojne krótkie biegi",
    "odpusc": "odpuść — wyraźnie lżejszy tydzień (około 75% zwykłego tygodnia z ostatniego czasu)",
    "utrzymaj": "utrzymaj — podobna objętość jak ostatnio (aplikacja dopuszcza najwyżej ok. 10% więcej)",
    "doloz": "dołóż — objętość może wzrosnąć o 5–10% (aplikacja dopuszcza najwyżej ok. 15%)",
    "odbuduj": "odbuduj — powrót do znanej objętości, tydzień może być do 25% dłuższy niż ostatni, "
               "ale nie dłuższy niż zwykły tydzień sprzed 5–12 tygodni",
}
# Dwa lekkie stopnie: bez zapasu na prośbę biegacza i bez „nie niżej niż ostatni tydzień”.
LIGHT_DECISIONS = ("regeneracja", "odpusc")
# Powody lekkiego tygodnia, które oznaczają zmęczenie albo regenerację: wtedy bez akcentów (prompt: „zero u zmęczonych”).
# Taper i planowy tydzień cofnięcia to nie zmęczenie — tam jeden akcent zostaje.
FATIGUE_CAUSES = ("pain", "rhr_high", "rhr_up", "struggling", "hrv_rhr", "after_race")
# Długi bieg w lekkim tygodniu: część najdłuższego niedawnego biegu (zamiast wzrostu).
LIGHT_LONG_RUN = {"regeneracja": 0.6, "odpusc": 0.75, "step_back": 0.8}
AFTER_RACE_EASY_MAX = 45  # tydzień po starcie: krótkie spokojne biegi, długi bieg też nie dłuższy
# Tydzień startu na krótkim dystansie: długi bieg najwyżej tę część najdłuższego niedawnego (świeże nogi na start).
RACE_WEEK_LONG_RUN = {"5k": 0.55, "10k": 0.6}
SHORT_RACES = ("5k", "10k")
# Taper przed startem (Bosquet 2007, przegląd 2023): około 2 tygodni, objętość w dół o 41–60%, intensywność
# i częstotliwość bez zmian. Tydzień przed startem ok. 80% zwykłego tygodnia, tydzień startu ok. 55%.
# Część tygodnia zwykłego w kolejnych tygodniach przed startem (indeks 0 = tydzień startu), zależnie od dystansu:
# krótki start potrzebuje krótkiego tapera, maraton trzech tygodni. Tydzień przed taperem: „utrzymaj” (bez wzrostu).
TAPER_WEEKS = {"5k": (0.75,), "10k": (0.65, 0.85), "hm": (0.55, 0.8), "marathon": (0.5, 0.7, 0.85)}
TAPER_DEFAULT = TAPER_WEEKS["hm"]
# Po starcie: tyle dni lżej (po maratonie dłużej, a pierwszy tydzień to regeneracja).
AFTER_RACE_DAYS = {"marathon": 14}
CAUSE_LABELS = {
    "after_short_race": "utrzymaj po krótkim starcie — pierwsze 2–3 dni tylko spokojnie, potem zwykły tydzień; "
                        "najwyżej jeden akcent, najwcześniej trzeciego dnia po starcie",
    "step_back": "tydzień cofnięcia — około 75% zwykłego tygodnia po trzech tygodniach wzrostu; to planowa przerwa "
                 "w budowaniu, nie zmęczenie: spokojne biegi i najwyżej jeden krótszy, lżejszy akcent",
    "taper": "odpuść przed startem — {taper}; mniej objętości, ale intensywność zostaje: "
             "krótki akcent w tempie startowym, bez nowych bodźców",
    "race_week": "tydzień startu — {taper}; krótkie spokojne biegi i jeden krótki trening "
                 "z kilkoma żywymi odcinkami, bez wyczerpujących jednostek",
}
# Twardy sufit, nie cel: mnożnik zwykłego tygodnia (week_reference), którego plan nie przekroczy.
# Cel opisują DECISION_LABELS (utrzymaj = podobnie jak ostatnio, czyli 1,0); sufit to tylko zapas.
WEEK_LIMIT = {"regeneracja": 0.6, "odpusc": 0.75, "utrzymaj": 1.1, "doloz": 1.15, "odbuduj": 1.15}
# Gdy biegacz zostawił trenerowi wiadomość na tydzień (np. „wydłuż niedzielę”), sufit tygodnia rośnie o tyle
# (a długi bieg może urosnąć o LONG_RUN_REQUEST_GROWTH zamiast LONG_RUN_GROWTH). Nie dotyczy „odpuść”
# (ból, zmęczenie, wiele opuszczonych treningów).
WEEK_REQUEST_LIMIT = 1.2
# Tydzień nigdy nie przekracza tylu średnich z czterech tygodni: chroni przed skokiem obciążenia
# zaraz po wyjątkowo dużym tygodniu.
WEEK_SPIKE_LIMIT = 1.3
# Powrót do objętości sprzed 5–12 tygodni: tydzień może urosnąć o tyle wobec ostatniego, ale nie ponad
# tamten zwykły tydzień. Znane już obciążenie odbudowuje się szybciej niż nowe.
COMEBACK_STEP = 1.25
EARLIER_MIN_WEEKS = 6  # z 8: dopiero regularne bieganie to wcześniejsza objętość
# HRV: tygodniowa średnia z zegarka poniżej zakresu tej osoby. Sama nie zmienia tygodnia na lżejszy (pojedyncza metryka),
# tylko blokuje dokładanie; razem z tętnem spoczynkowym wyższym o tyle bpm — lżejszy tydzień.
HRV_WITH_RHR_BPM = 3
HRV_FRESH_DAYS = 3
# Długi bieg najwyżej tyle minut dłuższy niż najdłuższy niedawny bieg; łatwy nie dłuższy niż on.
# Długi bieg najwyżej o tyle dłuższy niż najdłuższy niedawny (BJSM 2025: ryzyko rośnie przy skoku ponad ok. 10%),
# ale co najmniej o LONG_RUN_MIN_STEP minut, żeby krótkie biegi w ogóle mogły rosnąć.
LONG_RUN_GROWTH = 1.10
LONG_RUN_REQUEST_GROWTH = 1.15  # przy wiadomości od biegacza (nie dotyczy lekkich stopni)
LONG_RUN_MIN_STEP = 5
# Twardy sufit długiego biegu (moduł maratonu: „nigdy powyżej 3 godzin”); dłuższy bieg już zrobiony nie jest skracany.
LONG_RUN_MAX_MIN = 180


def long_run_limit(runner, longest) -> int:
    """Najdłuższy dozwolony długi bieg: +10% najdłuższego niedawnego (przy prośbie biegacza +15%), min. +5 min.

    W lekkim tygodniu długi bieg nie rośnie, tylko się skraca: w taperze do tej części najdłuższego biegu,
    co objętość tygodnia, po tygodniu cofnięcia do 80%, w „odpuść” do 75%, w regeneracji do 60%.
    """
    runner = runner or {}
    if runner.get("decision_cause") == "after_race":
        return min(AFTER_RACE_EASY_MAX, round(longest * LIGHT_LONG_RUN["regeneracja"]))
    if runner.get("taper_percent"):
        share = runner["taper_percent"] / 100
        if runner.get("decision_cause") == "race_week":
            share = min(share, RACE_WEEK_LONG_RUN.get(runner.get("goal_distance"), 1.0))
        return round(longest * share)
    if runner.get("decision_cause") == "step_back":
        return round(longest * LIGHT_LONG_RUN["step_back"])
    if runner.get("decision") in LIGHT_DECISIONS:
        return round(longest * LIGHT_LONG_RUN[runner["decision"]])
    asked = runner.get("user_request") and runner.get("decision") not in LIGHT_DECISIONS
    growth = LONG_RUN_REQUEST_GROWTH if asked else LONG_RUN_GROWTH
    limit = max(round(longest * growth), longest + LONG_RUN_MIN_STEP)
    return max(min(limit, LONG_RUN_MAX_MIN), min(longest, limit))


def easy_run_limit(runner, longest) -> int:
    """Najdłuższy bieg łatwy i akcent: najdłuższy niedawny bieg, a w lekkim tygodniu i w taperze nie dłużej
    niż długi bieg (bieg łatwy nie może obejść skrócenia długiego biegu); po starcie najwyżej 45 min."""
    runner = runner or {}
    limit = longest
    if runner.get("taper_percent") or runner.get("decision") in LIGHT_DECISIONS:
        limit = min(limit, long_run_limit(runner, longest))
    if runner.get("decision_cause") == "after_race":
        limit = min(limit, AFTER_RACE_EASY_MAX)
    return limit


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


def _hrv_low(hrv, today: date) -> tuple[bool, dict | None]:
    """Czy tygodniowa średnia HRV jest poniżej zakresu bazowego (albo Garmin ocenia ją jako niską)."""
    entries = [e for e in hrv or [] if isinstance(e, dict) and e.get("date")]
    if not entries:
        return False, None
    latest = max(entries, key=lambda e: str(e["date"]))
    try:
        age = (today - date.fromisoformat(str(latest["date"])[:10])).days
    except ValueError:
        return False, None
    if age > HRV_FRESH_DAYS:
        return False, None
    weekly, low = _number(latest.get("weekly_avg")), _number(latest.get("baseline_low"))
    status = str(latest.get("status") or "").upper()
    below = (weekly is not None and low is not None and weekly < low) or status in ("LOW", "POOR")
    whole = lambda number: round(number) if number is not None else None  # noqa: E731 - ms bez części dziesiętnej
    return below, {"weekly_avg": whole(weekly), "baseline_low": whole(low),
                   "baseline_high": whole(_number(latest.get("baseline_high")))}


def _race_days(target_date, today: date) -> int | None:
    """Ile dni do startu (ujemnie: dni po starcie); None bez daty celu."""
    try:
        return (date.fromisoformat(str(target_date or "")[:10]) - today).days
    except ValueError:
        return None


_CAUSE_TEXT = {
    "step_back": "Trzy tygodnie z rzędu rosła objętość — czas na lżejszy tydzień, żeby ciało się dostosowało.",
    "race_week": "To tydzień startu: mniej biegania, {taper}; krótkie żywe odcinki zostają, "
                 "żeby być świeżym.",
    "taper": "Coraz bliżej startu: objętość spada do {taper}, a intensywność zostaje — "
             "tak forma rośnie najlepiej.",
    "before_taper": "Za tydzień zaczyna się zmniejszanie objętości przed startem — ten tydzień objętość jak ostatnio.",
    "short_history": "Zegarek ma dopiero kilka dni Twoich biegów — na razie objętość jak dotąd, aż zobaczy pełne tygodnie.",
    "hrv_rhr": "HRV jest poniżej Twojego zakresu, a tętno spoczynkowe wyższe niż zwykle — organizm prosi o lżejszy tydzień.",
    "hrv_low": "HRV jest poniżej Twojego zakresu — ten tydzień objętość jak ostatnio, bez wzrostu.",
    "after_race": "Po starcie potrzebny jest lżejszy czas na regenerację (po maratonie dwa tygodnie).",
    "after_short_race": "Po starcie na krótkim dystansie: 2–3 spokojne dni, akcent najwcześniej trzeciego dnia, "
                        "objętość jak ostatnio.",
    "stabilise": "Poprzedni tydzień był wyraźnie lżejszy — najpierw wracasz do zwykłej objętości.",
}


def _taper_phrase(runner) -> str:
    """„około 70% zwykłego tygodnia (ok. 320 min)” — liczba minut daje modelowi konkretny cel, nie tylko sufit."""
    runner = runner or {}
    percent, reference = runner.get("taper_percent"), runner.get("week_reference_min")
    if not percent:
        return "wyraźnie mniej niż zwykle"
    if not reference:
        return f"około {percent}% zwykłego tygodnia"
    target, floor = (round(reference * share / 100 / 5) * 5 for share in (percent, percent - 15))
    return f"około {percent}% zwykłego tygodnia (ok. {target} min, nie mniej niż ok. {floor} min)"


def decision_reason(runner: dict) -> str:
    """Powód decyzji tygodnia prostym językiem — te same warunki, co w build_runner_profile."""
    decision, adherence = runner.get("decision"), runner.get("adherence")
    if runner.get("comeback") or decision == "odbuduj":
        return "Wracasz do objętości z wcześniejszych tygodni — tydzień może być trochę dłuższy niż ostatni."
    if runner.get("decision_cause") in _CAUSE_TEXT:
        return _CAUSE_TEXT[runner["decision_cause"]].format(taper=_taper_phrase(runner))
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



@dataclass(frozen=True)
class WeekDecision:
    """Stopień tygodnia, jego powód (klucz do tekstów) i taper przed startem."""

    decision: str
    cause: str
    taper_factor: float | None  # część zwykłego tygodnia w taperze; None poza nim
    taper: bool  # taper albo tydzień tuż przed nim (wtedy bez wzrostu i bez szybkiego powrotu)


def decide_week(*, pain, rhr_up, struggling, hrv_low, adherence, returning, hr_too_high, short_history,
                week_minutes, race_days, goal) -> WeekDecision:
    """Jedna decyzja tygodnia z sygnałów; kolejność warunków to hierarchia: zdrowie > start > rytm > wykonanie.

    Szybki powrót do znanej objętości („odbuduj”) i krótka historia z zegarka dochodzą później,
    bo zależą od limitu minut (``week_cap``).
    """
    taper_weeks = TAPER_WEEKS.get(goal, TAPER_DEFAULT)
    weeks_before = race_days // 7 if race_days is not None and race_days >= 0 else None
    taper_factor = taper_weeks[weeks_before] if weeks_before is not None and weeks_before < len(taper_weeks) else None
    taper = weeks_before is not None and weeks_before <= len(taper_weeks)
    after_race = AFTER_RACE_DAYS.get(goal, 7)
    if pain:
        decision, cause = "regeneracja", "pain"
    elif rhr_up is not None and rhr_up >= RHR_REGENERATION_BPM:
        decision, cause = "regeneracja", "rhr_high"
    elif rhr_up is not None and rhr_up >= 5:
        decision, cause = "odpusc", "rhr_up"
    elif struggling:
        decision, cause = "odpusc", "struggling"
    elif hrv_low and rhr_up is not None and rhr_up >= HRV_WITH_RHR_BPM:
        decision, cause = "odpusc", "hrv_rhr"
    elif taper_factor is not None:
        decision, cause = "odpusc", ("race_week" if weeks_before == 0 else "taper")
    elif race_days is not None and -7 < race_days < 0 and goal in SHORT_RACES:
        # Po 5 i 10 km wystarczą 2–3 spokojne dni: tydzień bez wzrostu, jeden akcent najwcześniej w 3. dniu.
        decision, cause = "utrzymaj", "after_short_race"
    elif race_days is not None and -after_race < race_days < 0:
        # Po maratonie pierwszy tydzień to regeneracja, drugi lżejszy; po półmaratonie jeden lżejszy tydzień.
        decision, cause = ("regeneracja" if after_race > 7 and race_days > -7 else "odpusc"), "after_race"
    elif not short_history and _rising_weeks(week_minutes):
        decision, cause = "odpusc", "step_back"
    elif adherence is None or adherence < 0.9 or returning or hr_too_high:
        decision, cause = "utrzymaj", "low_adherence"
    elif hrv_low:
        decision, cause = "utrzymaj", "hrv_low"
    elif taper:
        decision, cause = "utrzymaj", "before_taper"
    elif not short_history and _after_light_week(week_minutes):
        decision, cause = "utrzymaj", "stabilise"
    else:
        decision, cause = "doloz", "ready"
    return WeekDecision(decision, cause, taper_factor, taper)
