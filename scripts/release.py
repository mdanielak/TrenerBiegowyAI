# -*- coding: utf-8 -*-
"""Automatyzacja wydań Trenera Biegowego AI (wersja, tag, paczka ZIP, GitHub Release).

Użycie:
    .venv/bin/python scripts/release.py X.Y.Z --notes-file NOTATKI.md
    .venv/bin/python scripts/release.py X.Y.Z --dry-run
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.update_release import update_from_zip  # noqa: E402

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_PYPROJECT_VERSION_RE = re.compile(r'(?m)^version\s*=\s*"([^"]+)"')
_INIT_VERSION_RE = re.compile(r'(?m)^__version__\s*=\s*"([^"]+)"')

FORBIDDEN_IN_ZIP: tuple[str, ...] = (
    "/local/",
    "/logs/",
    "/.venv/",
    "/.git/",
    "node_modules/",
    ".playwright-mcp/",
    "testowanie.bat",
    "testowanie.sh",
    "scripts/testowanie.py",
    "scripts/release.py",
    "scripts/demo_server.py",
    "scripts/generate_art.py",
    "scripts/rescale_assets.py",
    "/tests/",
    "/docs/",
    "/.githooks/",
    "/CLAUDE.md",
    "/DESIGN.md",
    "/PRODUCT.md",
    "_originals/",
    "00_mockups/",
    "source_sheets/",
)

_REQUIRED_IN_ZIP: tuple[str, ...] = (
    "TrenerBiegowyAI/pyproject.toml",
    "TrenerBiegowyAI/trainer/__init__.py",
    "TrenerBiegowyAI/scripts/check_privacy.py",
)


class ReleaseError(Exception):
    """Błąd procedury przygotowania lub publikacji wydania."""


def validate_version(version: str) -> str:
    """Sprawdza format wersji X.Y.Z (bez prefiksu v)."""
    cleaned = version.strip()
    if not _VERSION_RE.fullmatch(cleaned):
        raise ReleaseError(f"Nieprawidłowy numer wersji '{version}'. Oczekiwano formatu X.Y.Z (bez 'v').")
    return cleaned


def _current_pyproject_version(root: Path) -> str:
    pyproject_path = root / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        return str(data["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
        raise ReleaseError(f"Nie można odczytać wersji z {pyproject_path}: {error}") from error


def update_version_files(root: Path, version: str) -> tuple[str, str]:
    """Podbija numer wersji w pyproject.toml i trainer/__init__.py."""
    version = validate_version(version)
    pyproject_path = root / "pyproject.toml"
    init_path = root / "trainer" / "__init__.py"

    try:
        pyproject_text = pyproject_path.read_text(encoding="utf-8")
        init_text = init_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ReleaseError(f"Nie można odczytać plików wersji: {error}") from error

    pyproject_matches = _PYPROJECT_VERSION_RE.findall(pyproject_text)
    if len(pyproject_matches) != 1:
        raise ReleaseError(f"Oczekiwano dokładnie jednego pola version w {pyproject_path}.")

    init_matches = _INIT_VERSION_RE.findall(init_text)
    if len(init_matches) != 1:
        raise ReleaseError(f"Oczekiwano dokładnie jednego __version__ w {init_path}.")

    old_version = pyproject_matches[0]
    new_pyproject = _PYPROJECT_VERSION_RE.sub(f'version = "{version}"', pyproject_text, count=1)
    new_init = _INIT_VERSION_RE.sub(f'__version__ = "{version}"', init_text, count=1)

    pyproject_path.write_text(new_pyproject, encoding="utf-8")
    init_path.write_text(new_init, encoding="utf-8")
    return old_version, version


def _is_forbidden_zip_entry(name: str) -> bool:
    if any(bad in name for bad in FORBIDDEN_IN_ZIP):
        return True
    if name.endswith("/.env") or ("/.env." in name and not name.endswith("/.env.example")):
        return True
    return False


def verify_zip(zip_path: Path, expected_version: str, *, min_bytes: int = 500_000) -> dict[str, object]:
    """Weryfikuje rozmiar, zawartość i rozpakowanie paczki ZIP przez update_from_zip."""
    if not zip_path.is_file():
        raise ReleaseError(f"Brak paczki ZIP: {zip_path}")
    size = zip_path.stat().st_size
    if size < min_bytes:
        raise ReleaseError(f"Paczka {zip_path.name} jest podejrzanie mała ({size} B < {min_bytes} B).")

    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
    except (zipfile.BadZipFile, OSError) as error:
        raise ReleaseError(f"Nie można otworzyć paczki {zip_path}: {error}") from error

    missing = [req for req in _REQUIRED_IN_ZIP if req not in names]
    if missing:
        raise ReleaseError(f"W paczce brakuje wymaganych plików: {', '.join(missing)}")

    forbidden = [name for name in names if _is_forbidden_zip_entry(name)]
    if forbidden:
        preview = ", ".join(forbidden[:10])
        raise ReleaseError(f"W paczce wykryto niedozwolone pliki: {preview}")

    with tempfile.TemporaryDirectory(prefix="trener-release-check-") as tmp:
        actual_version = update_from_zip(zip_path, Path(tmp))
    if actual_version != expected_version:
        raise ReleaseError(f"Wersja po rozpakowaniu paczki ({actual_version}) != oczekiwana ({expected_version}).")

    return {"files": len(names), "size_bytes": size, "version": actual_version}


def _run(cmd: list[str], *, cwd: Path = ROOT, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=capture,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        suffix = f": {details}" if details else ""
        raise ReleaseError(f"Polecenie {' '.join(cmd)} zakończyło się kodem {result.returncode}{suffix}")
    return result


def check_git_ready(root: Path, version: str, *, check_remote: bool) -> None:
    """Sprawdza czystość repozytorium na gałęzi main i brak konfliktu tagu."""
    branch_res = _run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=root, capture=True, check=False)
    if branch_res.returncode != 0 or branch_res.stdout.strip() != "main":
        current = branch_res.stdout.strip() or "(detached HEAD)"
        raise ReleaseError(f"Wydanie można robić tylko z gałęzi 'main' (obecnie: {current}).")

    status_res = _run(["git", "status", "--porcelain"], cwd=root, capture=True)
    if status_res.stdout.strip():
        raise ReleaseError("Katalog roboczy zawiera niezacommitowane lub nieśledzone zmiany.")

    tag = f"v{version}"
    local_tag = _run(["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"], cwd=root, capture=True, check=False)
    if local_tag.returncode == 0:
        raise ReleaseError(f"Tag {tag} już istnieje lokalnie.")

    if check_remote:
        remote_tag = _run(["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"], cwd=root, capture=True)
        if remote_tag.stdout.strip():
            raise ReleaseError(f"Tag {tag} już istnieje na origin.")
        gh_res = _run(["gh", "auth", "status"], cwd=root, capture=True, check=False)
        if gh_res.returncode != 0:
            raise ReleaseError("Brak aktywnej autoryzacji GitHub CLI (`gh auth status`).")


def _build_archive(root: Path, ref: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    _run(["git", "archive", "--format=zip", "--prefix=TrenerBiegowyAI/", "-o", str(output_path), ref], cwd=root)


def _run_checks(*, skip_tests: bool) -> None:
    _run([sys.executable, "scripts/check_privacy.py"])
    if not skip_tests:
        _run([sys.executable, "-m", "pytest", "-q"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Przygotowanie i publikacja wydania Trenera Biegowego AI.")
    parser.add_argument("version", help="Nowy numer wersji w formacie X.Y.Z (bez prefiksu v)")
    parser.add_argument("--notes-file", type=Path, help="Plik Markdown z polskimi notatkami wydania")
    parser.add_argument("--dry-run", action="store_true", help="Symulacja: weryfikuje repo, testy i paczkę ZIP z HEAD")
    parser.add_argument("--skip-tests", action="store_true", help="Pomiń pełny pytest przed zmianą wersji")
    parser.add_argument("--no-push", action="store_true", help="Zrób commit, tag i ZIP lokalnie, bez push i GitHub Release")
    args = parser.parse_args(argv)

    try:
        version = validate_version(args.version)
        tag = f"v{version}"
        needs_remote = not args.dry_run and not args.no_push

        if needs_remote:
            if not args.notes_file:
                raise ReleaseError("Dla publikacji na GitHubie podaj --notes-file z polskimi notatkami wydania.")
            if not args.notes_file.is_file() or not args.notes_file.read_text(encoding="utf-8").strip():
                raise ReleaseError(f"Plik notatek nie istnieje lub jest pusty: {args.notes_file}")

        check_git_ready(ROOT, version, check_remote=needs_remote)
        _run_checks(skip_tests=args.skip_tests)

        if args.dry_run:
            current_version = _current_pyproject_version(ROOT)
            with tempfile.TemporaryDirectory(prefix="trener-dryrun-") as tmp:
                tmp_zip = Path(tmp) / f"TrenerBiegowyAI-{version}-dryrun.zip"
                _build_archive(ROOT, "HEAD", tmp_zip)
                info = verify_zip(tmp_zip, current_version)
            size_mib = int(info["size_bytes"]) / (1024 * 1024)
            print(
                f"DRY-RUN OK: aktualna wersja {current_version}, "
                f"paczka z HEAD = {size_mib:.2f} MiB ({info['files']} wpisów)."
            )
            print(f"Planowane kroki dla {tag}: podbicie wersji -> commit 'Release {version}' -> tag {tag} -> dist/TrenerBiegowyAI-{version}.zip")
            return 0

        old_version, new_version = update_version_files(ROOT, version)
        print(f"Zaktualizowano wersję: {old_version} -> {new_version}")

        _run([sys.executable, "-m", "pytest", "tests/test_version.py", "tests/test_update_release.py", "tests/test_release.py", "-q"])
        _run([sys.executable, "scripts/check_privacy.py"])

        _run(["git", "add", "pyproject.toml", "trainer/__init__.py"])
        _run(["git", "commit", "-m", f"Release {version}"])
        _run(["git", "tag", "-a", tag, "-m", f"Release {version}"])

        zip_path = ROOT / "dist" / f"TrenerBiegowyAI-{version}.zip"
        _build_archive(ROOT, tag, zip_path)
        info = verify_zip(zip_path, version)
        size_mib = int(info["size_bytes"]) / (1024 * 1024)
        print(f"ZIP OK: {zip_path.name}, {size_mib:.2f} MiB, pliki={info['files']}, update_from_zip -> {info['version']}")

        if args.no_push:
            print(f"Tryb --no-push: commit i tag {tag} utworzone lokalnie, paczka gotowa w {zip_path}.")
            return 0

        _run(["git", "push", "origin", "main", tag])
        _run([
            "gh", "release", "create", tag, str(zip_path),
            "--latest",
            "--title", f"Trener Biegowy AI {version}",
            "--notes-file", str(args.notes_file),
        ])
        _run(["gh", "release", "view", tag])
        return 0
    except ReleaseError as error:
        print(f"BŁĄD: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
