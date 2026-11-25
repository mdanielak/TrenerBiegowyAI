# -*- coding: utf-8 -*-
"""Testy automatyzacji wydania (scripts/release.py) i odchudzania paczki ZIP (.gitattributes)."""
import importlib.util
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release.py"
_spec = importlib.util.spec_from_file_location("release", SCRIPT)
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)


@pytest.mark.parametrize("valid", ["0.9.1", "1.0.0", "12.34.56"])
def test_validate_version_accepts_semver(valid):
    assert release.validate_version(valid) == valid


@pytest.mark.parametrize("invalid", ["v0.9.1", "0.9", "0.9.1-rc1", "abc", "", "1.2.3.4"])
def test_validate_version_rejects_bad_formats(invalid):
    with pytest.raises(release.ReleaseError):
        release.validate_version(invalid)


def test_update_version_files_updates_both_targets(tmp_path):
    (tmp_path / "trainer").mkdir()
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.9.0"\n', encoding="utf-8")
    (tmp_path / "trainer" / "__init__.py").write_text('__version__ = "0.9.0"\n', encoding="utf-8")

    old_ver, new_ver = release.update_version_files(tmp_path, "0.9.1")

    assert (old_ver, new_ver) == ("0.9.0", "0.9.1")
    assert 'version = "0.9.1"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "0.9.1"' in (tmp_path / "trainer" / "__init__.py").read_text(encoding="utf-8")


def _write_valid_zip(path: Path, *, version: str = "0.9.1", extra: dict[str, str] | None = None) -> None:
    entries = {
        "TrenerBiegowyAI/pyproject.toml": f'[project]\nversion = "{version}"\n',
        "TrenerBiegowyAI/trainer/__init__.py": f'__version__ = "{version}"\n',
        "TrenerBiegowyAI/scripts/check_privacy.py": "def main(): return 0\n",
        "TrenerBiegowyAI/.env.example": "AI_API_KEY=\n",
    }
    if extra:
        entries.update(extra)
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


def test_verify_zip_accepts_clean_archive_with_env_example(tmp_path):
    zp = tmp_path / "TrenerBiegowyAI-0.9.1.zip"
    _write_valid_zip(zp, version="0.9.1")

    info = release.verify_zip(zp, "0.9.1", min_bytes=100)

    assert info["version"] == "0.9.1"
    assert info["files"] == 4


@pytest.mark.parametrize(
    "forbidden_entry",
    [
        "TrenerBiegowyAI/local/profile.json",
        "TrenerBiegowyAI/.env",
        "TrenerBiegowyAI/.env.local",
        "TrenerBiegowyAI/tests/test_api.py",
        "TrenerBiegowyAI/docs/AUDYT_CLAUDE_2026-11-23.md",
        "TrenerBiegowyAI/scripts/release.py",
        "TrenerBiegowyAI/scripts/demo_server.py",
    ],
)
def test_verify_zip_rejects_forbidden_entries(tmp_path, forbidden_entry):
    zp = tmp_path / "bad.zip"
    _write_valid_zip(zp, extra={forbidden_entry: "x"})

    with pytest.raises(release.ReleaseError, match="niedozwolone pliki"):
        release.verify_zip(zp, "0.9.1", min_bytes=100)


def test_verify_zip_rejects_version_mismatch(tmp_path):
    zp = tmp_path / "mismatch.zip"
    _write_valid_zip(zp, version="0.9.0")

    with pytest.raises(release.ReleaseError, match="Wersja po rozpakowaniu"):
        release.verify_zip(zp, "0.9.1", min_bytes=100)


def test_gitattributes_ignores_dev_files_but_keeps_runtime_privacy_check():
    content = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    for expected in (
        "tests export-ignore",
        "docs export-ignore",
        ".githooks export-ignore",
        "CLAUDE.md export-ignore",
        "DESIGN.md export-ignore",
        "PRODUCT.md export-ignore",
        "scripts/release.py export-ignore",
        "scripts/demo_server.py export-ignore",
    ):
        assert expected in content
    assert "scripts/check_privacy.py export-ignore" not in content
