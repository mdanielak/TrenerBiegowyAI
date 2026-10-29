# -*- coding: utf-8 -*-
"""Łączenie z Garminem w przeglądarce (bez sieci: fałszywy klient Garmina)."""
import re

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from services import garmin_setup
from services.data_extract import SnapshotReadResult, SnapshotStatus
from tests.test_api import _report

pytestmark = pytest.mark.usefixtures("testclient_sockets")

PASSWORD = "Bardzo-Tajne-123"


class _Client:
    def __init__(self):
        self.dumped = None

    def dump(self, path):
        self.dumped = path
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"token": "t"}')


def _factory(mfa=False, fail=None, bad_code=False):
    def build(email, password, return_on_mfa=False):
        class Api:
            client = _Client()

            def login(self):
                if fail:
                    raise RuntimeError(fail)
                return ("needs_mfa", {"state": 1}) if mfa else (None, None)

            def resume_login(self, state, code):
                if bad_code:
                    raise RuntimeError("Invalid MFA code")
                assert state == {"state": 1}

        assert return_on_mfa is True
        return Api()
    return build


def test_login_without_mfa_saves_only_the_token(monkeypatch, tmp_path):
    monkeypatch.setattr("trainer.garmin_auth.ensure_garmindb_config", lambda email: True)

    assert garmin_setup.start_login("ala@example.com", PASSWORD, garmin_factory=_factory()) == ("done", None)

    from trainer.garmin_auth import token_path
    assert token_path().is_file()
    assert PASSWORD not in token_path().read_text(encoding="utf-8")


def test_mfa_is_completed_in_a_second_step(monkeypatch):
    monkeypatch.setattr("trainer.garmin_auth.ensure_garmindb_config", lambda email: True)

    outcome, pending = garmin_setup.start_login("ala@example.com", PASSWORD, garmin_factory=_factory(mfa=True))

    assert outcome == "mfa" and pending
    assert garmin_setup.complete_mfa(pending, " 123 456 ") == "ala@example.com"
    with pytest.raises(garmin_setup.GarminSetupError, match="wygasło"):
        garmin_setup.complete_mfa(pending, "123456")


def test_errors_are_explained_without_details(monkeypatch):
    with pytest.raises(garmin_setup.GarminSetupError, match="odrzucił e-mail lub hasło"):
        garmin_setup.start_login("ala@example.com", PASSWORD, garmin_factory=_factory(fail="401 Unauthorized"))
    with pytest.raises(garmin_setup.GarminSetupError, match="Podaj e-mail"):
        garmin_setup.start_login("bez-malpy", PASSWORD, garmin_factory=_factory())
    _, pending = garmin_setup.start_login("ala@example.com", PASSWORD, garmin_factory=_factory(mfa=True, bad_code=True))
    with pytest.raises(garmin_setup.GarminSetupError, match="cyfr"):
        garmin_setup.complete_mfa(pending, "abc")


def test_pending_logins_expire(monkeypatch):
    _, pending = garmin_setup.start_login("ala@example.com", PASSWORD, garmin_factory=_factory(mfa=True))
    garmin_setup._cleanup(now=garmin_setup._PENDING[pending].created + garmin_setup.PENDING_TTL + 1)

    with pytest.raises(garmin_setup.GarminSetupError, match="wygasło"):
        garmin_setup.complete_mfa(pending, "123456")


def test_browser_flow_with_mfa_then_offers_the_first_download(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("services.garmin_setup.start_login",
                        lambda email, password: calls.append(("start", email, bool(password))) or ("mfa", "p1"))
    monkeypatch.setattr("services.garmin_setup.complete_mfa",
                        lambda pending, code: calls.append(("mfa", pending, code)) or "ala@example.com")
    monkeypatch.setattr("services.garmin_setup.import_profile", lambda email: calls.append(("import", email)) or {})

    token_state = {"value": False}
    app = create_app(
        report_provider=lambda: _report(status="profile_missing"),
        profile_provider=lambda: {"name": "Ala", "hr_max": 190},
        garmin_token_check=lambda: token_state["value"],
        snapshot_provider=lambda: SnapshotReadResult(status=SnapshotStatus.MISSING, data=None),
    )
    client = TestClient(app)

    assert client.get("/", follow_redirects=False).headers["location"] == "/setup/garmin"
    page = client.get("/setup/garmin").text
    assert "Zaloguj się do Garmin Connect" in page
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    headers = {"Origin": "http://testserver"}

    mfa_page = client.post("/setup/garmin", data={"csrf_token": token, "email": "ala@example.com",
                                                  "password": PASSWORD}, headers=headers)
    assert "Wpisz kod weryfikacyjny" in mfa_page.text and PASSWORD not in mfa_page.text
    done = client.post("/setup/garmin/mfa", data={"csrf_token": token, "pending": "p1", "code": "123456",
                                                  "email": "ala@example.com"}, headers=headers, follow_redirects=False)

    assert done.headers["location"] == "/setup/garmin?connected=1"
    assert calls == [("start", "ala@example.com", True), ("mfa", "p1", "123456"), ("import", "ala@example.com")]
    token_state["value"] = True
    connected = client.get("/setup/garmin?connected=1").text
    assert "Zegarek połączony" in connected and "Pobierz dane z zegarka" in connected and "190 bpm" in connected


def test_login_form_rejects_forged_posts(tmp_path):
    client = TestClient(create_app(report_provider=lambda: _report(), garmin_token_check=lambda: False,
                                   snapshot_provider=lambda: SnapshotReadResult(status=SnapshotStatus.MISSING, data=None)))
    response = client.post("/setup/garmin", data={"csrf_token": "x", "email": "a@b.pl", "password": "p"},
                           headers={"Origin": "http://testserver"})
    assert response.status_code == 403
