# -*- coding: utf-8 -*-
"""Tests for services/data_extract.py — data extraction and sync services."""
import sys
import os
import json
import sqlite3
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

from services.data_extract import (
    GarminDBSyncError, SnapshotStatus, SyncStatus, extract, load_data_latest,
    print_summary, read_snapshot_status, save_json, sync, sync_full, synchronize_and_save,
)
from services.locking import acquire_lock
from trainer.commands import sync as data_sync


class TestExtract:
    """Test the extract() function with mocked databases."""

    @patch('services.data_extract.os.path.exists', return_value=False)
    def test_extract_returns_empty_when_no_db(self, mock_exists):
        data = extract()
        assert data['activities'] == []
        assert data['daily_health'] == []
        assert data['sleep'] == []
        assert data['hrv'] == []
        assert data['weight'] == []
        assert 'timestamp' in data
        assert datetime.fromisoformat(data['timestamp']).tzinfo is not None

    @patch('services.data_extract.MAIN_DB', '/nonexistent/garmin.db')
    @patch('services.data_extract.ACT_DB', '/nonexistent/activities.db')
    def test_extract_returns_empty_with_nonexistent_paths(self):
        data = extract()
        assert data['activities'] == []
        assert data['daily_health'] == []

    def test_extract_with_mock_activities(self, tmp_path):
        """Test extraction with a real SQLite database in tmp."""
        act_path = str(tmp_path / "activities.db")

        conn = sqlite3.connect(act_path)
        conn.execute("""
            CREATE TABLE activities (
                activity_id INTEGER, start_time TEXT, name TEXT, distance REAL,
                moving_time TEXT, avg_hr INTEGER, max_hr INTEGER,
                avg_speed REAL, ascent REAL, training_effect REAL,
                anaerobic_training_effect REAL, sport TEXT, sub_sport TEXT
            )
        """)
        conn.execute("""
            INSERT INTO activities VALUES
            (123, '2026-09-15 08:00:00', 'Bieg poranny', 10.5,
             '0:55:00', 150, 170, 3.0, 50.0, 3.5, 1.2, 'running', 'running')
        """)
        conn.commit()
        conn.close()

        with patch('services.data_extract.ACT_DB', act_path), \
             patch('services.data_extract.MAIN_DB', '/nonexistent/main.db'):
            data = extract()

        assert len(data['activities']) == 1
        assert data['activities'][0]['name'] == 'Bieg poranny'
        assert data['activities'][0]['distance_km'] == 10.5
        assert data['activities'][0]['activity_id'] == 123
        assert data['activities'][0]['avg_speed_kmh'] == 3.0

    def test_extract_handles_empty_activities(self, tmp_path):
        act_path = str(tmp_path / "activities.db")

        conn = sqlite3.connect(act_path)
        conn.execute("""
            CREATE TABLE activities (
                activity_id INTEGER, start_time TEXT, name TEXT, distance REAL,
                moving_time TEXT, avg_hr INTEGER, max_hr INTEGER,
                avg_speed REAL, ascent REAL, training_effect REAL,
                anaerobic_training_effect REAL, sport TEXT, sub_sport TEXT
            )
        """)
        conn.commit()
        conn.close()

        with patch('services.data_extract.ACT_DB', act_path), \
             patch('services.data_extract.MAIN_DB', '/nonexistent/main.db'):
            data = extract()
        assert data['activities'] == []


class TestSaveLoadJson:
    def test_save_and_load_roundtrip(self, tmp_path):
        data = {
            "timestamp": "2026-09-16T10:00:00",
            "activities": [{"name": "test", "distance_km": 5.0}],
            "daily_health": [],
            "sleep": [],
            "hrv": [],
            "weight": [],
        }
        path = tmp_path / "test_data.json"
        save_json(data, path)

        loaded = load_data_latest(path)
        assert loaded['timestamp'] == data['timestamp']
        assert len(loaded['activities']) == 1

    def test_save_overwrites_existing_file_atomically(self, tmp_path):
        path = tmp_path / "test_data.json"
        path.write_text(json.dumps({"old": True}), encoding="utf-8")

        save_json({"new": True}, path)

        assert json.loads(path.read_text(encoding="utf-8")) == {"new": True}

    def test_save_failure_preserves_existing_file_and_cleans_temporary_file(self, tmp_path, monkeypatch):
        path = tmp_path / "test_data.json"
        original = {"timestamp": "2026-09-16T10:00:00", "old": True}
        path.write_text(json.dumps(original), encoding="utf-8")

        def fail_dump(*args, **kwargs):
            raise OSError("simulated write failure")

        monkeypatch.setattr("services.data_extract.json.dump", fail_dump)

        with pytest.raises(OSError, match="simulated write failure"):
            save_json({"new": True}, path)

        assert json.loads(path.read_text(encoding="utf-8")) == original
        assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []

    def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_data_latest(tmp_path / "nonexistent.json")

    def test_load_corrupted_json_raises(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{invalid json", encoding='utf-8')
        with pytest.raises(json.JSONDecodeError):
            load_data_latest(path)


class TestSnapshotStatus:
    def test_missing_snapshot(self, tmp_path):
        assert read_snapshot_status(tmp_path / "missing.json").status is SnapshotStatus.MISSING

    def test_invalid_snapshot(self, tmp_path):
        path = tmp_path / "invalid.json"
        path.write_text('{"timestamp": "not-a-date"}', encoding="utf-8")
        assert read_snapshot_status(path).status is SnapshotStatus.INVALID

    def test_fresh_and_stale_snapshot(self, tmp_path):
        now = datetime(2026, 9, 28, tzinfo=timezone.utc)
        path = tmp_path / "snapshot.json"
        path.write_text(json.dumps({"timestamp": now.isoformat()}), encoding="utf-8")
        assert read_snapshot_status(path, now=now).status is SnapshotStatus.FRESH
        assert read_snapshot_status(path, now=now + timedelta(hours=25)).status is SnapshotStatus.STALE

    def test_utc_timestamp_has_correct_age(self, tmp_path):
        now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
        path = tmp_path / "snapshot.json"
        path.write_text(json.dumps({"timestamp": (now - timedelta(seconds=59)).isoformat()}), encoding="utf-8")

        assert read_snapshot_status(path, now=now, ttl_seconds=60).status is SnapshotStatus.FRESH

    def test_naive_legacy_timestamp_is_interpreted_as_local_time(self, tmp_path):
        now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
        local_created_at = (now.astimezone() - timedelta(seconds=59)).replace(tzinfo=None)
        path = tmp_path / "snapshot.json"
        path.write_text(json.dumps({"timestamp": local_created_at.isoformat()}), encoding="utf-8")

        assert read_snapshot_status(path, now=now, ttl_seconds=60).status is SnapshotStatus.FRESH

    def test_snapshot_status_at_ttl_boundary_and_with_z_suffix(self, tmp_path):
        now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
        path = tmp_path / "snapshot.json"
        path.write_text(json.dumps({"timestamp": (now - timedelta(seconds=60)).isoformat().replace("+00:00", "Z")}), encoding="utf-8")

        assert read_snapshot_status(path, now=now, ttl_seconds=60).status is SnapshotStatus.FRESH
        assert read_snapshot_status(path, now=now + timedelta(seconds=1), ttl_seconds=60).status is SnapshotStatus.STALE


class TestSyncFailure:
    def test_sync_failure_blocks_snapshot_save(self, monkeypatch):
        monkeypatch.setattr(data_sync, 'setup_logging', lambda: None)
        operation_mock = MagicMock(side_effect=GarminDBSyncError('timeout'))
        monkeypatch.setattr(data_sync, 'synchronize_and_save', operation_mock)
        monkeypatch.setattr(sys, 'argv', ['data_sync.py'])

        with pytest.raises(GarminDBSyncError, match='timeout'):
            data_sync.main()

        operation_mock.assert_called_once_with(fresh=False)

    def test_partial_sync_status_is_saved_in_snapshot(self, monkeypatch):
        from services import data_extract

        monkeypatch.setattr(data_extract, 'sync', lambda progress=None: SyncStatus.PARTIAL)
        monkeypatch.setattr(data_extract, 'extract', lambda: {"timestamp": "2026-09-16T10:00:00"})
        save_mock = MagicMock()
        monkeypatch.setattr(data_extract, 'save_json', save_mock)

        synchronize_and_save()

        assert save_mock.call_args.args[0]['sync_status'] == "partial"


class TestSynchronizeAndSave:
    @pytest.mark.parametrize(("fresh", "expected"), [(False, "sync"), (True, "sync_full")])
    def test_uses_proper_sync_variant(self, fresh, expected, monkeypatch):
        from services import data_extract

        calls = []
        monkeypatch.setattr(data_extract, 'sync', lambda progress=None: calls.append("sync") or SyncStatus.FULL)
        monkeypatch.setattr(data_extract, 'sync_full', lambda progress=None: calls.append("sync_full") or SyncStatus.FULL)
        monkeypatch.setattr(data_extract, 'extract', lambda: calls.append("extract") or {"timestamp": "test"})
        monkeypatch.setattr(data_extract, 'save_json', lambda data: calls.append(("save", data)))

        data = synchronize_and_save(fresh=fresh)

        assert calls[0] == expected
        assert calls[1:] == ["extract", ("save", data)]

    def test_does_not_acquire_a_second_lock(self, tmp_path, monkeypatch):
        from services import data_extract

        monkeypatch.setattr(data_extract, 'sync', lambda progress=None: SyncStatus.FULL)
        monkeypatch.setattr(data_extract, 'extract', lambda: {"timestamp": "test"})
        monkeypatch.setattr(data_extract, 'save_json', lambda data: None)

        with acquire_lock(name="sync", directory=tmp_path):
            assert synchronize_and_save()["sync_status"] == "full"


class TestGarminDBSubprocess:
    @pytest.fixture(autouse=True)
    def _stub_auth(self, monkeypatch):
        """Nie wchodź w prawdziwe uwierzytelnianie ani w pakiet garmindb.

        sync() dba teraz o token przed uruchomieniem GarminDB, a realny
        garmindb importuje garminconnect, który inne testy podmieniają
        na atrapę w sys.modules.
        """
        from services import data_extract

        monkeypatch.setattr(data_extract, 'ensure_garmindb_config', lambda email: False)
        monkeypatch.setattr(data_extract, 'ensure_token', lambda: object())

    def test_sync_uses_logs_directory_as_cwd(self, monkeypatch, tmp_path):
        from services import data_extract

        calls = []
        monkeypatch.setattr(data_extract, 'PROJECT_ROOT', tmp_path)
        monkeypatch.setattr(data_extract, '_find_python', lambda: 'python')
        monkeypatch.setattr(data_extract, '_find_garmindb_cli', lambda: 'C:/tools/garmindb_cli.py')
        monkeypatch.setattr(data_extract, 'download_today', lambda cwd=None: True)
        monkeypatch.setattr(data_extract.subprocess, 'run', lambda *args, **kwargs: calls.append(kwargs) or MagicMock(returncode=0))

        assert sync() is SyncStatus.FULL
        assert calls[0]['cwd'] == tmp_path / 'logs'
        assert (tmp_path / 'logs').is_dir()

    def test_full_sync_uses_logs_directory_as_cwd(self, monkeypatch, tmp_path):
        from services import data_extract

        calls = []
        monkeypatch.setattr(data_extract, 'PROJECT_ROOT', tmp_path)
        monkeypatch.setattr(data_extract, '_find_python', lambda: 'python')
        monkeypatch.setattr(data_extract, '_find_garmindb_cli', lambda: 'C:/tools/garmindb_cli.py')
        monkeypatch.setattr(data_extract.subprocess, 'run', lambda *args, **kwargs: calls.append(kwargs) or MagicMock(returncode=0))

        assert sync_full() is SyncStatus.FULL
        assert calls[0]['cwd'] == tmp_path / 'logs'

    @pytest.mark.parametrize('operation', ['sync', 'sync_full', 'download_today'])
    def test_sync_without_token_requires_login_before_subprocess(self, monkeypatch, operation):
        from services import data_extract
        from trainer.garmin_auth import GarminAuthError
        def missing_token():
            raise GarminAuthError('Zaloguj ponownie: python -m trainer setup')
        run = MagicMock()
        monkeypatch.setattr(data_extract, 'ensure_token', missing_token)
        monkeypatch.setattr(data_extract.subprocess, 'run', run)
        with pytest.raises(GarminAuthError, match='python -m trainer setup'):
            getattr(data_extract, operation)()
        run.assert_not_called()

    def test_find_garmindb_cli_finds_in_python_dir(self, monkeypatch, tmp_path):
        from services import data_extract
        fake_bin = tmp_path / 'bin'
        fake_bin.mkdir()
        fake_cli = fake_bin / 'garmindb_cli.py'
        fake_cli.write_text('#!/usr/bin/env python')
        monkeypatch.setattr(data_extract, 'PROJECT_ROOT', tmp_path / 'proj')
        monkeypatch.setattr(data_extract.sys, 'executable', str(fake_bin / 'python'))
        assert data_extract._find_garmindb_cli() == str(fake_cli)



class TestPrintSummary:
    def test_print_summary_runs_without_error(self, capsys):
        data = {
            "timestamp": "2026-09-16T10:00:00",
            "activities": [{"date": "2026-09-15", "name": "Bieg",
                           "distance_km": 10.0, "pace": "5:30/km",
                           "avg_hr": 150, "max_hr": 170, "ascent_m": 50}],
            "daily_health": [{"date": "2026-09-16", "rhr": 50, "hr_min": 45,
                             "hr_max": 170, "steps": 8000, "stress_avg": 30,
                             "rr": 60, "spo2": 97}],
            "sleep": [{"date": "2026-09-16", "total_h": 7.5, "deep_h": 1.5,
                       "rem_h": 1.2, "score": 85, "qualifier": "GOOD"}],
            "hrv": [{"date": "2026-09-16", "weekly_avg": 70, "last_night": 72,
                     "baseline_low": 67, "baseline_high": 82, "status": "BALANCED"}],
            "weight": [{"date": "2026-09-16", "weight_kg": 74.0}],
        }
        print_summary(data)
        captured = capsys.readouterr()
        assert "OSTATNIA SYNCHRONIZACJA" in captured.out
        assert "AKTYWNOŚCI" in captured.out
        assert "ZDROWIE DZIENNE" in captured.out

    def test_print_summary_empty_data(self, capsys):
        data = {
            "timestamp": "2026-09-16T10:00:00",
            "activities": [],
            "daily_health": [],
            "sleep": [],
            "hrv": [],
            "weight": [],
        }
        print_summary(data)
        captured = capsys.readouterr()
        assert "OSTATNIA SYNCHRONIZACJA" in captured.out

    def test_print_summary_shows_hrv_alert(self, capsys):
        data = {
            "timestamp": "2026-09-16T10:00:00",
            "activities": [],
            "daily_health": [],
            "sleep": [],
            "hrv": [
                {"date": "2026-09-16", "weekly_avg": 60, "last_night": 55,
                 "baseline_low": 67, "baseline_high": 82, "status": "LOW"},
                {"date": "2026-09-15", "weekly_avg": 61, "last_night": 56,
                 "baseline_low": 67, "baseline_high": 82, "status": "LOW"},
                {"date": "2026-09-14", "weekly_avg": 62, "last_night": 57,
                 "baseline_low": 67, "baseline_high": 82, "status": "LOW"},
            ],
            "weight": [],
        }
        print_summary(data)
        captured = capsys.readouterr()
        assert "ALERT" in captured.out
        assert "HRV NISKIE" in captured.out


def _activities_db(path, start_times):
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE activities (
            activity_id INTEGER, start_time TEXT, name TEXT, distance REAL,
            moving_time TEXT, avg_hr INTEGER, max_hr INTEGER,
            avg_speed REAL, ascent REAL, training_effect REAL,
            anaerobic_training_effect REAL, sport TEXT, sub_sport TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO activities VALUES (?, ?, 'Bieg', 5.0, '0:30:00', 140, 160, 10.0, 0, 2.0, 0.0, 'running', 'running')",
        list(enumerate(start_times)),
    )
    conn.commit()
    conn.close()


def test_extract_takes_every_activity_in_the_window_not_the_last_50(tmp_path):
    act_path = str(tmp_path / "activities.db")
    newest = datetime(2026, 10, 1, 7, 0)
    recent = [(newest - timedelta(hours=12 * i)).strftime('%Y-%m-%d %H:%M:%S') for i in range(80)]
    old = (newest - timedelta(days=200)).strftime('%Y-%m-%d %H:%M:%S')
    _activities_db(act_path, recent + [old])

    with patch('services.data_extract.ACT_DB', act_path), \
         patch('services.data_extract.MAIN_DB', '/nonexistent/main.db'):
        data = extract()

    assert len(data['activities']) == 80
    assert data['window'] == {'activity_days': 120, 'health_days': 90}


def test_extract_reads_health_from_the_last_90_days(tmp_path):
    main_path = str(tmp_path / "garmin.db")
    conn = sqlite3.connect(main_path)
    conn.execute("""
        CREATE TABLE daily_summary (
            day TEXT, rhr INTEGER, hr_min INTEGER, hr_max INTEGER, steps INTEGER, stress_avg INTEGER,
            rr_waking_avg REAL, spo2_avg REAL, calories_active INTEGER, calories_total INTEGER,
            moderate_activity_time TEXT, vigorous_activity_time TEXT
        )
    """)
    conn.execute("CREATE TABLE weight (day TEXT, weight REAL)")
    last = datetime(2026, 10, 1)
    conn.executemany(
        "INSERT INTO daily_summary (day, rhr) VALUES (?, 50)",
        [((last - timedelta(days=i)).strftime('%Y-%m-%d'),) for i in range(120)],
    )
    conn.commit()
    conn.close()

    with patch('services.data_extract.ACT_DB', '/nonexistent/activities.db'), \
         patch('services.data_extract.MAIN_DB', main_path):
        data = extract()

    assert len(data['daily_health']) == 91
    assert data['daily_health'][0]['date'] == '2026-10-01'
    assert data['daily_health'][-1]['date'] == '2026-07-03'
