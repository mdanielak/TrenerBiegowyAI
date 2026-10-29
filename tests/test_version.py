# -*- coding: utf-8 -*-
"""Jedna wersja: update.bat i /health czytają pyproject.toml, a CLI trainer.__version__."""
import tomllib
from pathlib import Path

import trainer


def test_cli_and_package_versions_match():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert trainer.__version__ == tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
