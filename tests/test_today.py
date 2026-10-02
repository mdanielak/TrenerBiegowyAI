from datetime import datetime

from trainer.commands import today
from services.data_extract import SnapshotReadResult, SnapshotStatus


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


def _run_today(monkeypatch, activities):
    data = {'daily_health': [], 'sleep': [], 'hrv': [], 'activities': activities}
    monkeypatch.setattr(today, 'datetime', _ClockAt20261002)
    monkeypatch.setattr(today, 'load_profile', lambda: {})
    monkeypatch.setattr(today, 'read_snapshot_status', lambda: SnapshotReadResult(SnapshotStatus.FRESH, data))
    monkeypatch.setattr(today, 'get_weekly_availability',
                        lambda _: {'available': False, 'min_minutes': 0, 'max_minutes': 0})
    monkeypatch.setattr(today, 'load_events', lambda: [])
    return today.main()


def test_missing_snapshot_is_friendly(monkeypatch, capsys):
    monkeypatch.setattr(today, 'load_profile', lambda: {})
    monkeypatch.setattr(today, 'read_snapshot_status', lambda: SnapshotReadResult(SnapshotStatus.MISSING))
    assert today.main() == 1
    assert 'sync' in capsys.readouterr().out


def test_stale_snapshot_warns(monkeypatch, capsys):
    data = {'daily_health': [], 'sleep': [], 'hrv': [], 'activities': []}
    monkeypatch.setattr(today, 'load_profile', lambda: {})
    monkeypatch.setattr(today, 'read_snapshot_status', lambda: SnapshotReadResult(SnapshotStatus.STALE, data))
    monkeypatch.setattr(today, 'get_weekly_availability', lambda _: {'available': False, 'min_minutes': 0, 'max_minutes': 0})
    monkeypatch.setattr(today, 'load_events', lambda: [])
    assert today.main() == 0
    assert 'nieaktualny' in capsys.readouterr().out


def test_missing_profile_points_to_setup(monkeypatch, capsys):
    monkeypatch.setattr(today, 'load_profile', lambda: (_ for _ in ()).throw(FileNotFoundError()))
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
