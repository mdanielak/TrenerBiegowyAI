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


def test_yesterday_prefers_run_over_later_walk(monkeypatch, capsys):
    """Spacer zapisany po biegu nie może podmienić treningu, choć jest nowszy."""
    assert _run_today(monkeypatch, [_WALK, _RUN]) == 0
    line = next(l for l in capsys.readouterr().out.splitlines() if l.startswith('Wczoraj:'))
    assert 'Wieliczka Z2' in line
    assert '6.07' in line
    assert 'Chodzenie' not in line


def test_yesterday_falls_back_to_walk_when_no_run(monkeypatch, capsys):
    """Bez biegu nadal pokazujemy to, co było, zamiast pomijać dzień."""
    assert _run_today(monkeypatch, [_WALK]) == 0
    line = next(l for l in capsys.readouterr().out.splitlines() if l.startswith('Wczoraj:'))
    assert 'Chodzenie' in line
