# -*- coding: utf-8 -*-
"""update.ps1 podmienia pliki aplikacji i nigdy nie dotyka danych użytkownika."""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update.ps1"
USER_FILES = {
    "local/profile.json": "MOJ PROFIL",
    ".env": "AI_API_KEY=moj-klucz",
    "training-plans/long-term/half-marathon-2027.md": "MOJA STRATEGIA",
    "training-plans/2026-10/26-1.json": "MOJ PLAN",
}

pytestmark = pytest.mark.skipif(sys.platform != "win32" or shutil.which("powershell") is None,
                                reason="update.ps1 działa tylko w Windows PowerShell")


def test_update_from_zip_replaces_app_files_and_keeps_user_data(tmp_path):
    install = tmp_path / "install"
    (install / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, install / "scripts" / "update.ps1")
    (install / "pyproject.toml").write_text('[project]\nversion = "0.3.0"\n', encoding="utf-8")
    (install / "app.py").write_text("old", encoding="utf-8")
    for rel, text in USER_FILES.items():
        (install / rel).parent.mkdir(parents=True, exist_ok=True)
        (install / rel).write_text(text, encoding="utf-8")

    package = tmp_path / "TrenerBiegowyAI-9.9.9.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("TrenerBiegowyAI/pyproject.toml", '[project]\nversion = "9.9.9"\n')
        archive.writestr("TrenerBiegowyAI/app.py", "new")
        # Paczka, która omyłkowo zawierałaby dane, nie może nadpisać danych użytkownika.
        archive.writestr("TrenerBiegowyAI/local/profile.json", "OBCY PROFIL")
        archive.writestr("TrenerBiegowyAI/.env", "AI_API_KEY=obcy")

    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(install / "scripts" / "update.ps1"),
         "-ZipPath", str(package), "-Port", "8999"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        env={**os.environ, "TRENER_NONINTERACTIVE": "1"})

    assert result.returncode == 0, result.stdout + result.stderr
    assert (install / "app.py").read_text(encoding="utf-8") == "new"
    assert '"9.9.9"' in (install / "pyproject.toml").read_text(encoding="utf-8")
    for rel, text in USER_FILES.items():
        assert (install / rel).read_text(encoding="utf-8") == text, rel
