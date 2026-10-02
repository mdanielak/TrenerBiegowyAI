"""Przyjazne diagnostyki błędów uruchomieniowych.

Stabilne kody wyjścia: 1 — błąd ogólny, 3 — brak zależności, 4 — brak
GarminDB, 5 — problem z profilem lub JSON, 6 — brak uprawnień, 7 — baza
danych.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorAdvice:
    message: str
    hint: str
    exit_code: int


_SECRET_RE = re.compile(r"(?i)((?:password|passwd|secret|token|api[_ -]?key)\s*[=:]\s*)([^\s,;]+)")


def _safe_text(exc: BaseException) -> str:
    """Usuń z tekstu błędu potencjalne wartości sekretów."""
    return _SECRET_RE.sub(r"\1***", str(exc))


def env_hint(var_name: str, example_value: str = "") -> str:
    """Zwróć gotowe do wklejenia polecenie ustawiające zmienną środowiskową."""
    value = example_value.replace('"', '\\"')
    if sys.platform == "win32":
        return f'$env:{var_name} = "{value}"'
    return f'export {var_name}="{value}"'


def describe_error(exc: BaseException) -> ErrorAdvice:
    """Przetłumacz wyjątek na bezpieczny komunikat i wskazówkę po polsku."""
    text = _safe_text(exc)
    lower = text.lower()
    if isinstance(exc, (ModuleNotFoundError, ImportError)):
        return ErrorAdvice("Brakuje wymaganej zależności Pythona.", "Uruchom: pip install -r requirements.txt", 3)
    if isinstance(exc, FileNotFoundError) and "garmindb_cli" in lower:
        return ErrorAdvice("Nie znaleziono programu GarminDB.", "Zainstaluj GarminDB zgodnie z requirements.txt.", 4)
    if isinstance(exc, FileNotFoundError) and "profile.json" in lower:
        return ErrorAdvice("Nie znaleziono lokalnego profilu biegacza.", "Uruchom: python -m trainer setup", 5)
    if isinstance(exc, json.JSONDecodeError):
        filename = getattr(exc, "filename", None) or "wskazany plik JSON"
        return ErrorAdvice("Plik JSON jest niepoprawny.", f"Popraw format JSON w pliku: {filename}", 5)
    if isinstance(exc, PermissionError):
        return ErrorAdvice("Brak uprawnień do pliku lub katalogu.", "Sprawdź uprawnienia do lokalnych danych.", 6)
    if isinstance(exc, sqlite3.DatabaseError):
        return ErrorAdvice("Wystąpił problem z lokalną bazą danych.", "Uruchom: python -m trainer doctor, a następnie python -m trainer sync", 7)
    return ErrorAdvice("Wystąpił nieoczekiwany błąd.", f"Szczegóły: {text or type(exc).__name__}", 1)
