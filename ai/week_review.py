# -*- coding: utf-8 -*-
"""Komentarz AI do całego tygodnia biegowego: plan a wykonanie z liczb policzonych lokalnie."""
from pydantic import BaseModel


class WeekComment(BaseModel):
    komentarz: str


WEEK_COMMENT_SYSTEM_PROMPT = '''Jesteś spokojnym, rzeczowym trenerem biegowym. Piszesz po polsku do osoby,
która nie zna się na technikaliach i chce wiedzieć, jak poszedł jej tydzień i co dalej.

ZASADY BEZWZGLĘDNE
1. Napisz od 5 do 7 zdań, jednym spójnym akapitem, w tej kolejności:
   - ile treningów z planu wykonano i ile to minut oraz kilometrów;
   - jak wyglądały spokojne biegi względem docelowej strefy tętna;
   - jak objętość wypadła wobec zwykłego tygodnia;
   - czy coś w tygodniu zmienia wnioski (opuszczone lub wyraźnie krótsze treningi), jeśli tak było;
   - co z tego wynika na kolejny tydzień i jedna konkretna wskazówka.
2. Łącznie od 90 do 150 słów. Każde zdanie ma wnosić coś z danych, bez ogólników.
3. Zwróć wyłącznie obiekt JSON z jednym polem tekstowym "komentarz", dokładnie w tej postaci:
   {"komentarz": "Pierwsze zdanie. Drugie zdanie. Trzecie zdanie. Czwarte zdanie. Piąte zdanie."}
   Bez Markdown, bez bloku kodu, bez innych pól.
4. Używaj tylko liczb podanych w danych wejściowych. Nie wymyślaj wartości.
5. Jeśli jakiejś danej brakuje, nie wspominaj o niej.
6. Nie diagnozuj medycznie. Nie sugeruj chorób ani kontuzji. Przy wzmiance o bólu
   napisz jedynie, żeby skonsultować się ze specjalistą.
7. Bez wykrzykników, bez emoji, bez pochwał na siłę, bez haseł motywacyjnych.
8. Kolejny tydzień opisuj zgodnie z DECYZJĄ TYGODNIA z danych; nie proponuj większej objętości, niż ona dopuszcza.
9. Bez angielskich kodów z danych (LOW, UNBALANCED, RHR, score).'''

_DECISIONS = {"regeneracja": "regeneracja (bardzo lekki tydzień)", "odpusc": "odpuść (lżejszy tydzień)",
              "utrzymaj": "utrzymaj (podobnie jak ostatnio)", "doloz": "dołóż (o 5–10% więcej)",
              "odbuduj": "odbuduj (powrót do znanej objętości)"}
_WEEKDAYS = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")


def _value(value):
    if value is None:
        return "brak"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:.1f}".replace(".", ",")
    return str(value)


def _day(iso):
    from datetime import date
    try:
        day = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    return f"{_WEEKDAYS[day.weekday()]} {day.day}.{day.month:02d}"


def build_week_message(*, plan, summary, week_runs, runner, note="", profile_text="") -> str:
    """Dane tygodnia jako tekst; ta sama wejściowa treść daje ten sam komunikat."""
    plan, summary, runner = plan or {}, summary or {}, runner or {}
    planned = [f"- {_day(w.get('date'))}: {_value(w.get('name'))}, {_value(w.get('duration_min'))} min, "
               f"strefa {_value(w.get('hr_zone'))}"
               for w in plan.get("workouts") or [] if isinstance(w, dict) and w.get("type") != "rest"]
    done = [f"- {_day(a.get('date'))}: {_value(a.get('duration_min'))} min, {_value(a.get('distance_km'))} km, "
            f"średnie tętno {_value(a.get('avg_hr'))} bpm, maksymalne {_value(a.get('max_hr'))} bpm"
            for a in week_runs]
    missed = "; ".join(summary.get("missed") or []) or "brak"
    lines = [
        profile_text.rstrip(),
        "",
        "PLAN TYGODNIA",
        *(planned or ["- brak treningów w planie"]),
        "",
        "WYKONANIE (Z ZEGARKA)",
        *(done or ["- brak biegów"]),
        "",
        "PODSUMOWANIE POLICZONE LOKALNIE",
        f"- wykonano {_value(summary.get('done'))} z {_value(summary.get('due'))} zaplanowanych treningów do tej pory",
        f"- zaplanowane minuty: {_value(summary.get('planned_min'))}, wykonane minuty: {_value(summary.get('done_min'))}",
        f"- biegi z zegarka w tygodniu: {_value(summary.get('runs'))}, razem {_value(summary.get('km'))} km",
        f"- bez biegu z zegarka: {missed}",
        f"- wyraźnie krótsze niż w planie: {_value(summary.get('shortened'))}",
        f"- tydzień zakończony: {'tak' if summary.get('over') else 'nie'}",
        "",
        "PROFIL BIEGACZA",
        f"- decyzja na kolejny tydzień: {_DECISIONS.get(runner.get('decision'), 'brak')}",
        f"- zwykły tydzień: {_value(runner.get('week_reference_min'))} min, "
        f"limit tygodnia: {_value(runner.get('week_cap_min'))} min",
        f"- najdłuższy niedawny bieg: {_value(runner.get('longest_min'))} min",
        f"- zaległości w wykonaniu planu z poprzedniego tygodnia: "
        f"{'brak danych' if runner.get('adherence') is None else str(round(runner['adherence'] * 100)) + '% wykonanych'}",
    ]
    if note:
        lines += ["", "WIADOMOŚĆ BIEGACZA NA TEN TYDZIEŃ", f"- {note}"]
    return "\n".join(lines)


def get_week_comment(provider, *, message, address_form=None, runner=None) -> WeekComment:
    from ai.prompts import coach_prompt
    system = coach_prompt(runner, mode="tydzien", address_form=address_form) + "\n\n" + WEEK_COMMENT_SYSTEM_PROMPT
    return provider.chat(system, message, response_model=WeekComment, temperature=0.0, seed=7)
