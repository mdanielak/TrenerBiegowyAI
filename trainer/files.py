# -*- coding: utf-8 -*-
"""Zapis pliku odporny na przerwanie: przerwany zapis nigdy nie zostawia połowy pliku."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_atomic(path, text: str) -> None:
    """Zapisz tekst UTF-8 do pliku tymczasowego obok i podmień nim plik docelowy."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # mkstemp tworzy plik dostępny tylko dla właściciela (0600 na POSIX), w tym samym systemie plików.
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
