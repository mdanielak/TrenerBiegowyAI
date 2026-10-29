# -*- coding: utf-8 -*-
"""Widok statystyk: kilometry tygodniowo i wykresy trendów liczone na serwerze."""
from __future__ import annotations

import math

from api.views.common import _MONTHS_GENITIVE, _format_number
from services.stats import trend_direction

_CHART_WIDTH = 760
# Wykres tygodni zajmuje całą kartę, więc szerszy viewBox trzyma etykiety przy ok. 11 px.
_WEEKLY_WIDTH = 1060
_CHART_HEIGHT = 170
_PAD_LEFT = 36
_PAD_RIGHT = 14
_PAD_TOP = 18
_PAD_BOTTOM = 28

_METRIC_META = {
    "readiness": {"label": "Gotowość", "unit": "/10", "domain": (0, 10), "asset": "02_health_status/readiness.png",
                  "hint": "Ocena z nocnych pomiarów, ta sama co na stronie głównej."},
    "rhr": {"label": "Tętno spoczynkowe", "unit": "bpm", "asset": "02_health_status/resting_hr.png",
            "hint": "Niższe zwykle oznacza lepszą regenerację."},
    "hrv": {"label": "HRV ostatniej nocy", "unit": "ms", "asset": "02_health_status/hrv.png",
            "hint": "Wyższe zwykle oznacza lepszą regenerację."},
    "sleep": {"label": "Sen — ocena", "unit": "/100", "domain": (0, 100), "asset": "02_health_status/sleep.png",
              "hint": "Ocena snu wyliczona przez zegarek."},
    "stress": {"label": "Stres — średnia dobowa", "unit": "", "domain": (0, 100), "asset": "02_health_status/stress.png",
               "hint": "Niższy zwykle oznacza spokojniejszy dzień."},
}
_METRIC_ORDER = ("readiness", "rhr", "hrv", "sleep", "stress")


def _short_date(iso_day: str) -> str:
    """'2026-10-06' -> '6.10' na osi wykresu."""
    return f"{int(iso_day[8:10])}.{iso_day[5:7]}"


def _range_label(start, end) -> str:
    return (f"{start.day} {_MONTHS_GENITIVE[start.month - 1]} – "
            f"{end.day} {_MONTHS_GENITIVE[end.month - 1]} {end.year}")


def _inner(width=_CHART_WIDTH):
    return (width - _PAD_LEFT - _PAD_RIGHT, _CHART_HEIGHT - _PAD_TOP - _PAD_BOTTOM)


def _weekly_chart(weekly) -> dict | None:
    """Słupki kilometrów biegowych tydzień po tygodniu; bieżący tydzień jest oznaczony."""
    if not weekly or not any(week.distance_km for week in weekly):
        return None
    inner_width, inner_height = _inner(_WEEKLY_WIDTH)
    baseline = _PAD_TOP + inner_height
    # Skala obejmuje też górną granicę zakresu fazy, żeby pas strategii się mieścił.
    peak = max([week.distance_km for week in weekly] + [week.phase_km[1] for week in weekly if week.phase_km])
    slot = inner_width / len(weekly)

    def y_of(km):
        return round(baseline - inner_height * km / peak, 2)

    bar_width = round(min(slot * 0.62, 56), 2)
    bars = []
    for index, week in enumerate(weekly):
        height = round(inner_height * week.distance_km / peak, 2) if week.distance_km else 0
        center = _PAD_LEFT + slot * index + slot / 2
        band = None
        if week.phase_km:
            band = {"x": round(center - slot * 0.42, 2), "width": round(slot * 0.84, 2),
                    "y": y_of(week.phase_km[1]), "height": round(y_of(week.phase_km[0]) - y_of(week.phase_km[1]), 2)}
        bars.append({
            "band": band,
            "x": round(center - bar_width / 2, 2),
            "center": round(center, 2),
            "y": round(baseline - height, 2),
            "width": bar_width,
            "height": height,
            "km": week.distance_km,
            "date": week.monday.isoformat(),
            "sessions": week.sessions,
            "label": _short_date(week.monday.isoformat()),
            "is_current": week.is_current,
        })
    return {
        "width": _WEEKLY_WIDTH,
        "height": _CHART_HEIGHT,
        "baseline": round(baseline, 2),
        "label_y": round(baseline + 18, 2),
        "grid_start": _PAD_LEFT,
        "grid_end": _WEEKLY_WIDTH - _PAD_RIGHT,
        "bars": bars,
        "has_bands": any(bar["band"] for bar in bars),
    }


def _range_text(values, unit="km") -> str:
    return f"{values[0]}–{values[1]} {unit}"


def _versus(value, target) -> str:
    """Słowny opis wartości wobec zakresu; kolor nigdy nie niesie tego sam."""
    if value < target[0]:
        return "poniżej zakresu"
    if value > target[1]:
        return "powyżej zakresu"
    return "w zakresie"


def _phase_view(report) -> dict | None:
    """Bieżąca faza strategii i ostatni pełny tydzień na jej tle."""
    strategy = report.strategy
    phase = strategy.phase_for(report.end) if strategy else None
    if phase is None:
        return None
    week_number = (report.end - phase.start).days // 7 + 1
    total_weeks = (phase.end - phase.start).days // 7 + 1
    completed = [week for week in report.weekly if not week.is_current]
    last = completed[-1] if completed else None
    rows = []
    if last is not None and phase.km:
        rows.append({"label": "Kilometry w ostatnim pełnym tygodniu", "value": last.distance_km, "unit": "km",
                     "target": _range_text(phase.km), "status": _versus(last.distance_km, phase.km)})
    if last is not None and phase.long_km:
        rows.append({"label": "Najdłuższy bieg w tym tygodniu", "value": last.longest_km, "unit": "km",
                     "target": _range_text(phase.long_km), "status": _versus(last.longest_km, phase.long_km)})
    return {
        "name": phase.name,
        "dates": f"{phase.start.day}.{phase.start.month:02d}–{phase.end.day}.{phase.end.month:02d}.{phase.end.year}",
        "week_number": week_number,
        "total_weeks": total_weeks,
        "km": _range_text(phase.km) if phase.km else None,
        "long_km": _range_text(phase.long_km) if phase.long_km else None,
        "rows": rows,
    }


def _plan_rows(weekly) -> list[dict]:
    """Zaplanowane minuty obok przebiegniętych, najnowszy tydzień pierwszy."""
    rows = []
    for week in reversed(weekly):
        if week.planned_min is None:
            continue
        share = round(100 * week.duration_min / week.planned_min) if week.planned_min else None
        rows.append({
            "label": _short_date(week.monday.isoformat()),
            "planned": week.planned_min,
            "done": week.duration_min,
            "share": share,
            "is_current": week.is_current,
        })
    return rows


def _axis_bounds(values, domain=None) -> tuple[float, float]:
    """Zakres osi z marginesem, zaokrąglony do pełnych wartości i przycięty do skali miary."""
    low, high = min(values), max(values)
    span = high - low or max(abs(high) * 0.1, 1.0)
    low, high = math.floor(low - span * 0.15), math.ceil(high + span * 0.15)
    if domain is not None:
        low, high = max(low, domain[0]), min(high, domain[1])
    return low, high


def _line_chart(trend, domain=None) -> dict | None:
    """Linia dzień po dniu; brak pomiaru przerywa linię zamiast udawać wartość."""
    values = [value for _, value in trend.points if value is not None]
    if len(values) < 2:
        return None
    inner_width, inner_height = _inner()
    low, high = _axis_bounds(values, domain)
    steps = max(len(trend.points) - 1, 1)

    def y_of(value):
        return round(_PAD_TOP + (1 - (value - low) / (high - low)) * inner_height, 2)

    segments, current, dots, labels = [], [], [], []
    for index, (day, value) in enumerate(trend.points):
        x = round(_PAD_LEFT + inner_width * index / steps, 2)
        if index % 7 == 0:
            labels.append({"x": x, "text": _short_date(day)})
        if value is None:
            if current:
                segments.append(current)
            current = []
            continue
        current.append((x, y_of(value)))
    if current:
        segments.append(current)

    lines = []
    for segment in segments:
        if len(segment) == 1:
            dots.append({"x": segment[0][0], "y": segment[0][1]})
        else:
            lines.append(" ".join(f"{x},{y}" for x, y in segment))

    last_x, last_y = segments[-1][-1]
    middle = (low + high) / 2
    return {
        "width": _CHART_WIDTH,
        "height": _CHART_HEIGHT,
        "grid_start": _PAD_LEFT,
        "grid_end": _CHART_WIDTH - _PAD_RIGHT,
        "axis_x": _PAD_LEFT - 8,
        "label_y": round(_PAD_TOP + inner_height + 18, 2),
        "gridlines": [{"y": y_of(value), "label": _format_number(value, 0)} for value in (low, middle, high)],
        "lines": lines,
        "dots": dots,
        "last": {"x": last_x, "y": last_y},
        "average_y": y_of(trend.average) if trend.average is not None else None,
        "labels": labels,
    }


def _trend_tone(trend) -> dict:
    """Porównaj ostatnie 7 dni ze średnią zakresu. Kolor zawsze z opisem słownym."""
    direction = trend_direction(trend)
    if direction is None:
        return {"direction": None, "tone": "flat", "label": "za mało pomiarów do porównania"}
    if direction == "flat":
        return {"direction": "flat", "tone": "flat", "label": "bez wyraźnej zmiany"}
    favorable = (direction == "up") == trend.higher_is_better
    return {
        "direction": direction,
        "tone": "favorable" if favorable else "unfavorable",
        "label": "wyżej niż średnia" if direction == "up" else "niżej niż średnia",
    }


def _metric_views(metrics) -> list[dict]:
    views = []
    for key in _METRIC_ORDER:
        trend = metrics.get(key)
        if trend is None:
            continue
        meta = _METRIC_META[key]
        views.append({
            "key": key,
            "label": meta["label"],
            "unit": meta["unit"],
            "asset": meta["asset"],
            "hint": meta["hint"],
            "average": trend.average,
            "recent": trend.recent_average,
            "measured_days": trend.measured_days,
            "total_days": len(trend.points),
            "trend": _trend_tone(trend),
            "chart": _line_chart(trend, meta.get("domain")),
            "points": trend.points,
        })
    return views


def _stats_view(report) -> dict:
    """Zbierz dane strony statystyk z raportu."""
    completed = [week for week in report.weekly if not week.is_current]
    total_km = round(sum(week.distance_km for week in report.weekly), 1)
    return {
        "weeks": report.weeks,
        "range_label": _range_label(report.start, report.end),
        "total_km": total_km,
        "total_sessions": sum(week.sessions for week in report.weekly),
        "total_minutes": sum(week.duration_min for week in report.weekly),
        "average_km": (round(sum(week.distance_km for week in completed) / len(completed), 1)
                       if completed else None),
        "weekly_chart": _weekly_chart(report.weekly),
        "phase": _phase_view(report),
        "plan_rows": _plan_rows(report.weekly),
        "metrics": _metric_views(report.metrics),
    }
