import json
import sys
import types

import pytest

from trainer import garmin_auth


def test_ensure_token_uses_existing_token(monkeypatch, tmp_path):
    path = tmp_path / 'garmin_tokens.json'
    path.write_text('{}', encoding='utf8')
    calls = []
    class Garmin:
        def __init__(self, *args): calls.append(args)
        def login(self, token): calls.append(('login', token))
    monkeypatch.setattr(garmin_auth, 'token_path', lambda: path)
    monkeypatch.setattr(garmin_auth, 'Garmin', Garmin)
    assert isinstance(garmin_auth.ensure_token(), Garmin)
    assert calls == [(), ('login', str(path))]


def test_ensure_token_falls_back_from_invalid_token(monkeypatch, tmp_path):
    path = tmp_path / 'garmin_tokens.json'
    path.write_text('{}', encoding='utf8')
    calls = []
    class Garmin:
        def __init__(self, *args): self.args = args
        def login(self, token):
            calls.append((self.args, token))
            if not self.args: raise RuntimeError('expired')
    monkeypatch.setattr(garmin_auth, 'token_path', lambda: path)
    monkeypatch.setattr(garmin_auth, 'Garmin', Garmin)
    garmin_auth.ensure_token('runner@example.com', 'secret')
    assert calls == [((), str(path)), (('runner@example.com', 'secret'), str(path))]


def test_ensure_token_requires_password(monkeypatch, tmp_path):
    monkeypatch.setattr(garmin_auth, 'token_path', lambda: tmp_path / 'missing.json')
    with pytest.raises(garmin_auth.GarminAuthError, match='GARMIN_PASSWORD'):
        garmin_auth.ensure_token('runner@example.com', '')


def test_ensure_garmindb_config_creates_neutral_credentials(monkeypatch, tmp_path):
    package = tmp_path / 'package'; package.mkdir()
    (package / 'GarminConnectConfig.json.example').write_text(json.dumps({'credentials': {'user': '', 'password': 'old'}}), encoding='utf8')
    monkeypatch.setattr(garmin_auth, 'token_path', lambda: tmp_path / '.GarminDb' / 'garmin_tokens.json')
    monkeypatch.setitem(sys.modules, 'garmindb', types.SimpleNamespace(__file__=str(package / '__init__.py')))
    assert garmin_auth.ensure_garmindb_config('runner@example.com') is True
    saved = json.loads((tmp_path / '.GarminDb' / 'GarminConnectConfig.json').read_text(encoding='utf8'))
    assert saved['credentials'] == {'user': 'runner@example.com', 'password': ''}


def test_ensure_garmindb_config_never_overwrites(monkeypatch, tmp_path):
    config = tmp_path / '.GarminDb' / 'GarminConnectConfig.json'; config.parent.mkdir()
    config.write_text('keep', encoding='utf8')
    monkeypatch.setattr(garmin_auth, 'token_path', lambda: config.parent / 'garmin_tokens.json')
    assert garmin_auth.ensure_garmindb_config('runner@example.com') is False
    assert config.read_text(encoding='utf8') == 'keep'
