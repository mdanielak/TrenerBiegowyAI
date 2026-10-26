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
            if not self.args: raise garmin_auth.GarminConnectAuthenticationError('expired')
    monkeypatch.setattr(garmin_auth, 'token_path', lambda: path)
    monkeypatch.setattr(garmin_auth, 'Garmin', Garmin)
    garmin_auth.ensure_token('runner@example.com', 'secret')
    assert calls == [((), str(path)), (('runner@example.com', 'secret'), str(path))]


def test_ensure_token_requires_password(monkeypatch, tmp_path):
    monkeypatch.setattr(garmin_auth, 'token_path', lambda: tmp_path / 'missing.json')
    with pytest.raises(garmin_auth.GarminAuthError, match='python -m trainer setup'):
        garmin_auth.ensure_token('runner@example.com', '')


def test_expired_token_without_password_requests_interactive_login(monkeypatch, tmp_path):
    path = tmp_path / 'tokens.json'
    path.write_text('{}')
    calls = []
    class Garmin:
        def __init__(self, *args): calls.append(args)
        def login(self, token):
            raise garmin_auth.GarminConnectAuthenticationError('expired')
    monkeypatch.setenv('GARMIN_PASSWORD', 'ignored-secret')
    monkeypatch.setattr(garmin_auth, 'token_path', lambda: path)
    monkeypatch.setattr(garmin_auth, 'Garmin', Garmin)
    with pytest.raises(garmin_auth.GarminAuthError, match='python -m trainer setup') as caught:
        garmin_auth.ensure_token('runner@example.com')
    assert caught.value.retry_credentials
    assert 'ignored-secret' not in str(caught.value)
    assert calls == [()]
    assert path.read_text() == '{}'


def test_mfa_passed_to_constructor_not_login(monkeypatch, tmp_path):
    path = tmp_path / 'tokens.json'
    calls = []
    prompt = lambda: '123456'
    class Garmin:
        def __init__(self, email, password, *, prompt_mfa):
            assert prompt_mfa is prompt
            calls.append((email, password))
        def login(self, token):
            calls.append(token)
    monkeypatch.setattr(garmin_auth, 'token_path', lambda: path)
    monkeypatch.setattr(garmin_auth, 'Garmin', Garmin)
    garmin_auth.ensure_token('runner@example.com', ' secret ', prompt_mfa=prompt)
    assert calls == [('runner@example.com', ' secret '), str(path)]


@pytest.mark.parametrize(('error', 'retry', 'message'), [
    (garmin_auth.GarminConnectTooManyRequestsError('429'), False, 'HTTP 429'),
    (garmin_auth.GarminConnectConnectionError('unexpected title'), False, 'SSO'),
    (garmin_auth.GarminConnectAuthenticationError('Invalid Username or Password'), True, 'odrzucił'),
    (garmin_auth.GarminConnectAuthenticationError('MFA failed'), False, 'MFA'),
    (TypeError('internal failure'), False, 'TypeError'),
])
def test_login_failure_does_not_repeat_strategy_chain(monkeypatch, tmp_path, error, retry, message):
    calls = []
    class Garmin:
        client = types.SimpleNamespace(skip_strategies=set())
        def __init__(self, *args, **kwargs): pass
        def login(self, token):
            calls.append(token)
            raise error
    monkeypatch.setattr(garmin_auth, 'token_path', lambda: tmp_path / 'tokens.json')
    monkeypatch.setattr(garmin_auth, 'Garmin', Garmin)
    with pytest.raises(garmin_auth.GarminAuthError, match=message) as caught:
        garmin_auth.ensure_token('runner@example.com', 'secret')
    assert caught.value.__cause__ is error
    assert caught.value.retry_credentials is retry
    assert len(calls) == 1
    assert Garmin.client.skip_strategies == set()


@pytest.mark.parametrize('error', [
    garmin_auth.GarminConnectTooManyRequestsError('429'),
    garmin_auth.GarminConnectConnectionError('offline'),
])
def test_token_network_error_never_falls_back_to_password(monkeypatch, tmp_path, error):
    path = tmp_path / 'tokens.json'
    path.write_text('{}')
    calls = []
    class Garmin:
        def __init__(self, *args): calls.append(args)
        def login(self, token): raise error
    monkeypatch.setattr(garmin_auth, 'token_path', lambda: path)
    monkeypatch.setattr(garmin_auth, 'Garmin', Garmin)
    with pytest.raises(garmin_auth.GarminAuthError) as caught:
        garmin_auth.ensure_token('runner@example.com', 'secret')
    assert caught.value.__cause__ is error
    assert calls == [()]
    assert path.read_text() == '{}'


@pytest.mark.parametrize('password', [None, ''])
def test_password_never_comes_from_environment(monkeypatch, tmp_path, password):
    monkeypatch.setenv('GARMIN_PASSWORD', 'old-secret')
    monkeypatch.setattr(garmin_auth, 'token_path', lambda: tmp_path / 'missing.json')
    with pytest.raises(garmin_auth.GarminAuthError, match='python -m trainer setup'):
        garmin_auth.ensure_token('runner@example.com', password)


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
