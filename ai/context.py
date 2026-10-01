# -*- coding: utf-8 -*-
"""
Training context builder for AI coach.

Prepares a controlled, minimal context from training data
instead of sending the entire data_latest.json to the AI.
"""
import json
from datetime import datetime, timedelta

from trainer.config import IMPORTANT_PROMPT, RUNNER_PROFILE_EXAMPLE, RUNNER_PROFILE_LOCAL
from trainer.core import check_hrv_alert
from services.training_plan import find_current_plan, get_today_workout_from_plan


_PROFILE_FIELDS = {
    "age", "weight_kg", "height_cm", "hr_max", "hr_rest",
    "lactate_threshold_hr", "hr_zones", "current_hm_record", "target_hm",
    "target_date",
}
def _validate_runner_profile(profile):
    """Validate the fields consumed by the AI-context formatter."""
    if not isinstance(profile, dict):
        raise ValueError("Runner profile JSON must contain an object")
    missing = _PROFILE_FIELDS - profile.keys()
    if missing:
        raise ValueError(f"Runner profile is missing fields: {', '.join(sorted(missing))}")
    return profile


def _load_runner_profile(local_path=RUNNER_PROFILE_LOCAL, example_path=RUNNER_PROFILE_EXAMPLE):
    """Load a local profile, falling back to the tracked neutral example."""
    path = local_path if local_path.is_file() else example_path
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError("Runner profile not found; add local/profile.json") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid runner profile JSON: {path.name}") from exc
    return _validate_runner_profile(profile)


# Public import retained for callers that previously imported this constant.
RUNNER_PROFILE = _load_runner_profile()


def _goal_from_profile(profile):
    """Build the goal view from profile fields without duplicate constants."""
    return {
        "target": profile["target_hm"],
        "deadline": profile["target_date"],
        "current_record": profile["current_hm_record"],
    }


def _load_important_prompt():
    """Load the IMPORTANT_PROMPT.txt system instructions."""
    try:
        return IMPORTANT_PROMPT.read_text(encoding='utf-8')
    except FileNotFoundError:
        return ""


def _get_recent_activities(data, n=7):
    """Get last N running activities as compact summaries."""
    activities = data.get('activities', [])
    running = [a for a in activities if a.get('type', '').startswith('running')]
    return [
        {
            "date": a["date"][:10],
            "name": a.get("name", ""),
            "distance_km": a["distance_km"],
            "duration_min": a["duration_min"],
            "pace": a["pace"],
            "avg_hr": a["avg_hr"],
            "max_hr": a["max_hr"],
            "ascent_m": a.get("ascent_m", 0),
            "te": a.get("te"),
        }
        for a in running[:n]
    ]


def _get_health_snapshot(data):
    """Get current health metrics as a compact dict."""
    health = data.get('daily_health', [{}])[0] if data.get('daily_health') else {}
    sleep = data.get('sleep', [{}])[0] if data.get('sleep') else {}
    hrv = data.get('hrv', [{}])[0] if data.get('hrv') else {}

    return {
        "rhr": health.get('rhr'),
        "stress_avg": health.get('stress_avg'),
        "hrv_status": hrv.get('status'),
        "hrv_last_night": hrv.get('last_night'),
        "hrv_baseline": f"{hrv.get('baseline_low', '?')}-{hrv.get('baseline_high', '?')}",
        "sleep_score": sleep.get('score'),
        "sleep_total_h": sleep.get('total_h'),
        "sleep_deep_h": sleep.get('deep_h'),
    }


def _compute_weekly_load(data, today=None):
    """Compute total km and sessions this week (Mon-Sun containing `today`)."""
    if today is None:
        today = datetime.now()
    monday = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')

    week_acts = [a for a in data.get('activities', [])
                 if a['date'][:10] >= monday and a.get('type', '').startswith('running')]

    total_km = sum(a['distance_km'] for a in week_acts)
    total_min = sum(a['duration_min'] for a in week_acts)
    return {
        "total_km": round(total_km, 1),
        "total_min": round(total_min, 0),
        "sessions": len(week_acts),
    }


def build_training_context(data, plan=None, today=None):
    """Build the context dict for AI coach.

    Returns dict with:
        system_prompt: IMPORTANT_PROMPT.txt content
        runner_profile: configured athlete profile
        goal: target and deadline from the configured profile
        recent_activities: last 7 running sessions
        weekly_load: km and minutes this week
        today_plan: today's planned workout (if any)
        health_metrics: current RHR, HRV, sleep, stress
        hrv_alert: active HRV alert (if any)
    """
    if today is None:
        today = datetime.now()

    system_prompt = _load_important_prompt()
    recent = _get_recent_activities(data)
    health = _get_health_snapshot(data)
    weekly = _compute_weekly_load(data, today)
    hrv_alert = check_hrv_alert(data.get('hrv', []))

    # Get today's plan
    if plan is None:
        plan = find_current_plan(today)
    today_workout = get_today_workout_from_plan(plan, today) if plan else None

    return {
        "system_prompt": system_prompt,
        "runner_profile": RUNNER_PROFILE,
        "goal": _goal_from_profile(RUNNER_PROFILE),
        "recent_activities": recent,
        "weekly_load": weekly,
        "today_plan": today_workout,
        "health_metrics": health,
        "hrv_alert": hrv_alert,
    }


def format_context_for_user(context):
    """Format the training context as a user message for the AI."""
    lines = []

    # Runner profile
    p = context["runner_profile"]
    lines.append(f"## Profil biegacza")
    lines.append(f"Wiek: {p['age']}, Waga: {p['weight_kg']}kg, Wzrost: {p['height_cm']}cm")
    lines.append(f"HRmax: {p['hr_max']}, HRrest: {p['hr_rest']}")
    lines.append(f"Próg mleczanowy: HR {p['lactate_threshold_hr']}")
    lines.append(f"Strefy HR: {p['hr_zones']}")
    lines.append(f"Rekord HM: {p['current_hm_record']}, Cel: {p['target_hm']}")
    lines.append(f"Termin: {p['target_date']}")
    lines.append("")

    # Goal
    g = context["goal"]
    lines.append(f"## Cel")
    lines.append(f"{g['target']} do {g['deadline']}")
    lines.append(f"Aktualny rekord: {g['current_record']}")
    lines.append("")

    # Health
    h = context["health_metrics"]
    lines.append(f"## Aktualny stan zdrowia")
    lines.append(f"RHR: {h['rhr']}")
    lines.append(f"HRV: {h['hrv_last_night']} (status: {h['hrv_status']}, norma: {h['hrv_baseline']})")
    lines.append(f"Sen: {h['sleep_total_h']}h (score: {h['sleep_score']}, deep: {h['sleep_deep_h']}h)")
    lines.append(f"Stres: {h['stress_avg']}")
    lines.append("")

    # HRV alert
    if context["hrv_alert"]:
        alert = context["hrv_alert"]
        lines.append(f"## ⚠️ ALERT HRV")
        lines.append(f"HRV niskie od {alert['days']} dni! Statusy: {', '.join(alert['statuses'])}")
        lines.append(f"Wartości: {alert['values']}")
        lines.append("")

    # Weekly load
    w = context["weekly_load"]
    lines.append(f"## Obciążenie tygodniowe")
    lines.append(f"Dystans: {w['total_km']}km, Czas: {w['total_min']}min, Sesje: {w['sessions']}")
    lines.append("")

    # Recent activities
    if context["recent_activities"]:
        lines.append(f"## Ostatnie treningi")
        for a in context["recent_activities"]:
            lines.append(f"- {a['date']}: {a['name'] or 'bieg'}, {a['distance_km']}km, "
                        f"{a['pace']}, HR {a['avg_hr']}/{a['max_hr']}, "
                        f"wznies {a['ascent_m']}m, TE: {a['te']}")
        lines.append("")

    # Today's plan
    tp = context["today_plan"]
    if tp:
        lines.append(f"## Plan na dzisiaj")
        lines.append(f"Trening: {tp['name']} ({tp['type']})")
        if tp['type'] != 'rest':
            lines.append(f"Dystans: {tp.get('distance_km', '?')} km")
            lines.append(f"Tempo: {tp.get('pace_target', '?')}")
            lines.append(f"HR: {tp.get('hr_target', '?')}")
        if tp.get('notes'):
            lines.append(f"Notatki: {tp['notes']}")
    else:
        lines.append(f"## Plan na dzisiaj")
        lines.append(f"Brak zaplanowanego treningu")

    return "\n".join(lines)
