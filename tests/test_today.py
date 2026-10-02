from trainer.commands import today
from services.data_extract import SnapshotReadResult, SnapshotStatus


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
