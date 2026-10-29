import os

import pytest

from trainer.ai_settings import read_ai_settings, resolve_test_key, same_api_provider, save_ai_settings
from trainer.env_file import read_env_file, load_env_file


def save(path, **changes):
    values = dict(base_url='https://api.example/v1', model='model', api_key='', export_enabled=False)
    values.update(changes)
    save_ai_settings(path, **values)


def test_preserves_other_entries_comments_and_blank_key(tmp_path):
    path = tmp_path / '.env'
    path.write_text('# comment\nGARMIN_PASSWORD="other"\nAI_BASE_URL=https://api.example/v1\nAI_API_KEY="old"\nexport AI_MODEL=first\nAI_MODEL=last\n')
    save(path)
    assert '# comment\nGARMIN_PASSWORD="other"' in path.read_text()
    assert path.read_text().count('AI_MODEL=') == 1
    assert read_env_file(path)['AI_API_KEY'] == 'old'
    assert read_ai_settings(path)['key_present'] is True
    assert 'old' not in str(read_ai_settings(path))
    if os.name == 'posix':
        assert path.stat().st_mode & 0o777 == 0o600


def test_key_roundtrip_clear_and_restart_loading(tmp_path, monkeypatch):
    path = tmp_path / '.env'
    key = 'a\\b"c\'d # e=$VALUE'
    save(path, api_key=key, export_enabled=True)
    assert read_env_file(path)['AI_API_KEY'] == key
    monkeypatch.delenv('AI_API_KEY', raising=False)
    assert load_env_file(path)['AI_API_KEY'] == key
    assert read_ai_settings(path)['export_enabled'] is True
    save(path, clear_key=True)
    assert read_env_file(path)['AI_API_KEY'] == ''
    assert read_ai_settings(path)['key_present'] is False
    assert read_ai_settings(path)['export_enabled'] is False


@pytest.mark.parametrize('changes', [
    {'base_url': 'file:///tmp/test'}, {'base_url': 'https://user:secret@host/v1'},
    {'base_url': 'https://host/v1?key=secret'}, {'base_url': 'https://host:bad'},
    {'base_url': 'https://bad host/v1'}, {'model': ''},
    {'api_key': 'secret\nOTHER=injection'}, {'api_key': 'secret\x00'},
    {'api_key': 'secret\u2028OTHER=injection'},
    {'api_key': 'secret', 'clear_key': True}, {'model': 'x' * 4097},
])
def test_invalid_settings_never_modify_file(tmp_path, changes):
    path = tmp_path / '.env'
    path.write_text('# original\n')
    with pytest.raises(ValueError):
        save(path, **changes)
    assert path.read_text() == '# original\n'


@pytest.mark.parametrize('url', [
    'https://api.example/v2', 'https://api.example/other/v1/',
    'https://API.EXAMPLE:443/v1',
])
def test_same_provider_reuses_and_preserves_key_after_path_change(tmp_path, url):
    path = tmp_path / '.env'
    path.write_text('AI_BASE_URL=https://api.example/v1\nAI_API_KEY=saved-secret\n')
    assert resolve_test_key(path, base_url=url, api_key='', clear_key=False) == 'saved-secret'
    save(path, base_url=url)
    assert read_env_file(path)['AI_API_KEY'] == 'saved-secret'
    assert read_env_file(path)['AI_BASE_URL'] == url
    assert read_ai_settings(path)['key_present'] is True
    # Ponowny odczyt z dysku, bez polegania na stanie procesu.
    assert resolve_test_key(path, base_url=url, api_key='', clear_key=False) == 'saved-secret'


@pytest.mark.parametrize('url', [
    'https://api.example.evil/v1', 'https://api.example-other/v1',
    'https://other.example/v1', 'https://sub.api.example/v1',
    'http://api.example/v1', 'https://api.example:8443/v1',
    'https://api.example@evil.example/v1', 'https://api.example:bad/v1',
])
def test_different_provider_never_receives_saved_key(tmp_path, url):
    path = tmp_path / '.env'
    original = 'AI_BASE_URL=https://api.example/v1\nAI_API_KEY=saved-secret\n'
    path.write_text(original)
    assert not same_api_provider(url, 'https://api.example/v1')
    with pytest.raises(ValueError):
        resolve_test_key(path, base_url=url, api_key='', clear_key=False)
    with pytest.raises(ValueError):
        save(path, base_url=url)
    assert path.read_text() == original


@pytest.mark.parametrize('changes,expected', [({'api_key': 'new-secret'}, 'new-secret'), ({'clear_key': True}, '')])
def test_provider_change_requires_explicit_key_decision(tmp_path, changes, expected):
    path = tmp_path / '.env'
    path.write_text('AI_BASE_URL=https://old.example/v1\nAI_API_KEY=old-secret\n')
    save(path, **changes)
    assert read_env_file(path)['AI_API_KEY'] == expected


def test_atomic_failure_preserves_old_file_and_cleans_temporary(tmp_path, monkeypatch):
    path = tmp_path / '.env'
    path.write_text('AI_API_KEY=old\n')
    def fail(*args):
        raise OSError('failure')
    monkeypatch.setattr('trainer.files.os.replace', fail)
    with pytest.raises(OSError):
        save(path, api_key='new')
    assert path.read_text() == 'AI_API_KEY=old\n'
    assert list(tmp_path.glob('*.tmp')) == []
