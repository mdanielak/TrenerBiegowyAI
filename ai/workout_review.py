# -*- coding: utf-8 -*-
"""Deterministyczny kontekst i komentarz AI do oceny treningu."""
from pydantic import BaseModel


class WorkoutComment(BaseModel):
    komentarz: str


WORKOUT_COMMENT_SYSTEM_PROMPT = '''Jesteś spokojnym, rzeczowym trenerem biegowym. Piszesz po polsku do osoby,
która nie zna się na technikaliach i chce wiedzieć, co dalej.

ZASADY BEZWZGLĘDNE
1. Napisz DOKŁADNIE dwa zdania. Pierwsze zdanie: co się stało na treningu,
   oparte na liczbach. Drugie zdanie: co z tego wynika na najbliższe dni.
2. Łącznie najwyżej 45 słów.
3. Zwróć wyłącznie JSON zgodny ze schematem. Bez Markdown, bez bloku kodu.
4. Używaj tylko liczb podanych w danych wejściowych. Nie wymyślaj wartości
   i nie zaokrąglaj inaczej, niż podano.
5. Jeśli jakiejś danej brakuje, nie wspominaj o niej. Wyjątkiem jest brak
   informacji o samym wykonaniu treningu.
6. Nie podawaj ocen punktowych cyfrą. Możesz odnieść się do nich słowem.
7. Nie diagnozuj medycznie. Nie sugeruj chorób ani kontuzji. Przy wzmiance
   o bólu napisz jedynie, żeby skonsultować się ze specjalistą.
8. Bez wykrzykników, bez emoji, bez pochwał na siłę, bez haseł motywacyjnych.
9. Nie zaczynaj od słów "Dzisiejszy trening" ani "Twój trening".
10. Bez angielskich kodów z danych (LOW, UNBALANCED, RHR, score) i bez form zależnych od płci.'''


def _value(value):
    if value is None or value == "None-None":
        return "brak"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.1f}".replace(".", ",")
    return str(value)


def _with_unit(value, unit):
    value = _value(value)
    return "brak" if value == "brak" else f"{value} {unit}"


def runner_text(profile) -> str:
    """Kto biega: cel i staż z profilu, żeby komentarz pasował do poziomu biegacza."""
    from services.runner_profile import RUNNING_SINCE_LABELS
    profile = profile or {}
    since = RUNNING_SINCE_LABELS.get(profile.get("running_since"), "brak")
    return f"BIEGACZ\n- cel: {_value(profile.get('target_race'))}\n- biega regularnie: {since}\n\n"


def build_comment_message(*, planned, execution, score, readiness, hr_zones_text, runner="") -> str:
    planned, execution, score, readiness = planned or {}, execution or {}, score or {}, readiness or {}
    spec = planned.get("spec") or {}
    band = score.get("zakres_docelowy")
    target_zone = score.get("strefa_docelowa")
    target = "brak" if target_zone is None or band is None else f"Z{_value(target_zone)} ({_value(band[0])}-{_value(band[1])} bpm)"
    match_method = execution.get("match_method")
    match = {"id": "po identyfikatorze", "heuristic": "heurystycznie", "ambiguous": "niejednoznacznie", "unmatched": "brak dopasowania"}.get(match_method, "brak") if isinstance(match_method, str) else "brak"
    happened = "tak" if execution.get("happened") is True else "nie"
    hrv = _value(readiness.get("hrv_last"))
    baseline = _value(readiness.get("hrv_baseline"))
    return runner + f'''ZAPLANOWANY TRENING
- nazwa: {_value(planned.get("name"))}
- zaplanowany czas: {_with_unit(spec.get("duration_min"), "min")}
- docelowa strefa: {target}

WYKONANIE
- czy sie odbylo: {happened}
- sposob dopasowania: {match}
- czas: {_with_unit(execution.get("duration_min"), "min")}
- dystans: {_with_unit(execution.get("distance_km"), "km")}
- srednie tetno: {_with_unit(execution.get("avg_hr"), "bpm")}
- maksymalne tetno: {_with_unit(execution.get("max_hr"), "bpm")}
- strefa wykonania: {_value(score.get("strefa_wykonania"))}

ROZNICE POLICZONE LOKALNIE
- odchylenie_czasu_proc: {_value(score.get("odchylenie_czasu_proc"))}
- odchylenie_tetna_bpm: {_value(score.get("odchylenie_tetna_bpm"))}
- uwaga: srednie tetno obejmuje takze rozgrzewke, dlatego dolna granica
  docelowego zakresu jest obnizona o 8 bpm przy liczeniu odchylenia

OCENY POLICZONE LOKALNIE
- zgodnosc_z_planem: {_value(score.get("zgodnosc_z_planem"))} z 10
- dopasowanie_do_formy: {_value(score.get("dopasowanie_do_formy"))} z 10
- pewnosc: {_value(score.get("pewnosc"))}

GOTOWOSC W DNIU TRENINGU
- gotowosc_punkty: {_value(readiness.get("score"))} z 10
- tetno spoczynkowe: {_with_unit(readiness.get("rhr"), "bpm")}
- HRV ostatniej nocy: {hrv}, zakres bazowy {baseline}, ocena zegarka: {_value(readiness.get("hrv_status"))}
- sen: {_value(readiness.get("sleep_score_val"))} z 100, dlugosc {_with_unit(readiness.get("sleep_total"), "h")}
- stres (srednia dobowa): {_value(readiness.get("stress"))}

STREFY TETNA BIEGACZA
- {_value(hr_zones_text)}'''


def get_workout_comment(provider, *, planned, execution, score, readiness, hr_zones_text,
                        runner="") -> WorkoutComment:
    message = build_comment_message(planned=planned, execution=execution, score=score,
                                    readiness=readiness, hr_zones_text=hr_zones_text, runner=runner)
    return provider.chat(WORKOUT_COMMENT_SYSTEM_PROMPT, message, response_model=WorkoutComment,
                         temperature=0.0, seed=7)
