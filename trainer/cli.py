"""Cienka warstwa CLI delegująca do istniejących modułów aplikacji."""
from __future__ import annotations

import argparse
import sys
from datetime import date

from . import __version__


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('wymagana dodatnia liczba całkowita') from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError('wymagana dodatnia liczba całkowita')
    return parsed


def iso_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('wymagana data ISO RRRR-MM-DD') from error
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='trainer', description='Narzędzia Trener Biegowy AI')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True)
    sync = commands.add_parser('sync', help='synchronizuje dane Garmin')
    sync.add_argument('--fresh', action='store_true', help='pełna synchronizacja')
    analyze = commands.add_parser('analyze', help='analizuje gotowość')
    analyze.add_argument('--ai', action='store_true', help='dołącz rekomendację AI')
    workouts = commands.add_parser('workouts', help='zarządza treningami Garmin')
    workout_commands = workouts.add_subparsers(dest='workout_command', required=True)
    usage = workout_commands.add_parser('usage', help='odświeża użycie treningów')
    usage.add_argument('--delete', action='store_true', help='usuń nieużywane treningi')
    create = workout_commands.add_parser('create', help='tworzy trening')
    kinds = create.add_subparsers(dest='kind', required=True)

    def add_kind(kind, fields):
        item = kinds.add_parser(kind)
        item.add_argument('name', help='nazwa treningu')
        for name, converter in fields:
            item.add_argument(name, type=converter)
    add_kind('easy', [('minutes', positive_int), ('date', iso_date)])
    add_kind('tempo', [('minutes', positive_int), ('pace_from', str), ('pace_to', str), ('date', iso_date)])
    add_kind('intervals', [('repeats', positive_int), ('work_seconds', positive_int), ('rest_seconds', positive_int), ('pace_from', str), ('pace_to', str), ('date', iso_date)])
    add_kind('long', [('minutes', positive_int), ('date', iso_date)])
    add_kind('strides', [('base_minutes', positive_int), ('repeats', positive_int), ('date', iso_date)])
    commands.add_parser('privacy-check', help='sprawdza ścieżki prywatnych danych')
    commands.add_parser('doctor', help='sprawdza lokalną konfigurację bez synchronizacji')
    return parser


def dispatch(args: argparse.Namespace) -> int:
    if args.command == 'sync':
        from .commands.sync import main as sync
        return sync(fresh=args.fresh) or 0
    if args.command == 'analyze':
        from .commands.analyze import main as analyze
        return analyze(use_ai=args.ai, strict_ai=True) or 0
    if args.command == 'privacy-check':
        from scripts.check_privacy import main as privacy_check
        return privacy_check()
    if args.command == 'doctor':
        from .doctor import main as doctor
        return doctor()
    if args.workout_command == 'usage':
        from .commands.workout_usage import main as usage
        return usage(delete=args.delete) or 0
    from .workouts import create_workout
    values = vars(args).copy()
    for key in ('command', 'workout_command', 'kind', 'name'):
        values.pop(key, None)
    create_workout(args.kind, args.name, **values)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return dispatch(args)
    except (ImportError, ModuleNotFoundError) as error:
        print(f'BŁĄD: brak zależności: {error}', file=sys.stderr)
        return 3
    except Exception as error:
        print(f'BŁĄD wykonania: {error}', file=sys.stderr)
        return 1
