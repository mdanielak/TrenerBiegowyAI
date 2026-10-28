"""Interaktywny kreator pierwszej konfiguracji."""
from __future__ import annotations

import os
import sys
import tempfile
import getpass
from pathlib import Path
from typing import Any
import re

from . import profile_store, preferences
from .config import PROJECT_ROOT
from .errors import env_hint
from .garmin_profile import fetch_snapshot
from .garmin_auth import GarminAuthError, ensure_garmindb_config, ensure_token, has_token

# Fallback tylko gdy nie ma zapisanych preferencji ani danych z Garmin Connect.
DEFAULT_TRAINING_MINUTES = (35, 45)
DEFAULT_LONG_TRAINING_MINUTES = (60, 90)
_DAYS = (("mon", "Pon"), ("tue", "Wt"), ("wed", "Śr"), ("thu", "Czw"),
         ("fri", "Pt"), ("sat", "Sob"), ("sun", "Nd"))


def _ask(label, default="", secret=False):
    shown = "****" if secret and default else default
    prompt = f"{label}" + (f" [{shown}]" if shown else "") + ": "
    value = getpass.getpass(prompt) if secret else input(prompt).strip()
    return value if value else default


def _integer(label, default=0, minimum=0, maximum=None):
    valid_default = isinstance(default, int) and not isinstance(default, bool)
    while True:
        value = _ask(label, str(default) if valid_default else "")
        try:
            number = int(value)
            if number < minimum or (maximum is not None and number > maximum):
                raise ValueError
            return number
        except ValueError:
            maximum_text = f" i nie większą niż {maximum}" if maximum is not None else ""
            print(f"Podaj liczbę całkowitą nie mniejszą niż {minimum}{maximum_text}.")


def _choice(label, options, default_index):
    """Pobierz numer opcji, powtarzając pytanie dla nieprawidłowego wyboru."""
    while True:
        value = _ask(label, str(default_index))
        try:
            selected = int(value)
            if 1 <= selected <= len(options):
                return selected
        except ValueError:
            pass
        print(f"Wybierz numer od 1 do {len(options)}.")


def _minutes_range(label, default_min, default_max):
    default = str(default_min) if default_min == default_max else f"{default_min}-{default_max}"
    while True:
        value = _ask(label, default)
        normalized = value.replace("–", "-")
        parts = [part.strip() for part in normalized.split("-")]
        try:
            if len(parts) == 1:
                minimum = maximum = int(parts[0])
            elif len(parts) == 2:
                minimum, maximum = (int(part) for part in parts)
            else:
                raise ValueError
            if 0 <= minimum <= maximum <= 600:
                return minimum, maximum
        except ValueError:
            pass
        print("Podaj minuty jako 30-45 albo 30; zakres musi być od 0 do 600.")


def _yes_no(label, default=False):
    suffix = "T/n" if default else "t/N"
    while True:
        value = input(f"{label} [{suffix}]: ").strip().lower()
        if not value:
            return default
        if value in {"t", "tak", "y", "yes"}:
            return True
        if value in {"n", "nie", "no"}:
            return False
        print("Odpowiedz t albo n.")


def _write_env(path: Path, values: dict[str, str]):
    """Uaktualnij ustawienia, zachowaj obce wpisy i usuń stare hasło Garmin."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        lines = []
    values = {key: str(value) for key, value in values.items()
              if value != "" and key != "GARMIN_PASSWORD"}
    def serialize(key: str, value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError(f"Wartość zmiennej {key} nie może zawierać znaku nowej linii.")
        if re.fullmatch(r"[A-Za-z0-9_./:@+-]+", value):
            return value
        if "'" not in value:
            return "'" + value + "'"
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    seen = set()
    result = []
    for line in lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].removeprefix("export ").strip() if "=" in stripped else ""
        if key == "GARMIN_PASSWORD":
            continue
        if key in values:
            if key not in seen:
                result.append(f"{key}={serialize(key, values[key])}")
                seen.add(key)
        else:
            result.append(line)
    result.extend(f"{key}={serialize(key, value)}" for key, value in values.items() if key not in seen)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".env.", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(result) + "\n")
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
    except BaseException:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise


def _weekly_proposal(local_days: dict, snapshot: dict) -> dict | None:
    """Zbuduj propozycję tygodnia z lokalnych ustawień albo danych Garmin."""
    if any(isinstance(item, dict) and item.get("available") for item in local_days.values()):
        return {day: dict(local_days.get(day, {})) for day, _ in _DAYS}
    available = set(snapshot.get("available_training_days", []))
    long_days = set(snapshot.get("long_training_days", []))
    if not available and not long_days:
        return None
    return {
        day: {
            "available": day in available or day in long_days,
            "min_minutes": (DEFAULT_LONG_TRAINING_MINUTES if day in long_days else DEFAULT_TRAINING_MINUTES)[0]
                           if day in available or day in long_days else 0,
            "max_minutes": (DEFAULT_LONG_TRAINING_MINUTES if day in long_days else DEFAULT_TRAINING_MINUTES)[1]
                           if day in available or day in long_days else 0,
        }
        for day, _ in _DAYS
    }


def _print_weekly_summary(days: dict) -> None:
    print("Dzień | dostępność | min–max")
    for key, label in _DAYS:
        item = days.get(key, {})
        print(f"{label:4} | {'tak' if item.get('available') else 'nie':11} | "
              f"{item.get('min_minutes', 0)}–{item.get('max_minutes', 0)}")


def _target_goal(profile: dict) -> dict[str, str]:
    options = ("5 km", "10 km", "półmaraton", "maraton", "Inny", "Brak — poprawa sprawności")
    saved_race = profile.get("target_race")
    default = next((index for index, option in enumerate(options[:4], 1) if option == saved_race), 3)
    print("Docelowy bieg:")
    for index, option in enumerate(options, 1):
        print(f"  {index}. {option}")
    selected = _choice("Wybierz numer", options, default)
    if selected == 5:
        while not (race := _ask("Nazwa biegu")):
            print("Podaj nazwę biegu.")
    elif selected == 6:
        race = "brak"
    else:
        race = options[selected - 1]
    target_time = "" if selected == 6 else _ask("Zakładany czas na ten bieg (np. 1:49:00)", profile.get("target_time", ""))
    return {"target_race": race, "target_time": target_time, "target_hm": f"{race} {target_time}".strip()}


def main() -> int:
    if not sys.stdin.isatty():
        print("Kreator wymaga interaktywnego terminala.")
        return 2
    try:
        print("=== Konfiguracja Trener Biegowy AI ===")
        print(f"Python: {sys.version.split()[0]}")
        for package in ("garminconnect", "garmindb"):
            try: __import__(package); print(f"{package}: OK")
            except ImportError: print(f"Brakuje {package}. Uruchom: pip install -r requirements.txt")
        current_env = {"GARMIN_EMAIL": os.environ.get("GARMIN_EMAIL", ""), "HEALTH_DATA_DIR": os.environ.get("HEALTH_DATA_DIR", str(Path.home() / "HealthData"))}
        health_dir = Path(current_env["HEALTH_DATA_DIR"]).expanduser()
        print("HEALTH_DATA_DIR:", "OK" if health_dir.exists() else f"brak ({env_hint('HEALTH_DATA_DIR', str(health_dir))})")
        email = _ask("E-mail Garmin", current_env["GARMIN_EMAIL"])
        had_token = has_token()
        if had_token:
            print("Znaleziono zapisany token Garmin — najpierw spróbuję użyć go bez hasła.")
            password = None
        else:
            print("Nie masz jeszcze zapisanego tokenu, więc hasło jest teraz potrzebne.")
            print("Posłuży do jednorazowego zalogowania i zapisania tokenu na przyszłość.")
            password = _ask("Hasło Garmin", "", secret=True)
        health = _ask("Katalog danych HEALTH_DATA_DIR", str(health_dir))
        try: profile = profile_store.load_profile()
        except FileNotFoundError:
            # Utwórz pusty profil tylko raz; późniejsze update_profile scala
            # wartości z ewentualnym zapisem stref dokonanym przez zones.
            profile = {}
            profile_store.save_profile(profile)
        snapshot = {}
        api = None
        def _mfa_prompt() -> str:
            print("\nGarmin wymaga weryfikacji dwuetapowej (MFA / kod SMS lub e-mail).")
            return input("Wpisz kod weryfikacyjny: ").strip()

        for attempt in range(3):
            try:
                print("Logowanie Garmin trwa — może potrwać kilka minut. "
                      "Ostrzeżenia mobile/widget nie są jeszcze wynikiem końcowym.", flush=True)
                api = ensure_token(email, password, prompt_mfa=_mfa_prompt)
                ensure_garmindb_config(email)
                print("Zalogowano do Garmin. Zapisane tokeny będą używane i odnawiane bez hasła.")
                break
            except GarminAuthError as exc:
                print(f"Logowanie Garmin zakończone niepowodzeniem: {exc}")
                if not exc.retry_credentials:
                    break
                if attempt < 2:
                    password = _ask("Hasło Garmin — spróbuj ponownie", "", secret=True)
        password = None  # Nie przechowuj hasła podczas dalszej konfiguracji.
        if api is not None:
            try:
                snapshot = fetch_snapshot(api)
                if snapshot:
                    print("Dane z Garmin Connect:")
                    for key, label in (("age", "Wiek"), ("weight", "Waga (kg)"), ("height", "Wzrost (cm)"), ("hr_max", "HR max"), ("hr_rest", "HR spoczynkowe (średnia 7 dni)"), ("lactate_threshold_hr", "Próg mleczanowy HR"), ("vo2max_running", "VO2max bieg")):
                        if key in snapshot: print(f"  {label}: {snapshot[key]}")
            except Exception as exc:
                print(f"Nie udało się pobrać danych z Garmin Connect: {exc}")
        elif not _yes_no("Nie udało się zalogować. Kontynuować z ręcznym wpisywaniem danych?", False):
            return 1
        use_snapshot = bool(snapshot) and _yes_no("Użyć tych danych?", True)
        limits = (("age", "Wiek", 10, 100), ("weight_kg", "Waga (kg)", 30, 250),
                  ("height_cm", "Wzrost (cm)", 100, 250), ("hr_max", "Tętno maksymalne", 120, 230),
                  ("hr_rest", "Tętno spoczynkowe", 25, 100), ("lactate_threshold_hr", "Próg mleczanowy HR", 100, 220))
        fields: dict[str, Any] = {}
        if use_snapshot:
            fields = {"weight_kg": snapshot["weight"]} if "weight" in snapshot else {}
            for key, _, _, _ in limits:
                source = "height" if key == "height_cm" else key
                if source in snapshot: fields[key] = snapshot[source]
        for key, label, low, high in limits:
            if key not in fields:
                default = snapshot.get("height" if key == "height_cm" else key, profile.get(key, low))
                fields[key] = _integer(label, default, low, high)
        while fields["hr_rest"] >= fields["hr_max"]:
            print("Tętno spoczynkowe musi być niższe niż tętno maksymalne.")
            fields["hr_rest"] = _integer("Tętno spoczynkowe", fields["hr_rest"], 25, 100)
        while fields["lactate_threshold_hr"] > fields["hr_max"]:
            print("Próg mleczanowy nie może być wyższy niż tętno maksymalne.")
            fields["lactate_threshold_hr"] = _integer("Próg mleczanowy HR", fields["lactate_threshold_hr"], 100, 220)
        if use_snapshot and snapshot.get("hr_zone_floors"):
            profile_store.set_hr_zones(snapshot["hr_zone_floors"], fields["hr_max"], "Garmin Connect — dane profilu")
        fields.update(_target_goal(profile),
                      target_date=_ask("Data celu (RRRR-MM-DD)", profile.get("target_date", "")),
                      current_hm_record=_ask("Aktualny rekord", profile.get("current_hm_record", "")))
        print("Dostępność treningowa:")
        local_days = preferences.load_preferences().get("days", {})
        proposal = _weekly_proposal(local_days, snapshot)
        if proposal:
            _print_weekly_summary(proposal)
        if proposal and _yes_no("Zatwierdzasz ten plan tygodnia?", True):
            for key, _ in _DAYS:
                item = proposal[key]
                preferences.set_weekly_availability(key, item.get("available", False),
                                                    item.get("min_minutes", 0), item.get("max_minutes", 0))
        else:
            for key, label in _DAYS:
                suggested = (proposal or {}).get(key, preferences.get_weekly_availability(key))
                available = _yes_no(f"{label}: trenujesz", suggested.get("available", False))
                minimum, maximum = (_minutes_range("  minuty (np. 30-45 albo 30)", suggested.get("min_minutes", 0), suggested.get("max_minutes", 0))
                                    if available else (0, 0))
                preferences.set_weekly_availability(key, available, minimum, maximum)
        prefs = preferences.load_preferences()
        prefs["max_quality_sessions_per_week"] = _integer("Maks. intensywnych sesji tygodniowo", prefs.get("max_quality_sessions_per_week", 0), 0)
        preferences.save_preferences(prefs)
        _print_weekly_summary(preferences.get_weekly_availability())
        env = {"GARMIN_EMAIL": email, "HEALTH_DATA_DIR": health}
        if _yes_no("Włączyć opcjonalne AI? Dane treningowe zostaną wysłane do zewnętrznego dostawcy.", False):
            env["AI_BASE_URL"] = _ask("AI_BASE_URL", os.environ.get("AI_BASE_URL", "https://api.openai.com/v1"))
            env["AI_MODEL"] = _ask("AI_MODEL", os.environ.get("AI_MODEL", "gpt-4o"))
            env["AI_API_KEY"] = _ask("AI_API_KEY", "", secret=True)
            env["AI_DATA_EXPORT_ENABLED"] = "true" if _yes_no("Wyrażasz zgodę na eksport danych do AI", False) else "false"
        profile_store.update_profile(**fields)
        if _yes_no("Zapisać ustawienia środowiska do projektu .env", True):
            _write_env(PROJECT_ROOT / ".env", env)
            print("Zapisano .env (sekrety: ****).")
        print("Zapisano profil i preferencje.")
        print("Dalej: python -m trainer doctor; python -m trainer sync; python -m trainer today")
        return 0
    except KeyboardInterrupt:
        print("\nPrzerwano.")
        return 130
