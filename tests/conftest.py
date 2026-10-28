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
