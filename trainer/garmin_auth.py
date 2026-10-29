"""Wspólne uwierzytelnianie Garmin Connect i przygotowanie GarminDB."""
import json
import logging
from datetime import date, timedelta
import os
import subprocess
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from .config import GARMIN_EMAIL
from .files import write_atomic


class GarminAuthError(RuntimeError):
    """Brak danych lub niemożliwe odnowienie uwierzytelnienia Garmin."""

    def __init__(self, message, *, retry_credentials=False):
        super().__init__(message)
        self.retry_credentials = retry_credentials


def _auth_error(exc):
    """Rozróżnij odmowę uwierzytelnienia od blokady i awarii połączenia.

    Nie wypisuj surowej odpowiedzi SSO: może zawierać dane sesji.
    Oryginalny wyjątek zachowujemy jako przyczynę (raise ... from exc).
    """
    if isinstance(exc, GarminConnectTooManyRequestsError):
        return GarminAuthError(
            "Garmin ograniczył lub zablokował logowanie (HTTP 429). "
            "To nie potwierdza błędnego hasła. Nie ponawiam automatycznie; "
            "spróbuj później. Zmiana sieci nie gwarantuje rozwiązania."
        )
    if isinstance(exc, GarminConnectAuthenticationError):
        if "mfa" in str(exc).lower():
            return GarminAuthError(
                "Nie ukończono weryfikacji MFA Garmin. Sprawdź kod i sposób "
                "weryfikacji konta; nie ponawiam logowania hasłem."
            )
        return GarminAuthError(
            "Garmin odrzucił uwierzytelnienie. Sprawdź e-mail i hasło oraz "
            "logowanie na https://connect.garmin.com/ (możliwa blokada konta).",
            retry_credentials=True,
        )
    if isinstance(exc, GarminConnectConnectionError):
        return GarminAuthError(
            "Nie udało się ukończyć połączenia/logowania SSO Garmin. "
            "To nie potwierdza błędnego hasła. Sprawdź logowanie na "
            "https://connect.garmin.com/. Nie ponawiam automatycznie."
        )
    return GarminAuthError(
        f"Logowanie przerwane przez błąd {type(exc).__name__}. "
        "Nie ponawiam automatycznie."
    )


def token_path() -> Path:
    return Path.home() / ".GarminDb" / "garmin_tokens.json"


def has_token() -> bool:
    path = token_path()
    return path.is_file() and path.stat().st_size > 0


def ensure_token(email=None, password=None, prompt_mfa=None):
    """Użyj tokenu lub hasła przekazanego jawnie podczas logowania.

    Nie pobieraj hasła z konfiguracji ani nie pytaj o nie w procesie serwera.
    Brak działającego tokenu wymaga interaktywnego uruchomienia kreatora.
    """
    path = token_path()
    if has_token():
        try:
            api = Garmin()
            api.login(str(path))
            secure_token_dir()
            return api
        except (GarminConnectAuthenticationError, FileNotFoundError, ValueError):
            # Tylko nieprawidłowy/wygasły token uzasadnia logowanie hasłem.
            pass
        except Exception as exc:
            raise _auth_error(exc) from exc
    email = GARMIN_EMAIL if email is None else email
    if not email or not password:
        raise GarminAuthError(
            "Brak działającego tokenu Garmin. Zaloguj ponownie: python -m trainer setup. "
            "Hasło podaj tylko w interaktywnym terminalu; nie zapisuj go w .env.",
            retry_credentials=True,
        )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if prompt_mfa is not None:
            api = Garmin(email, password, prompt_mfa=prompt_mfa)
        else:
            api = Garmin(email, password)
        # Biblioteka sama obsługuje strategie SSO, w tym portal.
        # Nie uruchamiaj całego łańcucha ponownie po błędzie.
        api.login(str(path))
        secure_token_dir()
        return api
    except Exception as exc:
        raise _auth_error(exc) from exc


# Przykład GarminDB pobiera wszystko od 31.12.2019: przy pierwszym pobraniu to godziny pracy
# i przerwanie przez limit czasu. Aplikacja czyta 120 dni aktywności i 90 dni pomiarów.
DOWNLOAD_HISTORY_DAYS = 120
_EXAMPLE_START = "12/31/2019"
_START_KEYS = ("weight_start_date", "sleep_start_date", "rhr_start_date", "hrv_start_date", "monitoring_start_date")


def _recent_history(config, today=None) -> bool:
    """Przestaw nietknięte daty przykładu na okno aplikacji; własne daty zostają."""
    start = ((today or date.today()) - timedelta(days=DOWNLOAD_HISTORY_DAYS)).strftime("%m/%d/%Y")
    data = config.setdefault("data", {})
    changed = False
    for key in _START_KEYS:
        if data.get(key, _EXAMPLE_START) == _EXAMPLE_START:
            data[key] = start
            changed = True
    return changed


def ensure_garmindb_config(email):
    """Utwórz neutralny config GarminDB, jeśli użytkownik jeszcze go nie ma."""
    config_path = token_path().parent / "GarminConnectConfig.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if _recent_history(config):
            write_atomic(config_path, json.dumps(config, indent=2) + "\n")
        return False
    import garmindb
    example_path = Path(garmindb.__file__).parent / "GarminConnectConfig.json.example"
    config = json.loads(example_path.read_text(encoding="utf-8"))
    config["credentials"]["user"] = email
    config["credentials"]["password"] = ""
    _recent_history(config)
    write_atomic(config_path, json.dumps(config, indent=2) + "\n")
    return True


_logger = logging.getLogger(__name__)
_SECURED = set()


# Szerokie grupy, przez które token mógłby czytać ktoś inny na tym samym komputerze:
# Wszyscy (Everyone), Użytkownicy (Users), Uwierzytelnieni użytkownicy.
_BROAD_GROUPS = ("*S-1-1-0", "*S-1-5-32-545", "*S-1-5-11")


def secure_token_dir(directory=None) -> bool:
    """Na Windows: odbierz dostęp do katalogu tokenu innym użytkownikom komputera.

    Dziedziczone uprawnienia zostają zamienione na jawne, a usuwane są tylko szerokie
    grupy. Właściciel, administratorzy i SYSTEM zostają — celowo nie zostawiamy
    „tylko bieżącego użytkownika”, bo to potrafi odciąć dostęp procesom w piaskownicy,
    usłudze czy kopii zapasowej. Pliki tworzone później (odnowiony token) dziedziczą
    to samo. Na Linux/macOS biblioteka sama ustawia 600/700. Błąd tylko trafia do logu.
    """
    if os.name != "nt":
        return False
    target = Path(directory or token_path().parent)
    if str(target) in _SECURED or not target.is_dir():
        return False
    try:
        subprocess.run(["icacls", str(target), "/inheritance:d", "/T", "/Q"],
                       check=True, capture_output=True, timeout=30)
        subprocess.run(["icacls", str(target), "/remove:g", *_BROAD_GROUPS, "/T", "/Q"],
                       check=True, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        _logger.warning("Could not restrict access to the Garmin token directory: %s", type(exc).__name__)
        return False
    _SECURED.add(str(target))
    return True


def disconnect(*, env_path=None) -> list[str]:
    """Odłącz konto: usuń token, wyczyść dane logowania GarminDB i e-mail z .env.

    Dane treningowe (bazy GarminDB, snapshot, plany) zostają. Zwraca listę tego,
    co faktycznie usunięto, do pokazania użytkownikowi.
    """
    removed = []
    path = token_path()
    if path.exists():
        path.unlink()
        removed.append("token Garmina")
    config_path = path.parent / "GarminConnectConfig.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        config = None
    credentials = (config or {}).get("credentials")
    if isinstance(credentials, dict) and any(credentials.get(key) for key in ("user", "password")):
        credentials.update(user="", password="")
        write_atomic(config_path, json.dumps(config, indent=2) + "\n")
        removed.append("dane logowania w konfiguracji GarminDB")
    if env_path is not None:
        try:
            lines = Path(env_path).read_text(encoding="utf-8-sig").splitlines()
        except FileNotFoundError:
            lines = []
        kept = [line for line in lines
                if line.split("=", 1)[0].removeprefix("export ").strip() not in ("GARMIN_EMAIL", "GARMIN_PASSWORD")]
        if len(kept) != len(lines):
            write_atomic(env_path, "\n".join(kept) + ("\n" if kept else ""))
            removed.append("e-mail konta w pliku .env")
    return removed
