"""Wspólna konfiguracja testów: testy muszą być hermetyczne (bez sieci).

Logowanie do Garmin Connect w teście skutkowało realnymi żądaniami i
odpowiedziami 429 (limit po stronie Garmina), co groziło zablokowaniem
konta używanego do codziennej synchronizacji. Blokujemy więc warstwę
gniazd dla całego zestawu testów.

Test, który świadomie wymaga sieci, oznacz markerem:

    @pytest.mark.allow_network

Dodatkowo izolujemy magazyn tokenów Garmina. Bez tego testy czytały
prawdziwy ~/.GarminDb/garmin_tokens.json z katalogu domowego, więc ich
wynik zależał od tego, czy użytkownik jest zalogowany, a kreator mógł
nadpisać realną konfigurację GarminDB.
"""
from __future__ import annotations

import socket

import pytest


class NetworkAccessBlocked(RuntimeError):
    """Test próbował otworzyć połączenie sieciowe."""


# Zapisane przed blokadą sieci: TestClient potrzebuje lokalnej pary gniazd.
_ORIGINAL_CONNECT = socket.socket.connect

_MESSAGE = (
    "Test próbował połączenia sieciowego. Zamockuj klienta Garmina "
    "(np. monkeypatch.setattr('trainer.garmin_workouts.GarminWorkout', ...)) "
    "albo oznacz test markerem @pytest.mark.allow_network."
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "allow_network: test świadomie korzysta z sieci (domyślnie zablokowana)."
    )


@pytest.fixture(autouse=True)
def _block_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Zablokuj wychodzące połączenia, chyba że test jawnie ich wymaga."""
    if request.node.get_closest_marker("allow_network"):
        return

    def blocked(*args, **kwargs):
        raise NetworkAccessBlocked(_MESSAGE)

    monkeypatch.setattr(socket.socket, "connect", blocked, raising=False)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked, raising=False)
    monkeypatch.setattr(socket, "create_connection", blocked, raising=False)
    monkeypatch.setattr(socket, "getaddrinfo", blocked, raising=False)
    # curl_cffi uses native libcurl and bypasses Python's socket guards.
    try:
        from curl_cffi.requests import Session
    except ImportError:
        pass
    else:
        monkeypatch.setattr(Session, "request", blocked)


@pytest.fixture(autouse=True)
def _isolate_garmin_tokens(tmp_path_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Przekieruj magazyn tokenów Garmina na katalog tymczasowy.

    Domyślnie katalog jest pusty, więc testy startują ze stanu "brak
    tokena". Test, który potrzebuje istniejącego tokena, tworzy go sam.
    """
    from trainer import garmin_auth

    token_dir = tmp_path_factory.mktemp("garmindb")
    monkeypatch.setattr(garmin_auth, "token_path",
                        lambda: token_dir / "garmin_tokens.json")


@pytest.fixture
def testclient_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pozwól TestClient utworzyć wyłącznie jego wewnętrzną parę gniazd na 127.0.0.1."""
    def socketpair():
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _ORIGINAL_CONNECT(client, listener.getsockname())
        server, _ = listener.accept()
        listener.close()
        return server, client

    monkeypatch.setattr(socket, "socketpair", socketpair)


@pytest.fixture(autouse=True)
def _isolate_jobs(tmp_path_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Start aplikacji w teście nie oznacza ani nie kasuje prawdziwych zadań z local/jobs (np. trwającej synchronizacji)."""
    monkeypatch.setattr("api.main.JOBS_DIR", tmp_path_factory.mktemp("jobs"))


@pytest.fixture(autouse=True)
def _isolate_recommendations(tmp_path_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rozmowa z trenerem w testach nie czyta ani nie zapisuje prawdziwego local/recommendations.jsonl."""
    monkeypatch.setattr("services.recommendations.RECOMMENDATIONS_PATH",
                        tmp_path_factory.mktemp("recommendations") / "recommendations.jsonl")


@pytest.fixture(autouse=True)
def _isolate_reviews(tmp_path_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Oceny treningów z testów nie trafiają do prawdziwego local/workout-reviews.jsonl."""
    monkeypatch.setattr("services.workout_reviews.REVIEWS_PATH", tmp_path_factory.mktemp("reviews") / "reviews.jsonl")


@pytest.fixture(autouse=True)
def _isolate_journal(tmp_path_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Testy nigdy nie czytają ani nie piszą prawdziwego local/journal.jsonl."""
    path = tmp_path_factory.mktemp("journal") / "journal.jsonl"
    monkeypatch.setattr("services.journal.JOURNAL_PATH", path)
    monkeypatch.setattr("api.main.JOURNAL_PATH", path, raising=False)


@pytest.fixture(autouse=True)
def _isolate_plans_and_registry(tmp_path_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Domyślnie testy widzą pusty katalog planów i pusty rejestr Garmina, nie prawdziwe pliki.

    Test, który potrzebuje własnych plików, nadal podmienia te ścieżki sam.
    """
    root = tmp_path_factory.mktemp("isolated")
    monkeypatch.setattr("services.plan_files.TRAINING_PLANS_DIR", root / "training-plans")
    monkeypatch.setattr("services.workout_registry.REGISTRY_PATH", root / "workout-registry.jsonl")


@pytest.fixture(autouse=True)
def _isolate_ai_status(tmp_path_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Wynik testu połączenia z AI w testach nigdy nie trafia do prawdziwego local/."""
    path = tmp_path_factory.mktemp("ai_status") / "ai_status.json"
    monkeypatch.setattr("services.ai_status.AI_STATUS_PATH", path)
    monkeypatch.setattr("api.main.AI_STATUS_PATH", path, raising=False)


@pytest.fixture(autouse=True)
def _isolate_preferences(tmp_path_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Przerwy i dostępność w testach nigdy nie zmieniają prawdziwego local/training_preferences.json."""
    from types import SimpleNamespace

    monkeypatch.setattr("trainer.preferences.SETTINGS", SimpleNamespace(local_dir=tmp_path_factory.mktemp("preferences")))


@pytest.fixture(autouse=True)
def _isolate_ai_notes(tmp_path_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Wiadomości dla AI w testach nie trafiają do prawdziwego local/ai-notes.jsonl."""
    monkeypatch.setattr("services.ai_notes.NOTES_PATH", tmp_path_factory.mktemp("ai_notes") / "ai-notes.jsonl")


@pytest.fixture(autouse=True)
def _isolate_locks(tmp_path_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Blokady w testach nie mogą kolidować z działającym dashboardem lub synchronizacją w local/."""
    from types import SimpleNamespace

    monkeypatch.setattr("services.locking.SETTINGS", SimpleNamespace(local_dir=tmp_path_factory.mktemp("locks")))
