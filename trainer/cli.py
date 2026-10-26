"""Cienka warstwa CLI delegująca do istniejących modułów aplikacji."""
from __future__ import annotations

import argparse
import sys
import traceback
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
    parser.add_argument('--debug', action='store_true', help='pokaż szczegóły błędu')
    commands = parser.add_subparsers(dest='command')
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
    commands.add_parser('setup', help='prowadzi przez pierwszą konfigurację')
    commands.add_parser('today', help='pokazuje plan i gotowość na dziś')
    zones = commands.add_parser('zones', help='pokazuje strefy tętna')
    zones.add_argument('--sync', action='store_true', help='pobierz strefy z Garmin Connect')
    profile = commands.add_parser('profile', help='pokazuje lokalny profil biegacza')
    profile.add_argument('--sync', action='store_true', help='pobierz profil z Garmin Connect')
    workout_commands.add_parser('new', help='interaktywnie tworzy trening')
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
    if args.command == 'setup':
        from .setup_wizard import main as setup
        return setup()
    if args.command == 'today':
        from .commands.today import main as today
        return today()
    if args.command == 'zones':
        from .commands.zones import main as zones
        return zones(sync=args.sync)
    if args.command == 'profile':
        from .commands.profile import main as profile
        return profile(sync=args.sync)
    if args.command == 'workouts' and args.workout_command == 'new':
        from .commands.workout_new import main as workout_new
        return workout_new()
    if args.workout_command == 'usage':
        from .commands.workout_usage import main as usage
        return usage(delete=args.delete) or 0
    from .workouts import create_workout
    values = vars(args).copy()
    for key in ('command', 'workout_command', 'kind', 'name', 'debug'):
        values.pop(key, None)
    create_workout(args.kind, args.name, **values)
    return 0


def _ensure_utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if callable(reconfigure):
            try:
                reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        print('\nZacznij od: python -m trainer setup')
        return 2
    try:
        return dispatch(args)
    except Exception as error:
        from .errors import describe_error
        advice = describe_error(error)
        print(f'BŁĄD: {advice.message}', file=sys.stderr)
        # Zachowujemy zwięzły szczegół zgodny z wcześniejszym CLI; porada poniżej
        # pozostaje bezpiecznie oczyszczona przez describe_error().
        if advice.exit_code == 1:
            print(f'BŁĄD wykonania: {error}', file=sys.stderr)
        print(advice.hint, file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        return advice.exit_code
