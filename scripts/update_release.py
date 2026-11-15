# -*- coding: utf-8 -*-
"""Aktualizacja z paczki wydania na GitHubie — linuksowy odpowiednik scripts/update.ps1.

Uruchamiany przez update.sh, gdy aplikacja nie jest kopią repozytorium git (instalacja z ZIP-a).
Kopiuje tylko pliki aplikacji; nigdy nie dotyka danych użytkownika: local/, .env, .venv/, logs/,
planów tygodniowych ani własnej strategii (nie ma ich w paczce, a dane są dodatkowo wykluczone).
Tylko biblioteka standardowa: skrypt działa jeszcze w starej wersji aplikacji.

Użycie: python scripts/update_release.py [--zip ŚCIEŻKA]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = "mdanielak/TrenerBiegowyAI"
RELEASE_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
ROOT = Path(__file__).resolve().parents[1]
# Na wszelki wypadek: tych ścieżek z paczki nigdy nie kopiujemy.
EXCLUDED = {"local", ".venv", ".git", "logs", ".env"}
_HEADERS = {"User-Agent": "TrenerBiegowyAI-update"}


class UpdateError(Exception):
    """Komunikat dla osoby aktualizującej aplikację."""


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text)[:3]) or (0,)


def local_version(root: Path) -> str:
    try:
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "0.0.0"


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=_HEADERS), timeout=30) as response:
        return json.load(response)


def _download(url: str, target: Path) -> None:
    with urllib.request.urlopen(urllib.request.Request(url, headers=_HEADERS), timeout=300) as response, \
            open(target, "wb") as out:
        shutil.copyfileobj(response, out)


def _replace_file(source: Path, destination: Path) -> None:
    """Nowy plik obok i podmiana jednym ruchem: działający update.sh czyta dalej swoją starą kopię."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.update")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)


def update_from_zip(zip_path: Path, root: Path) -> str:
    """Podmień pliki aplikacji plikami z paczki; zwraca nową wersję."""
    with tempfile.TemporaryDirectory(prefix="trener-update-") as work:
        unpacked = Path(work)
        try:
            with zipfile.ZipFile(zip_path) as archive:
                for member in archive.infolist():
                    target = (unpacked / member.filename).resolve()
                    if not target.is_relative_to(unpacked.resolve()):
                        raise UpdateError("To nie jest paczka Trenera Biegowego AI.")
                archive.extractall(unpacked)
        except (zipfile.BadZipFile, OSError) as error:
            raise UpdateError("Nie można otworzyć paczki ZIP.") from error
        top = list(unpacked.iterdir())
        source = top[0] if len(top) == 1 and top[0].is_dir() else unpacked
        if not (source / "pyproject.toml").is_file():
            raise UpdateError("To nie jest paczka Trenera Biegowego AI.")
        for item in source.rglob("*"):
            relative = item.relative_to(source)
            if relative.parts[0] in EXCLUDED or item.is_dir():
                continue
            _replace_file(item, root / relative)
        for script in root.glob("*.sh"):
            script.chmod(script.stat().st_mode | 0o755)
        for script in (root / "scripts").glob("*.sh"):
            script.chmod(script.stat().st_mode | 0o755)
    return local_version(root)


def main(argv=None, *, root: Path = ROOT, fetch_json=_fetch_json, download=_download) -> int:
    parser = argparse.ArgumentParser(description="Aktualizacja Trenera Biegowego AI z paczki wydania.")
    parser.add_argument("--zip", help="pobrana wcześniej paczka ZIP z wydania")
    args = parser.parse_args(argv)
    current = local_version(root)
    print(f"Zainstalowana wersja: {current}")
    try:
        if args.zip:
            zip_path = Path(args.zip)
            if not zip_path.is_file():
                raise UpdateError(f"Nie ma pliku: {zip_path}")
            print(f"Aktualizuję z paczki: {zip_path}")
            print(f"Zaktualizowano do wersji {update_from_zip(zip_path, root)}.")
            return 0
        print("Sprawdzam najnowsze wydanie na GitHubie...")
        try:
            release = fetch_json(RELEASE_URL)
        except (OSError, ValueError) as error:
            raise UpdateError("Nie udało się sprawdzić wydań (brak internetu?). Pobierz paczkę ZIP ręcznie "
                              "i uruchom: ./update.sh --zip ŚCIEŻKA_DO_PACZKI") from error
        latest = str(release.get("tag_name") or "").lstrip("v")
        print(f"Najnowsze wydanie: {latest}")
        if _version_tuple(latest) <= _version_tuple(current):
            print("Masz najnowszą wersję - nic do zrobienia.")
            return 0
        asset = next((a for a in release.get("assets") or [] if str(a.get("name", "")).endswith(".zip")), None)
        if asset is None:
            raise UpdateError(f"Wydanie {latest} nie ma paczki ZIP.")
        with tempfile.TemporaryDirectory(prefix="trener-download-") as work:
            zip_path = Path(work) / asset["name"]
            print(f"Pobieram {asset['name']}...")
            try:
                download(asset["browser_download_url"], zip_path)
            except OSError as error:
                raise UpdateError("Nie udało się pobrać paczki. Sprawdź internet i spróbuj ponownie.") from error
            print("Kopiuję nowe pliki aplikacji (Twoje dane zostają bez zmian)...")
            print(f"Zaktualizowano do wersji {update_from_zip(zip_path, root)}.")
        return 0
    except UpdateError as error:
        print(f"BŁĄD: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
