"""Wspólne uwierzytelnianie Garmin Connect i przygotowanie GarminDB."""
import json
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from .config import GARMIN_EMAIL


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
        return api
    except Exception as exc:
        raise _auth_error(exc) from exc


def ensure_garmindb_config(email):
    """Utwórz neutralny config GarminDB, jeśli użytkownik jeszcze go nie ma."""
    config_path = token_path().parent / "GarminConnectConfig.json"
    if config_path.exists():
        return False
    import garmindb
    example_path = Path(garmindb.__file__).parent / "GarminConnectConfig.json.example"
    config = json.loads(example_path.read_text(encoding="utf-8"))
    config["credentials"]["user"] = email
    config["credentials"]["password"] = ""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return True
