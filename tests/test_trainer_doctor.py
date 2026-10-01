import sqlite3

from trainer import doctor


class Status:
    def __init__(self, value):
        self.status = type('SnapshotStatus', (), {'value': value})()


def _ready_environment(monkeypatch, tmp_path):
    health_data = tmp_path / 'HealthData'
    databases = health_data / 'DBs'
    databases.mkdir(parents=True)
    for filename in ('garmin_activities.db', 'garmin.db'):
        with sqlite3.connect(databases / filename) as connection:
            connection.execute('CREATE TABLE sample (id INTEGER)')
    monkeypatch.setattr(doctor, 'HEALTH_DATA_DIR', health_data)
    monkeypatch.setattr(doctor, '_check_dependencies', lambda output: False)
    monkeypatch.setattr(doctor, '_snapshot_status', lambda: Status('fresh'))


def test_success_is_read_only_and_redacts_private_values(monkeypatch, tmp_path):
    _ready_environment(monkeypatch, tmp_path)
    monkeypatch.setattr('services.data_extract._find_garmindb_cli', lambda: 'ignored')
    output = []
    assert doctor.main(output.append) == 0
    assert 'OK ACT_DB: read-only quick_check ok' in output
    assert str(tmp_path) not in '\n'.join(output)
    assert 'ignored' not in '\n'.join(output)


def test_unset_env_uses_centrally_configured_directory(monkeypatch, tmp_path):
    _ready_environment(monkeypatch, tmp_path)
    monkeypatch.delenv('HEALTH_DATA_DIR', raising=False)
    monkeypatch.setattr('services.data_extract._find_garmindb_cli', lambda: 'ignored')
    output = []

    assert doctor.main(output.append) == 0
    assert 'OK HEALTH_DATA_DIR: configured' in output


def test_stale_snapshot_is_warning_with_success(monkeypatch, tmp_path):
    _ready_environment(monkeypatch, tmp_path)
    monkeypatch.setattr('services.data_extract._find_garmindb_cli', lambda: 'ignored')
    monkeypatch.setattr(doctor, '_snapshot_status', lambda: Status('stale'))
    output = []
    assert doctor.main(output.append) == 0
    assert 'WARN snapshot: stale' in output


def test_lowercase_dbs_is_supported_with_warning(monkeypatch, tmp_path):
    health_data = tmp_path / 'HealthData'
    databases = health_data / 'dbs'
    databases.mkdir(parents=True)
    for filename in ('garmin_activities.db', 'garmin.db'):
        with sqlite3.connect(databases / filename) as connection:
            connection.execute('CREATE TABLE sample (id INTEGER)')
    monkeypatch.setattr(doctor, 'HEALTH_DATA_DIR', health_data)
    monkeypatch.setattr(doctor, '_check_dependencies', lambda output: False)
    monkeypatch.setattr(doctor, '_snapshot_status', lambda: Status('fresh'))
    monkeypatch.setattr('services.data_extract._find_garmindb_cli', lambda: 'ignored')
    output = []

    assert doctor.main(output.append) == 0
    assert 'WARN DBs: using lowercase dbs directory' in output


def test_dbs_is_preferred_over_lowercase_fallback(monkeypatch, tmp_path):
    health_data = tmp_path / 'HealthData'
    databases = health_data / 'DBs'
    databases.mkdir(parents=True)
    for filename in ('garmin_activities.db', 'garmin.db'):
        with sqlite3.connect(databases / filename) as connection:
            connection.execute('CREATE TABLE sample (id INTEGER)')
    monkeypatch.setattr(doctor, 'HEALTH_DATA_DIR', health_data)
    monkeypatch.setattr(doctor, '_check_dependencies', lambda output: False)
    monkeypatch.setattr(doctor, '_snapshot_status', lambda: Status('fresh'))
    monkeypatch.setattr('services.data_extract._find_garmindb_cli', lambda: 'ignored')
    output = []

    assert doctor.main(output.append) == 0
    assert 'OK DBs: directory exists' in output
    assert 'WARN DBs: using lowercase dbs directory' not in output


def test_missing_database_directories_fail_without_paths(monkeypatch, tmp_path):
    health_data = tmp_path / 'HealthData'
    health_data.mkdir()
    monkeypatch.setattr(doctor, 'HEALTH_DATA_DIR', health_data)
    monkeypatch.setattr(doctor, '_check_dependencies', lambda output: False)
    monkeypatch.setattr(doctor, '_snapshot_status', lambda: Status('fresh'))
    monkeypatch.setattr('services.data_extract._find_garmindb_cli', lambda: 'ignored')
    output = []

    assert doctor.main(output.append) == 1
    assert 'FAIL DBs: directory missing' in output
    assert str(health_data) not in '\n'.join(output)


def test_runtime_failure_is_one_and_hides_secret(monkeypatch, tmp_path):
    missing_directory = tmp_path / 'missing-secret-token'
    monkeypatch.setattr(doctor, 'HEALTH_DATA_DIR', missing_directory)
    monkeypatch.setattr(doctor, '_check_dependencies', lambda output: False)
    monkeypatch.setattr('services.data_extract._find_garmindb_cli', lambda: 'ignored')
    monkeypatch.setattr(doctor, '_snapshot_status', lambda: Status('missing'))
    output = []
    assert doctor.main(output.append) == 1
    assert 'FAIL health-data-dir: directory missing' in output
    assert 'missing-secret-token' not in '\n'.join(output)


def test_dependency_or_cli_failure_has_precedence(monkeypatch, tmp_path):
    monkeypatch.delenv('HEALTH_DATA_DIR', raising=False)
    monkeypatch.setattr(doctor, 'HEALTH_DATA_DIR', tmp_path / 'isolated-health-data')
    monkeypatch.setattr(doctor, '_check_dependencies', lambda output: True)
    monkeypatch.setattr('services.data_extract._find_garmindb_cli', lambda: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(doctor, '_snapshot_status', lambda: Status('missing'))
    assert doctor.main(lambda line: None) == 3


def test_sqlite_check_uses_read_only_connection(tmp_path):
    database = tmp_path / 'database.db'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE sample (id INTEGER)')
    assert doctor._check_sqlite(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'sample'").fetchone() == ('sample',)
