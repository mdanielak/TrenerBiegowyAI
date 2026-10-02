from datetime import datetime
import json

from trainer.commands import today
from services import today as today_service
from services.data_extract import SnapshotReadResult, SnapshotStatus
from services import workout_registry


class _ClockAt20261002(datetime):
    """Zamraża "dziś" na 2026-10-02, więc wczoraj to 2026-10-01."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 2, 8, 0)


_WALK = {'date': '2026-10-01 17:14', 'type': 'walking/generic', 'name': 'Wieliczka Chodzenie',
         'distance_km': 0.29, 'duration_min': 4.7, 'avg_hr': 135}
_RUN = {'date': '2026-10-01 16:28', 'type': 'running/generic', 'name': 'Wieliczka Z2',
        'distance_km': 6.07, 'duration_min': 45.0, 'avg_hr': 133}
_RUN_MORNING = {'date': '2026-10-01 07:05', 'type': 'running/generic', 'name': 'Rozbieganie',
                'distance_km': 8.0, 'duration_min': 50.0, 'avg_hr': 128}
_SWIM = {'date': '2026-10-01 19:00', 'type': 'swimming/lap_swimming', 'name': 'Basen',
         'distance_km': 1.2, 'duration_min': 35.0, 'avg_hr': 120}


def _yesterday_block(capsys):
    """Zwraca linię "Wczoraj" wraz z wciętymi liniami aktywności."""
    lines = capsys.readouterr().out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith('Wczoraj'))
    block = [lines[start]]
    for line in lines[start + 1:]:
        if not line.startswith('  '):
            break
        block.append(line)
    return block


def _run_today(monkeypatch, activities, registry_events=None, tmp_path=None):
    data = {'daily_health': [], 'sleep': [], 'hrv': [], 'activities': activities}
    monkeypatch.setattr(today_service, 'datetime', _ClockAt20261002)
    monkeypatch.setattr(today_service, 'load_profile', lambda: {})
    monkeypatch.setattr(today_service, 'read_snapshot_status', lambda: SnapshotReadResult(SnapshotStatus.FRESH, data))
    monkeypatch.setattr(today_service, 'get_weekly_availability',
                        lambda _: {'available': False, 'min_minutes': 0, 'max_minutes': 0})
    if registry_events is None:
        monkeypatch.setattr(today_service, 'list_workouts', lambda status: [])
    else:
        if tmp_path is None:
            raise ValueError('tmp_path is required with registry events')
        registry_path = tmp_path / 'workout-registry.jsonl'
        registry_path.write_text(
            ''.join(json.dumps(event) + '\n' for event in registry_events),
            encoding='utf-8',
        )
        monkeypatch.setattr(workout_registry, 'REGISTRY_PATH', registry_path)
        monkeypatch.setattr(today_service, 'list_workouts', workout_registry.list_workouts)
    return today.main()


def test_missing_snapshot_is_friendly(monkeypatch, capsys):
    monkeypatch.setattr(today_service, 'load_profile', lambda: {})
    monkeypatch.setattr(today_service, 'read_snapshot_status', lambda: SnapshotReadResult(SnapshotStatus.MISSING))
    assert today.main() == 1
    assert 'sync' in capsys.readouterr().out


def test_stale_snapshot_warns(monkeypatch, capsys):
    data = {'daily_health': [], 'sleep': [], 'hrv': [], 'activities': []}
    monkeypatch.setattr(today_service, 'load_profile', lambda: {})
    monkeypatch.setattr(today_service, 'read_snapshot_status', lambda: SnapshotReadResult(SnapshotStatus.STALE, data))
    monkeypatch.setattr(today_service, 'get_weekly_availability', lambda _: {'available': False, 'min_minutes': 0, 'max_minutes': 0})
    monkeypatch.setattr(today_service, 'list_workouts', lambda status: [])
    assert today.main() == 0
    assert 'nieaktualny' in capsys.readouterr().out


def test_missing_profile_points_to_setup(monkeypatch, capsys):
    monkeypatch.setattr(today_service, 'load_profile', lambda: (_ for _ in ()).throw(FileNotFoundError()))
    assert today.main() == 5
    assert 'setup' in capsys.readouterr().out


def test_yesterday_lists_run_and_trailing_walk(monkeypatch, capsys):
    """Spacer dopisany po biegu nie może ukryć treningu ani zniknąć sam."""
    assert _run_today(monkeypatch, [_WALK, _RUN]) == 0
    block = _yesterday_block(capsys)
    assert block[0] == 'Wczoraj (2 aktywności):'
    assert '16:28' in block[1] and 'Wieliczka Z2' in block[1] and '6.07' in block[1]
    assert '17:14' in block[2] and 'Chodzenie' in block[2]


def test_yesterday_lists_both_runs_of_a_double_day(monkeypatch, capsys):
    """Dwa biegi jednego dnia muszą być widoczne oba."""
    assert _run_today(monkeypatch, [_RUN, _RUN_MORNING]) == 0
    block = _yesterday_block(capsys)
    assert block[0] == 'Wczoraj (2 aktywności):'
    assert 'Rozbieganie' in block[1]
    assert 'Wieliczka Z2' in block[2]


def test_yesterday_lists_non_running_sports(monkeypatch, capsys):
    """Pływanie to też trening, więc nie wolno go pomijać obok biegu."""
    assert _run_today(monkeypatch, [_SWIM, _RUN]) == 0
    block = _yesterday_block(capsys)
    assert 'Wieliczka Z2' in block[1]
    assert 'Basen' in block[2]


def test_single_activity_stays_on_one_line(monkeypatch, capsys):
    """Najczęstszy przypadek zostaje zwarty, bez nagłówka i wcięć."""
    assert _run_today(monkeypatch, [_WALK]) == 0
    block = _yesterday_block(capsys)
    assert len(block) == 1
    assert block[0].startswith('Wczoraj: ')
    assert 'Chodzenie' in block[0]


def test_deleted_registry_workout_is_not_shown(monkeypatch, capsys, tmp_path):
    events = [
        {'event': 'added', 'workout_id': 'w1', 'name': 'Interwały',
         'date': '2026-10-02', 'spec': {'kind': 'intervals'}, 'ts': '2026-10-01T08:00:00'},
        {'event': 'deleted', 'workout_id': 'w1', 'ts': '2026-10-01T09:00:00'},
    ]

    assert _run_today(monkeypatch, [], events, tmp_path) == 0
    assert 'Plan z rejestru: brak' in capsys.readouterr().out


def test_updated_registry_workout_shows_current_data(monkeypatch, capsys, tmp_path):
    events = [
        {'event': 'added', 'workout_id': 'w1', 'name': 'Pierwotny trening',
         'date': '2026-10-02', 'spec': {'kind': 'easy'}, 'ts': '2026-10-01T08:00:00'},
        {'event': 'updated', 'workout_id': 'w1', 'name': 'Zaktualizowany trening',
         'date': '2026-10-02', 'ts': '2026-10-01T09:00:00'},
    ]

    assert _run_today(monkeypatch, [], events, tmp_path) == 0
    output = capsys.readouterr().out
    assert 'Plan z rejestru: Zaktualizowany trening (easy)' in output
    assert 'Pierwotny trening' not in output


def test_newest_active_registry_workout_is_shown_for_same_date(monkeypatch, capsys, tmp_path):
    events = [
        {'event': 'added', 'workout_id': 'older', 'name': 'Starszy trening',
         'date': '2026-10-02', 'spec': {'kind': 'easy'}, 'ts': '2026-10-01T08:00:00'},
        {'event': 'added', 'workout_id': 'newer', 'name': 'Nowszy trening',
         'date': '2026-10-02', 'spec': {'kind': 'tempo'}, 'ts': '2026-10-01T09:00:00'},
    ]

    assert _run_today(monkeypatch, [], events, tmp_path) == 0
    output = capsys.readouterr().out
    assert 'Plan z rejestru: Nowszy trening (tempo)' in output
    assert 'Starszy trening' not in output
