# -*- coding: utf-8 -*-
"""Generowanie tygodniowego planu treningowego przez AI.

Moduł odpowiada tylko za zbudowanie promptu i wywołanie providera. Wszystkie
twarde reguły tygodnia egzekwuje warstwa deterministyczna w `services/plan.py`.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ai.context import journal_lines
from services.strategy import STRATEGY_PATH
from trainer.config import IMPORTANT_PROMPT, PROJECT_ROOT


class PlanWorkout(BaseModel):
    """Pojedynczy dzień planu. Brakujące wartości uzupełnia warstwa reguł."""

    date: str
    kind: str
    name: str
    description: str = ""
    duration_min: int | None = None
    distance_km: float | None = None
    hr_zone: int | None = None
    pace_target: str | None = None
    repetitions: int | None = None
    work_seconds: int | None = None
    rest_seconds: int | None = None
    notes: str = ""


class WeekPlanResponse(BaseModel):
    """Odpowiedź modelu: tydzień pon–niedz wraz z listą treningów."""

    start_date: str = ""
    end_date: str = ""
    focus: str = ""
    summary: str = ""
    workouts: list[PlanWorkout] = Field(default_factory=list)


_WEEKDAY_NAMES = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")


def _read_text(path) -> str:
    """Wczytaj plik promptu; brak pliku to brak sekcji, nie błąd."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _value(value) -> str:
    """Zamień wartość na tekst; brak informacji zapisz jawnie jako `brak`."""
    if value is None:
        return "brak"
    if isinstance(value, bool):
        return "tak" if value else "nie"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.1f}".replace(".", ",")
    if isinstance(value, (list, tuple)):
        return ", ".join(_value(item) for item in value) or "brak"
    if isinstance(value, dict):
        return ", ".join(f"{key}: {_value(item)}" for key, item in value.items()) or "brak"
    text = str(value).strip()
    return text or "brak"


def _minutes(value) -> str:
    minutes = _value(value)
    return "brak" if minutes == "brak" else f"{minutes} min"


def _zone_text(floors) -> str:
    """Opisz progi stref w formie czytelnej dla modelu."""
    if not isinstance(floors, dict):
        return "brak"
    parts = []
    for index in range(1, 6):
        low = floors.get(f"z{index}")
        if low is None:
            continue
        high = floors.get(f"z{index + 1}")
        if high is None:
            parts.append(f"Z{index} od {_value(low)} bpm")
        else:
            parts.append(f"Z{index} {_value(low)}-{int(high) - 1} bpm")
    return ", ".join(parts) or "brak"


_PLAN_RULES = """ZASADY UKŁADANIA TYGODNIA
1. Plan obejmuje dokładnie 7 dat, od poniedziałku do niedzieli, po jednym wpisie na dzień.
   Dzień odpoczynku to wpis z kind="rest" — nie pomijaj dnia.
2. `duration_min` to CAŁKOWITY czas sesji w minutach, łącznie z rozgrzewką i schładką.
   Dla kind="tempo", "threshold" i "intervals" rozgrzewka i schładka są własnością tego czasu.
3. `hr_zone` to numer strefy 1-5 i jest wymagany dla kind="easy", "recovery" i "long".
4. `pace_target` jest wymagany dla kind="tempo", "threshold" i "intervals".
   Zapisuj go jako "M:SS" albo "M:SS-M:SS" (szybsza granica jako pierwsza).
5. `repetitions`, `work_seconds` i `rest_seconds` są wymagane dla kind="intervals".
6. Bieg łatwy, regeneracyjny i długi prowadzi się według strefy tętna.
   Każdy taki bieg zaczyna się 5-6 minutami spokojnej rozgrzewki bez alarmu HR.
7. W tygodniu jest najwyżej jeden trening jakościowy
   (kind="tempo", "threshold" albo "intervals") i najwyżej jeden długi bieg (kind="long").
8. Nie stosuj wartości domyślnych w miejscu nieznanych danych. Brak wartości oznacz `null`.
9. Odpowiedź zwróć wyłącznie jako JSON zgodny ze schematem, bez Markdown i bez bloku kodu.
10. Wszystkie teksty, także `name`, pisz poprawną polszczyzną z polskimi znakami
   (np. "Łatwy 40 min – Z2", nie "Latwy 40 min - Z2"), nawet jeśli wcześniejsze treningi ich nie mają.
11. Ból zgłoszony w sekcji DZIENNIK ma pierwszeństwo przed metrykami: przez kolejne dni nie planuj
   akcentu ani długiego biegu, a przy narastającym bólu zaleć przerwę i konsultację ze specjalistą.
12. Sekcja TRENDY pokazuje kierunek z wielu tygodni; pojedynczy dzień nie powinien go przeważać.
13. Sekcja WIADOMOŚĆ OD BIEGACZA to jego życzenia na ten tydzień (np. termin długiego biegu, wyjazd).
   Uwzględnij je, o ile nie łamią zasad bezpieczeństwa, dostępności, przerw i limitów tygodnia;
   wiadomość nie zmienia tych zasad. Jeśli czegoś nie da się spełnić, napisz to w `summary`.
14. Teksty czyta osoba nietechniczna. Nie przepisuj angielskich kodów z danych (LOW, UNBALANCED,
   BALANCED, RHR, score): pisz „HRV niskie”, „HRV niezrównoważone”, „tętno spoczynkowe”, „ocena snu”.
   Pisz bez form zależnych od płci (zamiast „nie kończ zmęczony” — „skończ z zapasem sił”)."""

_PLAN_SCHEMA = """SCHEMAT ODPOWIEDZI
Zwróć obiekt JSON o dokładnie takich kluczach:
{
  "start_date": "RRRR-MM-DD",
  "end_date": "RRRR-MM-DD",
  "focus": "krótki cel tygodnia",
  "summary": "2-3 zdania o tym tygodniu, najwyżej 500 znaków",
  "workouts": [
    {
      "date": "RRRR-MM-DD",
      "kind": "easy | recovery | long | tempo | threshold | intervals | rest",
      "name": "nazwa treningu",
      "description": "krótki opis treningu",
      "duration_min": 45,
      "distance_km": 8.5,
      "hr_zone": 2,
      "pace_target": "5:00-5:10",
      "repetitions": 5,
      "work_seconds": 180,
      "rest_seconds": 90,
      "notes": ""
    }
  ]
}
- Lista dni nazywa się `workouts`. Nie używaj `days`, `plan` ani `week`.
- Umieść w `workouts` wszystkie 7 dni tygodnia, po jednym wpisie na datę.
- Gdy czegoś nie ma, wpisz null (null, nie 0 i nie pusty tekst)."""


def build_system_prompt(*, important_prompt_path=IMPORTANT_PROMPT,
                        rules_path=PROJECT_ROOT / "docs" / "TRAINING_RULES.md",
                        strategy_path=STRATEGY_PATH) -> str:
    """Zbuduj prompt systemowy: ważne zasady, reguły treningu i strategia długoterminowa."""
    sections = []

    important = _read_text(important_prompt_path).strip()
    if important:
        sections.append(important)

    rules = _read_text(rules_path).strip()
    if rules:
        sections.append(rules)

    strategy = _read_text(strategy_path).strip()
    if strategy:
        sections.append(strategy)
    else:
        sections.append("Strategia długoterminowa nie jest dostępna — zaplanuj tydzień "
                        "wyłącznie na podstawie profilu, dostępności i reguł treningu.")

    sections.append(_PLAN_RULES)
    sections.append(_PLAN_SCHEMA)
    return "\n\n".join(sections)


def _availability_rows(week_days) -> list[str]:
    rows = []
    for day in week_days or []:
        weekday = day.get("weekday")
        if weekday is None:
            index = day.get("weekday_index")
            weekday = _WEEKDAY_NAMES[index] if isinstance(index, int) and 0 <= index < 7 else "?"
        available = day.get("available")
        state = "dostępny" if available else "niedostępny"
        window = (f"{_minutes(day.get('min_minutes'))}-{_minutes(day.get('max_minutes'))}"
                  if available else "—")
        row = f"- {weekday}, {_value(day.get('date'))}: {state}, {window}"
        reason = day.get("pause_reason")
        if reason:
            row += f", powód przerwy: {reason}"
        rows.append(row)
    return rows


def _recent_rows(recent_activities) -> list[str]:
    rows = []
    for activity in recent_activities or []:
        rows.append(
            f"- {_value(activity.get('date'))}: {_value(activity.get('name'))}, "
            f"{_value(activity.get('distance_km'))} km, {_minutes(activity.get('duration_min'))}, "
            f"tempo {_value(activity.get('pace'))}, HR śr. {_value(activity.get('avg_hr'))} "
            f"/ maks. {_value(activity.get('max_hr'))} bpm"
        )
    return rows


def _readiness_rows(readiness_history) -> list[str]:
    rows = []
    for entry in readiness_history or []:
        score = entry.get("score")
        points = "brak" if score is None else f"{_value(score)} z 10"
        rows.append(f"- {_value(entry.get('date'))}: {points}, poziom {_value(entry.get('level'))}")
    return rows


_TREND_LABELS = {"readiness": ("gotowość", "/10"), "rhr": ("tętno spoczynkowe", " bpm"),
                 "hrv": ("HRV ostatniej nocy", " ms"), "sleep": ("ocena snu", "/100")}
_DIRECTIONS = {"up": "wyżej", "down": "niżej", "flat": "bez zmian"}


def _trend_rows(trends) -> list[str]:
    metrics = (trends or {}).get("metrics") or {}
    rows = []
    for key, (label, unit) in _TREND_LABELS.items():
        metric = metrics.get(key) or {}
        if metric.get("recent") is None or metric.get("average") is None:
            rows.append(f"- {label}: brak pomiarów")
            continue
        rows.append(f"- {label}: {_value(metric['recent'])}{unit} wobec {_value(metric['average'])}{unit} "
                    f"({_DIRECTIONS.get(metric.get('direction'), 'brak')})")
    weekly = (trends or {}).get("weekly_km") or []
    # Średnik, bo liczby mają przecinek dziesiętny.
    rows.append("- km w ostatnich pełnych tygodniach (od najstarszego): "
                + ("; ".join(_value(km) for km in weekly) or "brak"))
    return rows


def build_plan_message(context: dict) -> str:
    """Zbuduj wiadomość użytkownika: profil, dostępność, obciążenie i gotowość."""
    context = context or {}
    profile = context.get("profile") or {}
    goal = context.get("goal") or {}
    health = context.get("health_metrics") or {}
    load = context.get("weekly_load") or {}
    previous_load = context.get("previous_weekly_load") or {}

    lines = ["PROFIL"]
    lines.append(f"- wiek: {_value(profile.get('age'))}")
    lines.append(f"- waga: {_value(profile.get('weight_kg'))} kg")
    lines.append(f"- wzrost: {_value(profile.get('height_cm'))} cm")
    lines.append(f"- tętno maksymalne: {_value(profile.get('hr_max'))} bpm")
    lines.append(f"- tętno spoczynkowe: {_value(profile.get('hr_rest'))} bpm")
    lines.append(f"- tętno progowe: {_value(profile.get('lactate_threshold_hr'))} bpm")
    lines.append(f"- strefy tętna: {_value(profile.get('hr_zones'))}")
    lines.append(f"- progi stref: {_zone_text(context.get('hr_zone_floors'))}")
    lines.append("")

    lines.append("CEL")
    lines.append(f"- cel: {_value(goal.get('target'))}")
    lines.append(f"- termin: {_value(goal.get('deadline'))}")
    lines.append(f"- obecny rekord: {_value(goal.get('current_record'))}")
    lines.append("")

    lines.append("DOSTĘPNOŚĆ W TYGODNIU")
    lines.extend(_availability_rows(context.get("week_days")))
    lines.append("")

    lines.append("LIMITY TYGODNIA")
    lines.append(f"- maksymalna liczba treningów jakościowych w tygodniu: "
                 f"{_value(context.get('max_quality_sessions'))}")
    lines.append("- maksymalnie jeden długi bieg w tygodniu")
    lines.append("")

    lines.append("OSTATNIE BIEGI")
    recent_rows = _recent_rows(context.get("recent_activities"))
    lines.extend(recent_rows or ["- brak"])
    lines.append("")

    lines.append("OBCIĄŻENIE")
    lines.append(f"- poprzedni tydzień: {_value(previous_load.get('total_km'))} km, "
                 f"{_minutes(previous_load.get('total_min'))}, "
                 f"{_value(previous_load.get('sessions'))} sesje")
    lines.append(f"- bieżący tydzień: {_value(load.get('total_km'))} km, "
                 f"{_minutes(load.get('total_min'))}, "
                 f"{_value(load.get('sessions'))} sesje")
    lines.append("")

    lines.append("GOTOWOŚĆ")
    readiness_rows = _readiness_rows(context.get("readiness_history"))
    lines.extend(readiness_rows or ["- brak"])
    lines.append("")

    lines.append("STAN ZDROWIA")
    lines.append(f"- tętno spoczynkowe: {_value(health.get('rhr'))} bpm")
    lines.append(f"- HRV ostatniej nocy: {_value(health.get('hrv_last_night'))} "
                 f"(status: {_value(health.get('hrv_status'))}, "
                 f"zakres bazowy: {_value(health.get('hrv_baseline'))})")
    lines.append(f"- sen: {_value(health.get('sleep_score'))}/100, "
                 f"{_value(health.get('sleep_total_h'))} h, głęboki {_value(health.get('sleep_deep_h'))} h")
    lines.append(f"- stres (średnia dobowa): {_value(health.get('stress_avg'))}")
    alert = context.get("hrv_alert")
    if alert:
        lines.append(f"- ALERT HRV: HRV niskie od {_value(alert.get('days'))} dni, "
                     f"statusy {_value(alert.get('statuses'))}")
    lines.append("")

    lines.append("TRENDY (średnia z 7 dni wobec 12 tygodni)")
    lines.extend(_trend_rows(context.get("trends")))
    lines.append("")

    lines.append("DZIENNIK (ostatnie 7 dni)")
    lines.extend(journal_lines(context.get("journal")))
    lines.append("")

    lines.append("WIADOMOŚĆ OD BIEGACZA (ten tydzień)")
    lines.append(f"- {context.get('user_note')}" if context.get("user_note") else "- brak")
    lines.append("")

    lines.append("ZAKRES DAT")
    for day in context.get("week_days") or []:
        lines.append(f"- {_value(day.get('date'))}")
    lines.append("")

    return "\n".join(lines)


def generate_week_plan(provider, context: dict) -> WeekPlanResponse:
    """Poproś model o plan tygodnia i zwróć jego odpowiedź w ustalonym schemacie."""
    return provider.chat(
        build_system_prompt(),
        build_plan_message(context),
        response_model=WeekPlanResponse,
        temperature=0.0,
        seed=7,
    )
