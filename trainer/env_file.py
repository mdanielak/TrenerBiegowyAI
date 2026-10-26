"""Minimalny loader plików .env bez zewnętrznych zależności."""
from __future__ import annotations

import os
import re
from pathlib import Path


_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TRAILING_COMMENT_RE = re.compile(r"\s+#.*$")


def read_env_file(path=None) -> dict[str, str]:
    """Odczytaj plik bez modyfikowania środowiska procesu."""
    env_path = Path(path) if path is not None else Path(".env")
    try:
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        return {}

    applied: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not _KEY_RE.fullmatch(key):
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            quote = value[0]
            value = value[1:-1]
            if quote == '"':
                # Tylko cytowanie podwójne interpretuje dwa standardowe escape.
                # Inne sekwencje (np. \p w ścieżce Windows) zostają dosłowne.
                value = value.replace('\\\\', '\\').replace('\\"', '"')
        else:
            value = _TRAILING_COMMENT_RE.sub("", value).rstrip()

        applied[key] = value
    return applied


def load_env_file(path=None, override=False, *, exclude=()) -> dict[str, str]:
    """Wczytaj .env; istniejące zmienne systemowe mają pierwszeństwo."""
    applied = {}
    for key, value in read_env_file(path).items():
        if key in exclude:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied
