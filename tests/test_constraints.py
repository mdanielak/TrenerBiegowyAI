# -*- coding: utf-8 -*-
"""Instalacja i aktualizacja biorą przetestowane wersje bibliotek, nie najnowsze dostępne."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _name(line: str) -> str:
    return re.split(r"[<>=!~;\[ ]", line.strip(), 1)[0].replace("_", "-").lower()


def test_every_requirement_has_a_tested_version():
    pinned = {_name(line) for line in (ROOT / "constraints.txt").read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.startswith("#")}
    required = {_name(line) for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")}
    assert required <= pinned, required - pinned
    assert all("==" in line for line in (ROOT / "constraints.txt").read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.startswith("#"))


def test_install_and_update_use_the_constraints():
    for script in ("install.bat", "update.bat"):
        assert "-r requirements.txt -c constraints.txt" in (ROOT / script).read_text(encoding="utf-8"), script
