# -*- coding: utf-8 -*-
"""Motyw jasny i ciemny: ciasteczko, atrybut na <html> i bezpieczny powrót."""
import pytest
from fastapi.testclient import TestClient

from api.main import _safe_next, create_app
from tests.test_api import _report

pytestmark = pytest.mark.usefixtures("testclient_sockets")


def _client():
    return TestClient(create_app(report_provider=lambda: _report()))


def test_auto_follows_the_system_and_offers_the_switch():
    page = _client().get("/").text
    assert '<html lang="pl">' in page and 'content="light dark"' in page
    assert 'href="/theme?set=dark&amp;next=/"' in page and 'aria-current="true" class="is-active">Auto' in page


def test_choosing_dark_is_remembered_and_rendered_on_the_server():
    client = _client()
    response = client.get("/theme?set=dark&next=/plan", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/plan"
    assert "theme=dark" in response.headers["set-cookie"] and "HttpOnly" in response.headers["set-cookie"]

    page = client.get("/").text
    assert '<html lang="pl" data-theme="dark">' in page and 'content="dark"' in page
    assert 'aria-current="true" class="is-active">Ciemny' in page


def test_auto_clears_the_choice():
    client = _client()
    client.get("/theme?set=light")
    response = client.get("/theme?set=auto", follow_redirects=False)
    assert 'theme=""' in response.headers["set-cookie"] or "Max-Age=0" in response.headers["set-cookie"]


def test_unknown_values_fall_back_to_auto():
    client = _client()
    client.cookies.set("theme", "neon")
    assert '<html lang="pl">' in client.get("/").text


@pytest.mark.parametrize("value", ["https://evil.example", "//evil.example", "/\\evil.example", "", None, "plan"])
def test_return_address_never_leaves_the_app(value):
    assert _safe_next(value) == "/"


def test_return_address_keeps_local_pages_and_queries():
    assert _safe_next("/plan?week=2026-10-26") == "/plan?week=2026-10-26"
