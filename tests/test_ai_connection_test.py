import json

import httpx
import pytest

from ai.connection_test import AIConnectionTestError, check_connection


def transport(monkeypatch, handler):
    monkeypatch.setattr('ai.connection_test.DefaultHttpxClient',
                        lambda **kw: httpx.Client(transport=httpx.MockTransport(handler), **kw))


def test_connection_sends_only_synthetic_message(monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        assert request.headers['Authorization'] == 'Bearer test-secret'
        assert request.extensions['timeout']['read'] == 20.0
        return httpx.Response(200, json={'choices': [{'message': {'content': 'OK', 'role': 'assistant'}}]})
    transport(monkeypatch, handler)
    check_connection(base_url='https://example.test/v1', api_key='test-secret', model='selected-model')
    assert len(requests) == 1
    assert str(requests[0].url) == 'https://example.test/v1/chat/completions'
    assert json.loads(requests[0].content) == {
        'model': 'selected-model',
        'messages': [{'role': 'user', 'content': 'Connection test. Reply only OK.'}],
    }


@pytest.mark.parametrize('status,message', [
    (400, 'odrzuciło żądanie'), (401, 'odrzuciło klucz'), (403, 'Brak uprawnień'),
    (404, 'Nie znaleziono'), (429, 'Limit zapytań'), (500, 'API zwróciło błąd'),
    (302, 'API zwróciło błąd'),
])
def test_api_errors_are_sanitized_without_retries_or_redirects(monkeypatch, status, message):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={'Location': 'https://other.test'},
                              json={'error': {'message': 'test-secret private response'}})
    transport(monkeypatch, handler)
    with pytest.raises(AIConnectionTestError, match=message) as exc:
        check_connection(base_url='https://example.test/v1', api_key='test-secret', model='model')
    assert 'test-secret' not in str(exc.value)
    assert 'private response' not in str(exc.value)
    assert len(calls) == 1


@pytest.mark.parametrize('error,message', [
    (httpx.ReadTimeout, 'czas oczekiwania'), (httpx.ConnectError, 'Nie można połączyć'),
])
def test_network_errors_are_sanitized(monkeypatch, error, message):
    calls = []
    def handler(request):
        calls.append(request)
        raise error('test-secret', request=request)
    transport(monkeypatch, handler)
    with pytest.raises(AIConnectionTestError, match=message) as exc:
        check_connection(base_url='https://example.test/v1', api_key='test-secret', model='model')
    assert 'test-secret' not in str(exc.value)
    assert len(calls) == 1


@pytest.mark.parametrize('body', [{'choices': []}, {'choices': [{'message': {'content': ''}}]}, {'bad': 'response'}])
def test_empty_or_malformed_response_is_not_success(monkeypatch, body):
    transport(monkeypatch, lambda request: httpx.Response(200, json=body))
    with pytest.raises(AIConnectionTestError):
        check_connection(base_url='https://example.test/v1', api_key='test-secret', model='model')


def test_gemini_invalid_key_and_missing_funds_get_clear_messages(monkeypatch):
    gemini = [{'error': {'code': 400, 'message': 'API key not valid. Please pass a valid API key.',
                         'status': 'INVALID_ARGUMENT', 'details': [{'reason': 'API_KEY_INVALID'}]}}]
    transport(monkeypatch, lambda request: httpx.Response(400, json=gemini))
    with pytest.raises(AIConnectionTestError, match='Klucz API jest nieprawidłowy') as invalid:
        check_connection(base_url='https://example.test/v1', api_key='AIzaSecret', model='gemini-3.8-flash')
    assert 'Please pass' not in str(invalid.value)  # własny komunikat, nie treść dostawcy

    transport(monkeypatch, lambda request: httpx.Response(402, json={'error': {'message': 'Insufficient Balance'}}))
    with pytest.raises(AIConnectionTestError, match='Brak środków'):
        check_connection(base_url='https://example.test/v1', api_key='sk-secret', model='deepseek-flash')
