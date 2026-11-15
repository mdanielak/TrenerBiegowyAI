# -*- coding: utf-8 -*-
"""Informacja o nowej wersji wskazuje plik aktualizacji właściwy dla systemu."""
import sys

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from tests.test_api import _report

pytestmark = pytest.mark.usefixtures("testclient_sockets")


@pytest.mark.parametrize("platform, command", [("win32", "update.bat"), ("linux", "./update.sh")])
def test_new_version_note_names_the_update_file_for_this_system(monkeypatch, tmp_path, platform, command):
    app = create_app(report_provider=lambda: _report(), profile_provider=lambda: {"target_race": "10 km"},
                     runner_provider=lambda: None, journal_path=tmp_path / "journal.jsonl")
    app.state.update_available = "9.9.9"
    monkeypatch.setattr(sys, "platform", platform)
    page = TestClient(app).get("/").text
    assert "Jest nowa wersja 9.9.9." in page and f"<code>{command}</code>" in page
