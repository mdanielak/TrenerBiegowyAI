# -*- coding: utf-8 -*-
"""
Readiness assessment and plan-vs-actual comparison services.

Extracted from analyze_and_readiness.py — pure logic, no side effects.
Importable from CLI, tests, and future API.
"""
from datetime import datetime


def compute_readiness_breakdown(data):
    """Compute detailed readiness score with per-metric breakdown.

    Returns dict with: score, max_score, level, details (list of metric evaluations).
    """
    latest_health = data.get('daily_health', [{}])[0] if data.get('daily_health') else {}
    latest_sleep = data.get('sleep', [{}])[0] if data.get('sleep') else {}
    latest_hrv = data.get('hrv', [{}])[0] if data.get('hrv') else {}

    rhr = latest_health.get('rhr')
    hrv_status = latest_hrv.get('status')
    hrv_last = latest_hrv.get('last_night')
    hrv_baseline_low = latest_hrv.get('baseline_low')
    hrv_baseline_high = latest_hrv.get('baseline_high')
    sleep_score_val = latest_sleep.get('score')
    sleep_total = latest_sleep.get('total_h')
    stress = latest_health.get('stress_avg')

    raw_score = 0
    max_score = 10
    details = []
    available_metrics = []
    missing_metrics = []

    def unavailable(name, metric, message):
        missing_metrics.append(name)
        details.append({"metric": metric, "status": "UNKNOWN", "message": message})

    # 1. RHR
    if rhr is None:
        unavailable('rhr', 'RHR', "Brak pomiaru RHR")
    elif rhr <= 49:
        available_metrics.append('rhr')
        raw_score += 2.5
        details.append({"metric": "RHR", "status": "OK", "message": f"RHR w normie ({rhr})"})
    elif rhr <= 53:
        available_metrics.append('rhr')
        raw_score += 1.5
        details.append({"metric": "RHR", "status": "WARN", "message": f"RHR lekko podwyzszone ({rhr})"})
    else:
        available_metrics.append('rhr')
        details.append({"metric": "RHR", "status": "FAIL", "message": f"RHR podwyzszone ({rhr}) — regeneracja"})

    # 2. HRV
    if any(value is None for value in (hrv_status, hrv_last, hrv_baseline_low, hrv_baseline_high)):
        unavailable('hrv', 'HRV', "Brak pełnych danych HRV (status, wartość lub baseline)")
    elif hrv_status == "BALANCED" and hrv_last is not None and hrv_baseline_low is not None and hrv_last >= hrv_baseline_low:
        available_metrics.append('hrv')
        raw_score += 3
        details.append({"metric": "HRV", "status": "OK", "message": f"HRV zrownowazone ({hrv_last})"})
    elif hrv_status == "BALANCED":
        available_metrics.append('hrv')
        raw_score += 1
        details.append({"metric": "HRV", "status": "WARN", "message": f"HRV w normie ale ponizej baseline ({hrv_last})"})
    else:
        available_metrics.append('hrv')
        details.append({"metric": "HRV", "status": "FAIL", "message": f"HRV niezrownowazone ({hrv_status}) — zwolnij"})

    # 3. Sleep
    if sleep_score_val is None:
        unavailable('sleep', 'Sleep', "Brak sleep score")
    elif sleep_score_val >= 90:
        available_metrics.append('sleep')
        raw_score += 2.5
        details.append({"metric": "Sleep", "status": "OK", "message": f"Sen bardzo dobry (score {sleep_score_val}, {sleep_total}h)"})
    elif sleep_score_val >= 70:
        available_metrics.append('sleep')
        raw_score += 1.5
        details.append({"metric": "Sleep", "status": "WARN", "message": f"Sen akceptowalny (score {sleep_score_val})"})
    else:
        available_metrics.append('sleep')
        details.append({"metric": "Sleep", "status": "FAIL", "message": f"Slaby sen ({sleep_score_val})"})

    # 4. Stress
    if stress is None:
        unavailable('stress', 'Stress', "Brak pomiaru stresu")
    elif stress <= 30:
        available_metrics.append('stress')
        raw_score += 2
        details.append({"metric": "Stress", "status": "OK", "message": f"Niski poziom stresu ({stress})"})
    elif stress <= 40:
        available_metrics.append('stress')
        raw_score += 1
        details.append({"metric": "Stress", "status": "WARN", "message": f"Umiarkowany stres ({stress})"})
    else:
        available_metrics.append('stress')
        details.append({"metric": "Stress", "status": "WARN", "message": f"Podwyzszony stres ({stress})"})

    weights = {'rhr': 2.5, 'hrv': 3.0, 'sleep': 2.5, 'stress': 2.0}
    available_max_score = sum(weights[name] for name in available_metrics)
    score = round(raw_score / available_max_score * max_score, 1) if available_max_score else 0
    if score >= 8:
        level = "ready"
    elif score >= 5:
        level = "ready_with_reserves"
    else:
        level = "not_ready"

    return {
        "score": score,
        "max_score": max_score,
        "raw_score": raw_score,
        "available_max_score": available_max_score,
        "insufficient_data": bool(missing_metrics),
        "missing_metrics": missing_metrics,
        "available_metrics": available_metrics,
        "data_coverage": len(available_metrics) / 4,
        "confidence": ('none' if not available_metrics else 'low' if len(available_metrics) == 1
                       else 'medium' if len(available_metrics) < 4 else 'high'),
        "level": level,
        "rhr": rhr,
        "hrv_status": hrv_status,
        "hrv_last": hrv_last,
        "hrv_baseline": f"{hrv_baseline_low}-{hrv_baseline_high}",
        "sleep_score_val": sleep_score_val,
        "sleep_total": sleep_total,
        "stress": stress,
        "details": details,
    }


def compare_plan_vs_actual(plan, activities, today=None):
    """Compare planned workouts vs actual activities.

    Returns list of dicts with: day, date, type, name, status, details, is_today.
    """
    if today is None:
        today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')

    results = []
    for w in plan.get('workouts', []):
        day_date = w['date']
        day_name = w['day']
        wtype = w['type']

        day_acts = [a for a in activities
                    if a.get('date', '')[:10] == day_date and a.get('type', '').startswith('running')]

        status = ""
        details = ""
        is_today = (day_date == today_str)
        matched_activity = None
        match_method = 'unmatched'

        requested_id = w.get('matched_activity_id')
        if requested_id is not None:
            matched_activity = next(
                (a for a in activities if a.get('activity_id') is not None
                 and str(a.get('activity_id')) == str(requested_id)),
                None,
            )
            if matched_activity is not None:
                match_method = 'id'

        def choose_heuristic(candidates):
            if not candidates:
                return None, 'unmatched'
            target_distance = w.get('distance_km')
            target_name = (w.get('name') or '').strip().lower()
            ranked = []
            for candidate in candidates:
                distance = candidate.get('distance_km')
                distance_diff = abs(distance - target_distance) if isinstance(distance, (int, float)) and isinstance(target_distance, (int, float)) else 0
                name = (candidate.get('name') or '').strip().lower()
                name_score = 2 if name == target_name else 1 if target_name and target_name in name else 0
                ranked.append((distance_diff, -name_score, candidate))
            ranked.sort(key=lambda item: (item[0], item[1]))
            best = ranked[0]
            if sum((item[0], item[1]) == (best[0], best[1]) for item in ranked) != 1:
                return None, 'ambiguous'
            return best[2], 'heuristic'

        if wtype == 'rest':
            if matched_activity is None:
                matched_activity, match_method = choose_heuristic(day_acts)
            if matched_activity:
                status = "REST_VIOLATION"
                details = f"Rest day, a zrobiono: {matched_activity['name']} ({matched_activity['distance_km']}km)"
            else:
                status = "OK"
                details = "Odpoczynek — zgodnie z planem"
                match_method = 'unmatched'
        else:
            if matched_activity is None:
                matched_activity, match_method = choose_heuristic(day_acts)
            if not matched_activity:
                if day_date > today_str:
                    status = "SCHEDULED"
                    details = f"Jeszcze nie wykonano ({w['name']})"
                else:
                    status = "MISSING"
                    details = f"Zaplanowano: {w['name']}, nie wykonano"
            else:
                a = matched_activity
                dist_diff = abs(a['distance_km'] - w.get('distance_km', 0))
                dist_ok = dist_diff < 2.0

                hr_target = w.get('hr_target', '')
                hr_ok = True
                if hr_target.startswith('<'):
                    try:
                        max_allowed = int(hr_target[1:])
                        hr_ok = a['avg_hr'] <= max_allowed + 10
                    except ValueError:
                        pass

                if dist_ok and hr_ok:
                    status = "OK"
                elif dist_ok:
                    status = "HR_WARNING"
                else:
                    status = "DISTANCE_WARNING"

                details = (f"Zrobiono: {a['distance_km']}km, {a['pace']}, "
                           f"HR {a['avg_hr']}/{a['max_hr']}")
                if w.get('distance_km'):
                    details += f" | Plan: {w['distance_km']}km"
                if hr_target:
                    details += f" | Target HR: {hr_target}"

        results.append({
            "day": day_name,
            "date": day_date,
            "type": wtype,
            "name": w['name'],
            "status": status,
            "details": details,
            "is_today": is_today,
            "matched_activity_id": matched_activity.get('activity_id') if matched_activity else None,
            "match_method": match_method,
        })

    return results


def get_today_workout(plan, today=None):
    """Get today's planned workout from a training plan.

    Returns workout dict or None (rest day / no plan).
    """
    from services.training_plan import get_today_workout_from_plan
    return get_today_workout_from_plan(plan, today)
