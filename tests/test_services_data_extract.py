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
    print_summary, read_snapshot_status, save_json, sync, sync_full,
)
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


class TestSyncFailure:
    def test_sync_failure_blocks_snapshot_save(self, monkeypatch):
        monkeypatch.setattr(data_sync, 'setup_logging', lambda: None)
        monkeypatch.setattr(data_sync, 'sync', lambda: (_ for _ in ()).throw(GarminDBSyncError('timeout')))
        extract_mock = MagicMock()
        save_mock = MagicMock()
        monkeypatch.setattr(data_sync, 'extract', extract_mock)
        monkeypatch.setattr(data_sync, 'save_json', save_mock)
        monkeypatch.setattr(sys, 'argv', ['data_sync.py'])

        with pytest.raises(GarminDBSyncError, match='timeout'):
            data_sync.main()

        extract_mock.assert_not_called()
        save_mock.assert_not_called()

    def test_partial_sync_status_is_saved_in_snapshot(self, monkeypatch):
        monkeypatch.setattr(data_sync, 'setup_logging', lambda: None)
        monkeypatch.setattr(data_sync, 'sync', lambda: SyncStatus.PARTIAL)
        monkeypatch.setattr(data_sync, 'extract', lambda: {"timestamp": "2026-09-16T10:00:00"})
        save_mock = MagicMock()
        monkeypatch.setattr(data_sync, 'save_json', save_mock)
        monkeypatch.setattr(data_sync, 'print_summary', lambda data: None)
        monkeypatch.setattr(sys, 'argv', ['data_sync.py'])

        data_sync.main()

        assert save_mock.call_args.args[0]['sync_status'] == "partial"


class TestGarminDBSubprocess:
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
