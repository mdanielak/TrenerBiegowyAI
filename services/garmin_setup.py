# -*- coding: utf-8 -*-
"""Połączenie z Garminem z poziomu przeglądarki, z obsługą kodu MFA w dwóch krokach.

Hasło żyje wyłącznie w pamięci procesu na czas logowania i nigdy nie trafia na
dysk ani do logów. Po udanym logowaniu zostaje tylko token biblioteki (tak samo
jak po ``python -m trainer setup``), a oczekujące logowanie z MFA wygasa po
PENDING_TTL. Serwer działa wyłącznie na 127.0.0.1.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path

PENDING_TTL = 10 * 60
_LIMITS = (("age", "age"), ("weight", "weight_kg"), ("height", "height_cm"), ("hr_max", "hr_max"),
           ("hr_rest", "hr_rest"), ("lactate_threshold_hr", "lactate_threshold_hr"),
           ("vo2max_running", "vo2max_running"), ("sex", "sex"))


@dataclass
class _Pending:
    api: object
    state: object
    email: str
    created: float


_PENDING: dict[str, _Pending] = {}
_LOCK = threading.Lock()


class GarminSetupError(Exception):
    """Komunikat dla użytkownika, bez hasła i bez szczegółów odpowiedzi Garmina.

    ``restart`` znaczy, że oczekujące logowanie przepadło i trzeba wpisać hasło od nowa.
    """

    def __init__(self, message: str, *, restart: bool = False) -> None:
        super().__init__(message)
        self.restart = restart


def _friendly(exc) -> str:
    text = str(exc).lower()
    if "401" in text or "credential" in text or "password" in text or "authentication" in text:
        return "Garmin odrzucił e-mail lub hasło. Sprawdź je i spróbuj ponownie."
    if "mfa" in text or "code" in text:
        return "Kod weryfikacyjny jest nieprawidłowy albo wygasł. Zaloguj się ponownie."
    if "429" in text or "too many" in text:
        return "Garmin chwilowo blokuje zbyt wiele prób logowania. Odczekaj kilkanaście minut."
    if "connection" in text or "timeout" in text or "resolve" in text:
        return "Brak połączenia z Garmin Connect. Sprawdź internet i spróbuj ponownie."
    return "Logowanie do Garmina się nie udało. Spróbuj ponownie za chwilę."


def _cleanup(now=None) -> None:
    now = now or time.monotonic()
    with _LOCK:
        for key in [key for key, item in _PENDING.items() if now - item.created > PENDING_TTL]:
            _PENDING.pop(key, None)


def start_login(email: str, password: str, *, garmin_factory=None) -> tuple[str, str | None]:
    """('done', None) po zalogowaniu albo ('mfa', identyfikator) gdy Garmin chce kod."""
    email = (email or "").strip()
    if "@" not in email or not password:
        raise GarminSetupError("Podaj e-mail i hasło do konta Garmin Connect.")
    _cleanup()
    if garmin_factory is None:
        from garminconnect import Garmin as garmin_factory
    try:
        api = garmin_factory(email, password, return_on_mfa=True)
        status, state = api.login()
    except Exception as exc:  # noqa: BLE001 - każdy błąd biblioteki zamieniamy na zrozumiały komunikat
        raise GarminSetupError(_friendly(exc)) from None
    if status == "needs_mfa":
        token = secrets.token_urlsafe(24)
        with _LOCK:
            _PENDING[token] = _Pending(api, state, email, time.monotonic())
        return "mfa", token
    _finish(api, email)
    return "done", None


def complete_mfa(pending_id: str, code: str) -> str:
    """Dokończ logowanie kodem MFA; zwraca e-mail konta."""
    _cleanup()
    code = "".join(str(code or "").split())
    if not code.isdigit():
        # Przed zdjęciem logowania z kolejki: literówka pozwala wpisać kod jeszcze raz.
        with _LOCK:
            known = (pending_id or "") in _PENDING
        raise GarminSetupError("Kod weryfikacyjny składa się z cyfr.", restart=not known)
    with _LOCK:
        pending = _PENDING.pop(pending_id or "", None)
    if pending is None:
        raise GarminSetupError("Logowanie wygasło. Wpisz e-mail i hasło jeszcze raz.", restart=True)
    try:
        pending.api.resume_login(pending.state, code)
    except Exception as exc:  # noqa: BLE001 - Garmin unieważnia logowanie po odrzuconym kodzie
        raise GarminSetupError(_friendly(exc), restart=True) from None
    _finish(pending.api, pending.email)
    return pending.email


def _finish(api, email) -> None:
    """Zapisz token jak kreator w terminalu i przygotuj konfigurację GarminDB."""
    from trainer.garmin_auth import ensure_garmindb_config, secure_token_dir, token_path

    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        api.client.dump(str(path))
    except Exception as exc:  # noqa: BLE001
        raise GarminSetupError("Zalogowano, ale nie udało się zapisać tokenu na dysku.") from exc
    secure_token_dir(path.parent)
    ensure_garmindb_config(email)


def import_profile(*, email: str | None) -> dict:
    """Pobierz profil z Garmina do local/profile.json i zapisz e-mail w .env.

    Bez ``email`` (odświeżenie z zapisanego tokenu) plik .env zostaje nietknięty.

    Zwraca słownik tego, co udało się pobrać (do pokazania użytkownikowi).
    Dni treningowe ustawia tylko wtedy, gdy żaden dzień nie jest jeszcze dostępny.
    """
    from trainer import preferences, profile_store
    from trainer.config import PROJECT_ROOT
    from trainer.garmin_auth import ensure_token
    from trainer.garmin_profile import fetch_snapshot
    from trainer.setup_wizard import _weekly_proposal, _write_env

    try:
        profile = profile_store.load_profile()
    except FileNotFoundError:
        profile = {}
        profile_store.save_profile(profile)
    api = ensure_token()  # z zapisanego tokenu: profil konta jest wtedy w pełni wczytany
    try:
        snapshot = fetch_snapshot(api) or {}
    except Exception:  # noqa: BLE001 - brak danych profilu nie blokuje połączenia
        snapshot = {}
    fields = {target: snapshot[source] for source, target in _LIMITS if source in snapshot}
    if not profile.get("name"):
        try:
            name = api.get_full_name()
        except Exception:  # noqa: BLE001
            name = None
        if name:
            fields["name"] = str(name).split()[0]
    if fields:
        profile_store.update_profile(**fields)
    if snapshot.get("hr_zone_floors") and fields.get("hr_max"):
        profile_store.set_hr_zones(snapshot["hr_zone_floors"], fields["hr_max"], "Garmin Connect — dane profilu")

    days = preferences.load_preferences().get("days", {})
    if not any((slot or {}).get("available") for slot in days.values()):
        proposal = _weekly_proposal(days, snapshot)
        for key, slot in (proposal or {}).items():
            preferences.set_weekly_availability(key, slot.get("available", False),
                                                slot.get("min_minutes", 0), slot.get("max_minutes", 0))

    # Tylko e-mail: inne wpisy .env (np. własny HEALTH_DATA_DIR) zostają bez zmian.
    if email:
        _write_env(Path(PROJECT_ROOT) / ".env", {"GARMIN_EMAIL": email})
    return fields
