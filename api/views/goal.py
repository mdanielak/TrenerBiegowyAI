# -*- coding: utf-8 -*-
"""Widok celu: oś faz strategii i lista kryteriów gotowości."""
from __future__ import annotations

from api.views.common import _MONTHS_GENITIVE, _plural

_TRACK_WIDTH = 1060
# Pod paskiem jest miejsce na podpis „dziś” przy znaczniku.
_TRACK_HEIGHT = 62
_TRACK_Y = 8
_TRACK_BAR = 22
_GAP = 4


def _day_month(day) -> str:
    return f"{day.day}.{day.month:02d}"


def _timeline(report) -> dict | None:
    """Odcinki faz proporcjonalne do długości; znacznik „dziś” w bieżącej fazie."""
    phases = report.phases
    if not phases:
        return None
    start, end = phases[0].start, phases[-1].end
    span = max((end - start).days, 1)
    usable = _TRACK_WIDTH - _GAP * (len(phases) - 1)
    segments, x = [], 0.0
    for phase in phases:
        width = usable * ((phase.end - phase.start).days + 1) / (span + 1)
        segments.append({
            "x": round(x, 2), "width": round(width, 2), "number": phase.number,
            "state": "current" if phase.is_current else ("past" if phase.is_past else "future"),
            "center": round(x + width / 2, 2),
        })
        x += width + _GAP
    marker = None
    if report.current_phase is not None:
        segment = segments[report.current_phase.number - 1]
        phase = report.current_phase
        length = max((phase.end - phase.start).days, 1)
        fraction = min(max(((report.week_number - 1) * 7 + 3) / length, 0), 1)
        marker = round(segment["x"] + segment["width"] * fraction, 2)
    return {"width": _TRACK_WIDTH, "height": _TRACK_HEIGHT, "y": _TRACK_Y, "bar": _TRACK_BAR,
            "text_y": _TRACK_Y + _TRACK_BAR / 2 + 5, "segments": segments, "marker": marker,
            # Podpis nie może wyjść poza wykres, gdy „dziś” jest na samym początku lub końcu osi.
            "marker_label_x": None if marker is None else min(max(marker, 18), _TRACK_WIDTH - 18),
            "marker_label_y": _TRACK_Y + _TRACK_BAR + 24}


def _goal_view(report) -> dict:
    target = report.target_date
    return {
        "title": report.title,
        "target_label": (f"{target.day} {_MONTHS_GENITIVE[target.month - 1]} {target.year}" if target else None),
        "days_left": report.days_left,
        "days_word": _plural(report.days_left, "dzień", "dni", "dni") if report.days_left is not None else "",
        "target_time": report.target_time,
        "target_pace": report.target_pace,
        "distance_label": report.distance_label,
        "record": report.record,
        "timeline": _timeline(report),
        "phases": [{
            "number": phase.number,
            "name": phase.name,
            "dates": f"{_day_month(phase.start)}–{_day_month(phase.end)}.{phase.end.year}",
            "is_current": phase.is_current,
            "is_past": phase.is_past,
        } for phase in report.phases],
        "current": report.current_phase.name if report.current_phase else None,
        "week_number": report.week_number,
        "total_weeks": report.total_weeks,
        "criteria": [{
            "label": criterion.label,
            "target": criterion.target,
            "actual": criterion.actual,
            "state": "ok" if criterion.met else ("neutral" if criterion.met is None else "warn"),
            "state_label": ("spełnione" if criterion.met else
                            ("brak danych" if criterion.met is None else "jeszcze nie")),
        } for criterion in report.criteria],
    }
