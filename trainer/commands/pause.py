# -*- coding: utf-8 -*-
"""Zarządzanie planowanymi przerwami (np. zabiegi medyczne, choroba, wyjazdy)."""
from __future__ import annotations

import argparse
import sys
from datetime import date

from trainer.preferences import (
    add_planned_pause,
    get_active_pause,
    list_planned_pauses,
    remove_planned_pause,
)


def list_pauses() -> int:
    pauses = list_planned_pauses()
    today_str = date.today().isoformat()
    active = get_active_pause(today_str)

    if active:
        print(f"AKTYWNA PRZERWA DZIŚ: {active.get('reason')} ({active.get('start_date')} – {active.get('end_date')}) [typ: {active.get('type')}]")
        print()

    if not pauses:
        print("Brak zaplanowanych przerw treningowych.")
        print("Aby dodać przerwę: trainer pause add RRRR-MM-DD RRRR-MM-DD \"Powód\"")
        return 0

    print("ZAPLANOWANE PRZERWY TRENINGOWE:")
    for p in pauses:
        status = " (AKTYWNA)" if p.get("start_date") <= today_str <= p.get("end_date") else ""
        print(f"  • {p.get('start_date')} – {p.get('end_date')}: {p.get('reason')} [{p.get('type')}]{status}")
    return 0


def add_pause(start_date: str, end_date: str, reason: str, pause_type: str = "medical") -> int:
    try:
        entry = add_planned_pause(start_date, end_date, reason, pause_type)
        print(f"Dodano przerwę: {entry['reason']} ({entry['start_date']} – {entry['end_date']})")
        return 0
    except Exception as exc:
        print(f"BŁĄD: {exc}", file=sys.stderr)
        return 1


def remove_pause(start_date: str, end_date: str) -> int:
    success = remove_planned_pause(start_date, end_date)
    if success:
        print(f"Usunięto przerwę ({start_date} – {end_date}).")
        return 0
    print(f"Nie znaleziono przerwy o zakresie {start_date} – {end_date}.", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trainer pause", description="Zarządza planowanymi przerwami treningowymi")
    subparsers = parser.add_subparsers(dest="action")

    add_parser = subparsers.add_parser("add", help="dodaj planowaną przerwę")
    add_parser.add_argument("start_date", help="data rozpoczęcia (RRRR-MM-DD)")
    add_parser.add_argument("end_date", help="data zakończenia (RRRR-MM-DD)")
    add_parser.add_argument("reason", help="powód przerwy (np. przeziębienie, wyjazd)")
    add_parser.add_argument("--type", default="medical",
                            choices=["medical", "recovery", "vacation", "illness", "break"],
                            help="typ przerwy (domyślnie: medical)")

    remove_parser = subparsers.add_parser("remove", help="usuń planowaną przerwę")
    remove_parser.add_argument("start_date", help="data rozpoczęcia (RRRR-MM-DD)")
    remove_parser.add_argument("end_date", help="data zakończenia (RRRR-MM-DD)")

    args = parser.parse_args(argv)
    if args.action == "add":
        return add_pause(args.start_date, args.end_date, args.reason, args.type)
    if args.action == "remove":
        return remove_pause(args.start_date, args.end_date)
    return list_pauses()
