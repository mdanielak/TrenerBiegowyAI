import os
from pathlib import Path
import builtins
import types
from unittest import mock
import pytest

from trainer.env_file import load_env_file
from trainer.setup_wizard import _write_env
from trainer import setup_wizard, profile_store, preferences


def test_write_env_updates_without_duplicates_and_preserves_lines(tmp_path):
    path = tmp_path / '.env'
    path.write_text('# zachowaj\nONE=old\nOTHER=value\nONE=older\n', encoding='utf8')
    _write_env(path, {'ONE': 'new value', 'NEW': 'pa ss#wo"rd\\'})
    text = path.read_text(encoding='utf8')
    assert '# zachowaj' in text and 'OTHER=value' in text
    assert text.count('ONE=') == 1 and "ONE='new value'" in text
    assert "NEW='pa ss#wo\"rd\\'" in text


def test_write_env_round_trips_special_values(tmp_path, monkeypatch):
    path = tmp_path / '.env'
    values = {'PASSWORD': 'pa ss#wo"rd\\', 'HEALTH_DATA_DIR': r'C:\Moje dane\Health Data'}
    _write_env(path, values)
    monkeypatch.delenv('PASSWORD', raising=False)
    monkeypatch.delenv('HEALTH_DATA_DIR', raising=False)
    assert load_env_file(path, override=True) == values


def test_write_env_skips_empty_values(tmp_path):
    path = tmp_path / '.env'
    path.write_text('KEEP=old\n', encoding='utf8')
    _write_env(path, {'EMPTY': '', 'KEEP': ''})
    assert path.read_text(encoding='utf8') == 'KEEP=old\n'


def test_write_env_quoting_matrix_round_trips(tmp_path, monkeypatch):
    path = tmp_path / '.env'
    values = {
        'BARE': 'simple_value-1', 'SPACES': 'two words',
        'WINDOWS': r'C:\Moje dane\Health Data', 'HASH': 'a#b',
        'DOUBLE': 'a"b', 'SINGLE': "a'b", 'BOTH': "a'\"b\\",
        'SLASH': '\\',
    }
    _write_env(path, values)
    for key in values: monkeypatch.delenv(key, raising=False)
    assert load_env_file(path, override=True) == values
    text = path.read_text(encoding='utf8')
    assert "SPACES='two words'" in text
    assert 'BOTH="a\'\\"b\\\\"' in text


def test_write_env_rejects_newline(tmp_path):
    with pytest.raises(ValueError, match='NOWA'):
        _write_env(tmp_path / '.env', {'NOWA': 'a\nb'})


class _Tty:
    def isatty(self): return True


def _redirect_stores(monkeypatch, tmp_path):
    settings = types.SimpleNamespace(runner_profile_local=tmp_path / 'profile.json', local_dir=tmp_path)
    monkeypatch.setattr(profile_store, 'SETTINGS', settings)
    monkeypatch.setattr(preferences, 'SETTINGS', settings)
    monkeypatch.setattr(setup_wizard, 'PROJECT_ROOT', tmp_path)


def test_wizard_happy_path_writes_files_without_echoing_secrets(monkeypatch, tmp_path, capsys):
    _redirect_stores(monkeypatch, tmp_path)
    answers = iter(['runner@example.com', 'sekret#haslo', str(tmp_path / 'health'),
                    '35', '70', '180', '190', '50', '170', 'n',
                    'półmaraton', '2027-05-01', '1:45:00',
                    'n', 'n', 'n', 'n', 'n', 'n', 'n', '2',
                    't', 'https://api.example/v1', 'model', 'tajny-klucz', 't', 't'])
    monkeypatch.setattr(builtins, 'input', lambda _: next(answers))
    monkeypatch.setattr(setup_wizard.sys, 'stdin', _Tty())
    assert setup_wizard.main() == 0
    profile = profile_store.load_profile()
    assert profile['age'] == 35 and profile['target_hm'] == 'półmaraton'
    assert preferences.load_preferences()['max_quality_sessions_per_week'] == 2
    env = (tmp_path / '.env').read_text(encoding='utf8')
    assert 'sekret#haslo' in env and 'tajny-klucz' in env
    output = capsys.readouterr().out
    assert 'sekret#haslo' not in output and 'tajny-klucz' not in output


def test_wizard_zone_sync_survives_final_profile_write(monkeypatch, tmp_path):
    _redirect_stores(monkeypatch, tmp_path)
    profile_store.save_profile({'age': 30, 'weight_kg': 60, 'height_cm': 170, 'hr_max': 180, 'hr_rest': 50, 'lactate_threshold_hr': 160})
    def zones(sync=False):
        assert sync
        profile_store.set_hr_zones({'z1': 100, 'z2': 120, 'z3': 140, 'z4': 160, 'z5': 175}, 190, 'test Garmin')
        return 0
    module = types.ModuleType('trainer.commands.zones'); module.main = zones
    monkeypatch.setitem(__import__('sys').modules, 'trainer.commands.zones', module)
    answers = iter(['', '', str(tmp_path / 'health'), '31', '61', '171', '190', '51', '170', 't',
                    '', '', '', 'n', 'n', 'n', 'n', 'n', 'n', 'n', '0', 'n', 'n'])
    monkeypatch.setattr(builtins, 'input', lambda _: next(answers))
    monkeypatch.setattr(setup_wizard.sys, 'stdin', _Tty())
    assert setup_wizard.main() == 0
    result = profile_store.load_profile()
    assert result['age'] == 31 and result['hr_zone_floors'] == {'z1': 100, 'z2': 120, 'z3': 140, 'z4': 160, 'z5': 175}
    assert result['hr_zones_source'] == 'test Garmin' and result['hr_zones'] == 'Z1 100-119, Z2 120-139, Z3 140-159, Z4 160-174, Z5 175-190'
