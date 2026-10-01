"""Read-only local diagnostics for the Trainer runtime."""
from __future__ import annotations

import importlib
import importlib.metadata
from pathlib import Path
import sqlite3
import sys
from typing import Callable
from urllib.parse import quote

from .config import HEALTH_DATA_DIR, resolve_database_dir


DEPENDENCY_FAILURE = 3
RUNTIME_FAILURE = 1


def _emit(output: Callable[[str], None], level: str, check: str, detail: str) -> None:
    """Emit a stable diagnostic line without paths, records, or secrets."""
    output(f'{level} {check}: {detail}')


def _garmindb_version(module: object) -> str:
    version = getattr(module, '__version__', None)
    return str(version) if version else importlib.metadata.version('garmindb')


def _check_dependencies(output: Callable[[str], None]) -> bool:
    failed = False
    for name, version_getter in (
        ('garmindb', _garmindb_version),
        ('garminconnect', lambda module: str(getattr(module, '__version__', 'available'))),
    ):
        try:
            module = importlib.import_module(name)
            version = version_getter(module)
        except (ImportError, ModuleNotFoundError, importlib.metadata.PackageNotFoundError):
            _emit(output, 'FAIL', name, 'dependency unavailable')
            failed = True
        else:
            _emit(output, 'OK', name, f'available ({version})')
    return failed


def _readonly_sqlite_uri(path: Path) -> str:
    return f'file:{quote(path.resolve().as_posix())}?mode=ro'


def _check_sqlite(path: Path) -> bool:
    """Open only in SQLite read-only mode and run a non-record integrity check."""
    try:
        with sqlite3.connect(_readonly_sqlite_uri(path), uri=True) as connection:
            result = connection.execute('PRAGMA quick_check').fetchone()
    except sqlite3.Error:
        return False
    return result == ('ok',)


def _snapshot_status():
    """Use the existing snapshot classifier without printing snapshot contents."""
    from services.data_extract import read_snapshot_status
    return read_snapshot_status()


def main(output: Callable[[str], None] = print) -> int:
    """Run local checks without synchronizing, authenticating, logging, or writing."""
    dependency_failed = False
    runtime_failed = False
    _emit(output, 'OK', 'interpreter', f'Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')
    dependency_failed = _check_dependencies(output)

    try:
        from services.data_extract import _find_garmindb_cli
        _find_garmindb_cli()
    except (ImportError, ModuleNotFoundError, FileNotFoundError):
        _emit(output, 'FAIL', 'garmindb-cli', 'unavailable')
        dependency_failed = True
    else:
        _emit(output, 'OK', 'garmindb-cli', 'available')

    health_data_dir = HEALTH_DATA_DIR
    _emit(output, 'OK', 'HEALTH_DATA_DIR', 'configured')

    db_directory = resolve_database_dir(health_data_dir)
    if health_data_dir.is_dir():
        _emit(output, 'OK', 'health-data-dir', 'directory exists')
        if db_directory.is_dir() and db_directory.name == 'DBs':
            _emit(output, 'OK', 'DBs', 'directory exists')
        elif db_directory.is_dir() and db_directory.name == 'dbs':
            _emit(output, 'WARN', 'DBs', 'using lowercase dbs directory')
        else:
            _emit(output, 'FAIL', 'DBs', 'directory missing')
            runtime_failed = True
    else:
        _emit(output, 'FAIL', 'health-data-dir', 'directory missing')
        runtime_failed = True

    for label, filename in (('ACT_DB', 'garmin_activities.db'), ('MAIN_DB', 'garmin.db')):
        database = db_directory / filename
        if not database.is_file():
            _emit(output, 'FAIL', label, 'database missing')
            runtime_failed = True
        elif _check_sqlite(database):
            _emit(output, 'OK', label, 'read-only quick_check ok')
        else:
            _emit(output, 'FAIL', label, 'not readable read-only or quick_check failed')
            runtime_failed = True

    try:
        snapshot = _snapshot_status()
        status = getattr(snapshot.status, 'value', str(snapshot.status))
    except (ImportError, ModuleNotFoundError):
        _emit(output, 'FAIL', 'snapshot', 'status reader unavailable')
        dependency_failed = True
    except Exception:
        _emit(output, 'FAIL', 'snapshot', 'status unreadable')
        runtime_failed = True
    else:
        if status == 'fresh':
            _emit(output, 'OK', 'snapshot', 'fresh')
        elif status == 'stale':
            _emit(output, 'WARN', 'snapshot', 'stale')
        elif status in {'missing', 'invalid'}:
            _emit(output, 'FAIL', 'snapshot', status)
            runtime_failed = True
        else:
            _emit(output, 'FAIL', 'snapshot', 'status invalid')
            runtime_failed = True

    if dependency_failed:
        return DEPENDENCY_FAILURE
    return RUNTIME_FAILURE if runtime_failed else 0
