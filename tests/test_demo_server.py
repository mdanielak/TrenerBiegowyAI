# -*- coding: utf-8 -*-
"""Aplikacja demonstracyjna do zrzutów w README działa na danych przykładowych."""
import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.usefixtures("testclient_sockets")


def _demo_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "demo_server.py"
    spec = importlib.util.spec_from_file_location("demo_server", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_home_page_shows_sample_data_in_both_themes():
    client = TestClient(_demo_module().build_demo_app())
    page = client.get("/").text
    assert "Łatwy 45 min – Z2" in page and "AI połączone · Google" in page
    assert "Uważaj dziś na intensywność" in page
    assert page.index("Uważaj dziś na intensywność") < page.index("Sygnały z organizmu") < page.index("Trening na dziś")
    client.get("/theme?set=dark")
    assert 'data-theme="dark"' in client.get("/").text
