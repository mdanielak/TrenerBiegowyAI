# -*- coding: utf-8 -*-
"""Widok analizy: rozkład punktów gotowości i zmierzone wartości."""
from __future__ import annotations

from api.views.common import _HRV_STATUSES, _SIGNAL_META, _SIGNAL_STATE_LABELS

_ANALYSIS_PILL_CLASSES = {"OK": "ok", "WARN": "warn", "FAIL": "bad", "UNKNOWN": "neutral"}
_CONFIDENCE_LABELS = {"high": "wysoka", "medium": "średnia", "low": "niska", "none": "brak"}


def _analysis_rows(readiness_data: dict) -> list[dict]:
    """Przełóż rozkład punktów gotowości na wiersze widoku. Status jest jedynym źródłem koloru."""
    rows = []
    for detail in readiness_data.get("details") or []:
        metric = detail.get("metric")
        status = detail.get("status")
        meta = _SIGNAL_META.get(metric, {})
        rows.append({
            "label": meta.get("label") or metric or "Sygnał",
            "icon": meta.get("icon"),
            "pill_class": _ANALYSIS_PILL_CLASSES.get(status, "neutral"),
            "status_label": _SIGNAL_STATE_LABELS.get(status, "brak danych"),
            "message": detail.get("message") or "",
        })
    return rows


def _analysis_measurements(readiness_data: dict) -> list[dict]:
    """Pokaż zmierzone wartości stojące za oceną. Brak pomiaru zostaje brakiem, nie zerem."""
    baseline = readiness_data.get("hrv_baseline")
    baseline_text = None
    if baseline is not None and "None" not in str(baseline):
        baseline_text = str(baseline).replace("-", "–")
    hrv_status = readiness_data.get("hrv_status")
    return [
        {"label": "Tętno spoczynkowe", "value": readiness_data.get("rhr"), "unit": "bpm", "icon": "heart"},
        {"label": "HRV ostatniej nocy", "value": readiness_data.get("hrv_last"), "unit": "", "icon": "pulse"},
        {"label": "HRV — zakres bazowy", "value": baseline_text, "unit": "", "icon": "pulse"},
        {"label": "HRV — ocena zegarka", "icon": "pulse",
         "value": _HRV_STATUSES.get(hrv_status) if hrv_status is not None else None, "unit": ""},
        {"label": "Sen — ocena", "value": readiness_data.get("sleep_score_val"), "unit": "/100", "icon": "moon"},
        {"label": "Sen — długość", "value": readiness_data.get("sleep_total"), "unit": "h", "icon": "moon"},
        {"label": "Stres — średnia dobowa", "value": readiness_data.get("stress"), "unit": "", "icon": "bolt"},
    ]
