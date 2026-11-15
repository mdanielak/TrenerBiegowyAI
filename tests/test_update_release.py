# -*- coding: utf-8 -*-
"""update_release.py (używany przez update.sh): aktualizacja z paczki wydania bez ruszania danych użytkownika."""
import importlib.util
import shutil
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update_release.py"
_spec = importlib.util.spec_from_file_location("update_release", SCRIPT)
update_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(update_release)

USER_FILES = {
    "local/profile.json": "MOJ PROFIL",
    ".env": "AI_API_KEY=moj-klucz",
    "logs/app.log": "MOJ LOG",
    "training-plans/long-term/half-marathon-2027.md": "MOJA STRATEGIA",
    "training-plans/2026-10/26-1.json": "MOJ PLAN",
}


def _install(tmp_path, version="0.3.0"):
    install = tmp_path / "install"
    install.mkdir()
    (install / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n', encoding="utf-8")
    (install / "app.py").write_text("old", encoding="utf-8")
    for rel, text in USER_FILES.items():
        (install / rel).parent.mkdir(parents=True, exist_ok=True)
        (install / rel).write_text(text, encoding="utf-8")
    return install


def _package(tmp_path, version="9.9.9"):
    package = tmp_path / f"TrenerBiegowyAI-{version}.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("TrenerBiegowyAI/pyproject.toml", f'[project]\nversion = "{version}"\n')
        archive.writestr("TrenerBiegowyAI/app.py", "new")
        archive.writestr("TrenerBiegowyAI/update.sh", "#!/usr/bin/env bash\n")
        # Paczka, która omyłkowo zawierałaby dane, nie może nadpisać danych użytkownika.
        archive.writestr("TrenerBiegowyAI/local/profile.json", "OBCY PROFIL")
        archive.writestr("TrenerBiegowyAI/.env", "AI_API_KEY=obcy")
        archive.writestr("TrenerBiegowyAI/logs/app.log", "OBCY LOG")
    return package


def _assert_user_data_kept(install):
    for rel, text in USER_FILES.items():
        assert (install / rel).read_text(encoding="utf-8") == text, rel


def test_update_from_zip_replaces_app_files_and_keeps_user_data(tmp_path):
    install = _install(tmp_path)
    assert update_release.main(["--zip", str(_package(tmp_path))], root=install) == 0
    assert (install / "app.py").read_text(encoding="utf-8") == "new"
    assert update_release.local_version(install) == "9.9.9"
    assert (install / "update.sh").stat().st_mode & 0o111  # skrypty zostają wykonywalne
    _assert_user_data_kept(install)


def test_downloads_the_latest_release_when_it_is_newer(tmp_path):
    install, package = _install(tmp_path), _package(tmp_path)
    release = {"tag_name": "v9.9.9", "assets": [{"name": package.name, "browser_download_url": "https://x/p.zip"}]}
    fetched = []
    code = update_release.main([], root=install, fetch_json=lambda url: release,
                               download=lambda url, target: fetched.append(url) or shutil.copy(package, target))
    assert code == 0 and fetched == ["https://x/p.zip"]
    assert update_release.local_version(install) == "9.9.9"
    _assert_user_data_kept(install)


def test_the_latest_version_needs_nothing(tmp_path, capsys):
    install = _install(tmp_path, version="1.2.0")
    release = {"tag_name": "v1.2.0", "assets": []}
    code = update_release.main([], root=install, fetch_json=lambda url: release,
                               download=lambda url, target: pytest.fail("nic nie pobieramy"))
    assert code == 0 and "Masz najnowszą wersję" in capsys.readouterr().out
    assert (install / "app.py").read_text(encoding="utf-8") == "old"


def test_a_foreign_zip_or_no_internet_changes_nothing(tmp_path, capsys):
    install = _install(tmp_path)
    foreign = tmp_path / "inne.zip"
    with zipfile.ZipFile(foreign, "w") as archive:
        archive.writestr("cos/app.py", "obce")
    assert update_release.main(["--zip", str(foreign)], root=install) == 1
    assert "To nie jest paczka Trenera Biegowego AI." in capsys.readouterr().err

    def offline(url):
        raise OSError("brak sieci")
    assert update_release.main([], root=install, fetch_json=offline) == 1
    assert "Nie udało się sprawdzić wydań" in capsys.readouterr().err
    assert (install / "app.py").read_text(encoding="utf-8") == "old"
    _assert_user_data_kept(install)


def test_files_are_replaced_not_rewritten_so_a_running_update_sh_is_safe(tmp_path):
    install = _install(tmp_path)
    (install / "update.sh").write_text("#!/usr/bin/env bash\necho stary\n", encoding="utf-8")
    before = (install / "update.sh").stat().st_ino
    assert update_release.main(["--zip", str(_package(tmp_path))], root=install) == 0
    # Działający bash czyta stary plik dalej; nowy ma osobny i-węzeł.
    assert (install / "update.sh").stat().st_ino != before
