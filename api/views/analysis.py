# -*- coding: utf-8 -*-
"""Widok analizy: skąd wzięła się ocena — punkty za sygnały, główny powód i ostatnie 7 dni."""
from __future__ import annotations

from api.views.common import _SIGNAL_META, _SIGNAL_STATE_LABELS
from services.readiness import SCORING_RULES

_ANALYSIS_PILL_CLASSES = {"OK": "ok", "WARN": "warn", "FAIL": "bad", "UNKNOWN": "neutral"}
_CONFIDENCE_LABELS = {"high": "wysoka", "medium": "średnia", "low": "niska", "none": "brak"}


def _points(value) -> str:
    return f"{value:g}".replace(".", ",")


def _short_message(label: str, message: str) -> str:
    """Bez powtarzania nazwy sygnału nad wierszem: „Tętno spoczynkowe podwyższone…” → „Podwyższone…”."""
    if label and message.lower().startswith(label.lower() + " "):
        rest = message[len(label) + 1:]
        return rest[:1].upper() + rest[1:]
    return message


def _analysis_rows(readiness_data: dict) -> list[dict]:
    """Przełóż rozkład punktów gotowości na wiersze widoku. Status jest jedynym źródłem koloru."""
    rows = []
    for detail in readiness_data.get("details") or []:
        metric = detail.get("metric")
        status = detail.get("status")
        meta = _SIGNAL_META.get(metric, {})
        label = meta.get("label") or metric or "Sygnał"
        points, max_points = detail.get("points"), detail.get("max_points")
        rows.append({
            "label": label,
            "icon": meta.get("icon"),
            "pill_class": _ANALYSIS_PILL_CLASSES.get(status, "neutral"),
            "status_label": _SIGNAL_STATE_LABELS.get(status, "brak danych"),
            "message": _short_message(label, detail.get("message") or ""),
            "explain": meta.get("explain"),
            "scoring": SCORING_RULES.get(metric),
            "points_text": (f"{_points(points)} z {_points(max_points)} pkt" if points is not None and max_points
                            else "—"),
            "lost": (max_points - points) if points is not None and max_points else 0,
        })
    return rows


def _analysis_reason(rows: list[dict]) -> str | None:
    """Jedno zdanie: które sygnały najbardziej obniżyły ocenę (najwięcej utraconych punktów)."""
    weakest = sorted((row for row in rows if row["lost"] > 0), key=lambda row: -row["lost"])[:2]
    if not weakest:
        return "Wszystkie zmierzone sygnały są w normie." if any(row["points_text"] != "—" for row in rows) else None
    names = " i ".join(row["label"].lower() for row in weakest)
    # Czas teraźniejszy: „obniża/obniżają” nie zależy od rodzaju gramatycznego sygnału.
    return f"Ocenę najbardziej {'obniżają' if len(weakest) > 1 else 'obniża'}: {names}."


def _readiness_week(days: list[dict], weekdays_short) -> list[dict]:
    """Słupki gotowości z 7 dni (dziś na końcu); brak pomiaru zostaje brakiem, nie zerem."""
    from datetime import date

    bars = []
    for index, day in enumerate(days or []):
        score = day.get("score")
        bars.append({"label": "dziś" if index == len(days) - 1 else weekdays_short[date.fromisoformat(day["date"]).weekday()],
                     "score": score, "text": _points(score) if score is not None else "brak",
                     "height": round(score * 10) if score is not None else 0, "today": index == len(days) - 1})
    return bars
