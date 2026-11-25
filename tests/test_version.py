# -*- coding: utf-8 -*-
"""Jedna wersja: update.bat i /health czytają pyproject.toml, a CLI trainer.__version__."""
import tomllib
from pathlib import Path

import trainer


def test_cli_and_package_versions_match():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert trainer.__version__ == tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]


def test_requirements_match_pyproject_dependencies():
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    deps = list(pyproject["project"]["dependencies"])
    reqs = [
        line.strip()
        for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert reqs == deps
