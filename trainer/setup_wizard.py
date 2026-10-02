"""Interaktywny kreator pierwszej konfiguracji."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any
import re

from . import profile_store, preferences
from .config import PROJECT_ROOT, SETTINGS
from .errors import env_hint


def _ask(label, default="", secret=False):
    shown = "****" if secret and default else default
    value = input(f"{label}" + (f" [{shown}]" if shown else "") + ": ").strip()
    return value if value else default


def _integer(label, default=0, minimum=0, maximum=None):
    while True:
        value = _ask(label, str(default))
        try:
            number = int(value)
            if number < minimum or (maximum is not None and number > maximum):
                raise ValueError
            return number
        except ValueError:
            maximum_text = f" i nie większą niż {maximum}" if maximum is not None else ""
            print(f"Podaj liczbę całkowitą nie mniejszą niż {minimum}{maximum_text}.")


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
    """Uaktualnij tylko podane klucze, zachowując komentarze i obce wpisy."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    values = {key: str(value) for key, value in values.items() if value != ""}
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
        print("Hasło jest opcjonalne: domyślnie używany jest zapisany token OAuth GarminDB.")
        password = _ask("Hasło Garmin (zostaw puste dla tokenu)", "", secret=True)
        health = _ask("Katalog danych HEALTH_DATA_DIR", str(health_dir))
        try: profile = profile_store.load_profile()
        except FileNotFoundError:
            # Utwórz pusty profil tylko raz; późniejsze update_profile scala
            # wartości z ewentualnym zapisem stref dokonanym przez zones.
            profile = {}
            profile_store.save_profile(profile)
        limits = (("age", "Wiek", 10, 100), ("weight_kg", "Waga (kg)", 30, 250),
                  ("height_cm", "Wzrost (cm)", 100, 250), ("hr_max", "Tętno maksymalne", 120, 230),
                  ("hr_rest", "Tętno spoczynkowe", 25, 100), ("lactate_threshold_hr", "Próg mleczanowy HR", 100, 220))
        fields: dict[str, Any] = {key: _integer(label, profile.get(key, low), low, high) for key, label, low, high in limits}
        while fields["hr_rest"] >= fields["hr_max"]:
            print("Tętno spoczynkowe musi być niższe niż tętno maksymalne.")
            fields["hr_rest"] = _integer("Tętno spoczynkowe", fields["hr_rest"], 25, 100)
        while fields["lactate_threshold_hr"] > fields["hr_max"]:
            print("Próg mleczanowy nie może być wyższy niż tętno maksymalne.")
            fields["lactate_threshold_hr"] = _integer("Próg mleczanowy HR", fields["lactate_threshold_hr"], 100, 220)
        if _yes_no("Pobrać strefy HR z Garmin Connect teraz", False):
            try:
                from .commands.zones import main as zones
                if zones(sync=True): print("Nie udało się pobrać stref; kontynuuję.")
            except Exception:
                print("Nie udało się pobrać stref; kontynuuję.")
        fields.update(target_hm=_ask("Docelowy bieg", profile.get("target_hm", "półmaraton")),
                      target_date=_ask("Data celu (RRRR-MM-DD)", profile.get("target_date", "")),
                      current_hm_record=_ask("Aktualny rekord", profile.get("current_hm_record", "")))
        days = [("mon", "Pon"), ("tue", "Wt"), ("wed", "Śr"), ("thu", "Czw"), ("fri", "Pt"), ("sat", "Sob"), ("sun", "Nd")]
        print("Dostępność treningowa:")
        for key, label in days:
            old = preferences.get_weekly_availability(key)
            available = _yes_no(f"{label}: trenujesz", old["available"])
            minimum = _integer("  minimum minut", old["min_minutes"], 0) if available else 0
            maximum = _integer("  maksimum minut", old["max_minutes"], minimum) if available else 0
            preferences.set_weekly_availability(key, available, minimum, maximum)
        prefs = preferences.load_preferences()
        prefs["max_quality_sessions_per_week"] = _integer("Maks. intensywnych sesji tygodniowo", prefs.get("max_quality_sessions_per_week", 0), 0)
        preferences.save_preferences(prefs)
        print("Dzień | dostępność | min–max")
        for key, label in days:
            item = preferences.get_weekly_availability(key)
            print(f"{label:4} | {'tak' if item['available'] else 'nie':11} | {item['min_minutes']}–{item['max_minutes']}")
        env = {"GARMIN_EMAIL": email, "HEALTH_DATA_DIR": health}
        if password: env["GARMIN_PASSWORD"] = password
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
