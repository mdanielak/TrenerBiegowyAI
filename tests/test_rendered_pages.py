# -*- coding: utf-8 -*-
"""Każda strona dashboardu renderuje się bez typowych wpadek w tekście widocznym dla użytkownika."""
import html
import re

import pytest
from fastapi.testclient import TestClient

from services.stats import build_stats_report
from tests.test_api import _week_report
from tests.test_api_plan import _app, _plan
from tests.test_services_goal import _report as _goal_report, _run
from tests.test_services_stats import TODAY, _data, _snapshot

pytestmark = pytest.mark.usefixtures("testclient_sockets")

PAGES = ("/", "/plan", "/week", "/analysis", "/settings", "/settings/ai", "/stats?weeks=4", "/goal", "/journal", "/wizard")

_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S)
# Liczba z kropką dziesiętną tuż przed jednostką, np. „15.0 km”.
_DOT_DECIMAL = re.compile(r"\b\d+\.\d+\s*(km|h|min|bpm|ms|z)\b")
# Błędna odmiana po liczbie, np. „1 treningów”, „3 treningów”, „1 tygodni”.
# „1” musi stać samodzielnie (21 treningów jest poprawne); 2–4 nie może być częścią 12–14.
_BAD_PLURAL = re.compile(r"((?<![\d,])1 (treningów|treningi|tygodni|tygodnie)"
                         r"|(?<![1,])[2-4] (treningów|tygodni))\b")
_PLACEHOLDERS = re.compile(r"\b(None|nan|undefined|null)\b")


def _visible_text(page: str) -> str:
    return html.unescape(_TAGS.sub(" ", page))


@pytest.fixture
def client(tmp_path):
    app = _app(
        tmp_path,
        plan=_plan(),
        week_report_provider=lambda: _week_report(warnings=["snapshot_stale", "snapshot_activities_may_be_incomplete"]),
        stats_report_provider=lambda weeks: build_stats_report(snapshot=_snapshot(_data()), today=TODAY, weeks=weeks),
        ai_env_path=tmp_path / ".env",
        goal_report_provider=lambda: _goal_report([_run("2026-10-25", 10.2, 55)]),
        journal_path=tmp_path / "journal.jsonl",
    )
    return TestClient(app)


@pytest.mark.parametrize("path", PAGES)
def test_page_text_has_no_formatting_slips(client, path):
    response = client.get(path)
    assert response.status_code == 200, path
    text = _visible_text(response.text)

    assert "`" not in text, "Odwrotny apostrof w tekście — polecenia pokazuj w <code>."
    assert not _DOT_DECIMAL.findall(text), "Kropka dziesiętna zamiast przecinka."
    assert not _BAD_PLURAL.findall(text), "Błędna odmiana rzeczownika po liczbie."
    assert not _PLACEHOLDERS.findall(text), "Techniczna wartość zastępcza zamiast myślnika."


def test_visible_text_helper_drops_markup_and_code_attributes():
    assert _visible_text('<p title="15.0 km">8 km</p>').strip() == "8 km"


@pytest.mark.parametrize("bad", ["15.0 km", "6.1 h", "1 treningów", "3 treningów", "22 treningów", "1 tygodni", "None"])
def test_detectors_catch_known_slips(bad):
    assert _DOT_DECIMAL.search(bad) or _BAD_PLURAL.search(bad) or _PLACEHOLDERS.search(bad)


@pytest.mark.parametrize("good", ["15 km", "6,1 h", "1 trening", "3 treningi", "12 treningów", "21 treningów", "4 tygodnie"])
def test_detectors_accept_correct_polish(good):
    assert not (_DOT_DECIMAL.search(good) or _BAD_PLURAL.search(good) or _PLACEHOLDERS.search(good))


def test_base_template_survives_a_missing_badge_helper():
    """Serwer na starszym kodzie (bez funkcji plakietki) nie może zwracać 500 na każdej stronie."""
    from types import SimpleNamespace

    from api.main import _TEMPLATES

    env = _TEMPLATES.env
    helper = env.globals.pop("sidebar_ai_badge")
    try:
        html = env.get_template("_base.html").render(request=SimpleNamespace(state=SimpleNamespace()))
    finally:
        env.globals["sidebar_ai_badge"] = helper
    assert "Trener Biegowy" in html and "ai-badge" not in html
