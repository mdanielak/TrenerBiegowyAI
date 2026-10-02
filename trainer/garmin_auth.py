"""Wspólne uwierzytelnianie Garmin Connect i przygotowanie GarminDB."""
import json
from pathlib import Path

from garminconnect import Garmin

from .config import GARMIN_EMAIL, GARMIN_PASSWORD


class GarminAuthError(RuntimeError):
    """Brak danych lub niemożliwe odnowienie uwierzytelnienia Garmin."""


def token_path() -> Path:
    return Path.home() / ".GarminDb" / "garmin_tokens.json"


def has_token() -> bool:
    path = token_path()
    return path.is_file() and path.stat().st_size > 0


def ensure_token(email=None, password=None):
    """Zaloguj przez zapisany token albo utwórz/odśwież go hasłem."""
    path = token_path()
    if has_token():
        try:
            api = Garmin()
            api.login(str(path))
            return api
        except Exception:
            pass
    email = email or GARMIN_EMAIL
    password = password or GARMIN_PASSWORD
    missing = []
    if not email:
        missing.append("adresu e-mail Garmin")
    if not password:
        missing.append("hasła Garmin (GARMIN_PASSWORD)")
    if missing:
        raise GarminAuthError(
            f"Brakuje {', '.join(missing)}. Uzupełnij GARMIN_PASSWORD w pliku .env "
            "albo uruchom python -m trainer setup."
        )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        api = Garmin(email, password)
        api.login(str(path))
        return api
    except Exception as exc:
        raise GarminAuthError(f"Nie udało się zalogować do Garmin Connect: {exc}") from exc


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
