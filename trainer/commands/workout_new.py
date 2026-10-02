"""Interaktywny kreator treningu Garmin."""
from __future__ import annotations
import sys
from datetime import date
from typing import Any

def _ask(text, default=""):
    value = input(f"{text}" + (f" [{default}]" if default != "" else "") + ": ").strip()
    return value or str(default)
def _positive(text, default, maximum=None):
    while True:
        try:
            value = int(_ask(text, default))
            if value > 0 and (maximum is None or value <= maximum): return value
        except ValueError: pass
        print("Podaj dodatnią liczbę całkowitą" + (f" do {maximum}" if maximum else "") + ".")
def _pace(text, default):
    while True:
        value = _ask(text, default)
        try:
            minute, second = map(int, value.split(":"))
            if 2 <= minute <= 15 and 0 <= second < 60: return value
        except ValueError: pass
        print("Podaj tempo M:SS (od 2:00 do 15:59).")
def _date():
    while True:
        value = _ask("Data (RRRR-MM-DD)", date.today().isoformat())
        try:
            if date.fromisoformat(value) >= date.today(): return value
        except ValueError: pass
        print("Podaj dzisiejszą lub przyszłą datę RRRR-MM-DD.")
def main() -> int:
    if not sys.stdin.isatty(): print("Kreator wymaga interaktywnego terminala."); return 2
    kinds = {"1":"easy", "2":"tempo", "3":"intervals", "4":"long", "5":"strides", "6":"hr_zone_run", "7":"easy_run_zoned"}
    print("1 łatwy, 2 tempo, 3 interwały, 4 długi, 5 przebieżki, 6 strefa HR, 7 łatwy w strefie HR")
    while (choice := _ask("Wybierz rodzaj")) not in kinds: print("Wybierz numer 1–7.")
    kind, name, when = kinds[choice], _ask("Nazwa treningu", "Trening biegowy"), _date()
    kw: dict[str, Any] = {"date": when}
    if kind in {"easy", "long", "hr_zone_run"}: kw["minutes"] = _positive("Czas (min)", 45)
    if kind == "tempo": kw.update(minutes=_positive("Tempo (min)", 20), pace_from=_pace("Szybsze tempo", "5:00"), pace_to=_pace("Wolniejsze tempo", "5:15"))
    if kind == "intervals": kw.update(repeats=_positive("Powtórzenia", 5), work_seconds=_positive("Praca (s)", 180), rest_seconds=_positive("Przerwa (s)", 120), pace_from=_pace("Szybsze tempo", "5:00"), pace_to=_pace("Wolniejsze tempo", "5:15"))
    if kind == "strides": kw.update(base_minutes=_positive("Bieg bazowy (min)", 30), repeats=_positive("Przebieżki", 6))
    if kind == "hr_zone_run": kw["zone_number"] = _positive("Numer strefy HR", 2, 5)
    if kind == "easy_run_zoned": kw.update(main_minutes=_positive("Część główna (min)", 30), zone_number=_positive("Numer strefy HR", 2, 5))
    print("\nPodsumowanie:", name, kind, when, kw)
    if _ask("Utworzyć i zaplanować trening? (t/N)", "n").lower() not in {"t", "tak", "y", "yes"}:
        print("Nic nie utworzono."); return 0
    from ..workouts import create_workout
    create_workout(kind, name, **kw)
    return 0
