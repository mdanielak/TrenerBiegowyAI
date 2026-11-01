# -*- coding: utf-8 -*-
"""
Readiness assessment and plan-vs-actual comparison services.

Extracted from analyze_and_readiness.py — pure logic, no side effects.
Importable from CLI, tests, and future API.
"""
import math
import statistics
from datetime import datetime, timedelta

from services.activity_matching import find_activity_for_workout


# Oceny HRV z zegarka po polsku: te zdania trafiają na stronę Analiza i do kontekstu AI.
_HRV_WORDS = {"UNBALANCED": "niezrównoważone", "LOW": "niskie", "POOR": "słabe", "UNKNOWN": "bez oceny zegarka"}


def record_for_day(records, day: str) -> dict:
    """Rekord z podanego dnia albo pusty słownik: starszy pomiar nie udaje dzisiejszego."""
    return next((record for record in records or [] if str(record.get("date", ""))[:10] == day), {})


_NORM_DAYS = 28
_NORM_MIN_READINGS = 7
# Najmniejsze „zwykłe wahanie”: przy bardzo równych pomiarach (np. tętno zawsze 50) ostrzeżenie
# pojawiałoby się już po 1 bpm albo 2 punktach snu. Wartości to typowy szum pomiaru z zegarka.
_MIN_SPREAD = {"rhr": 2.0, "sleep": 5.0, "stress": 4.0}
# Do 1 zwykłego wahania od normy — w normie; do 2,5 — wyraźne odchylenie; dalej — duże odchylenie.
_WARN_SPREADS = 2.5


def _limits(mean, spread):
    """Progi całkowite z normy: górne (tętno, stres) i dolne (sen)."""
    return {"mean": round(mean, 1), "spread": round(spread, 1),
            "ok": math.floor(mean + spread), "warn": math.floor(mean + _WARN_SPREADS * spread),
            "ok_low": math.ceil(mean - spread), "warn_low": math.ceil(mean - _WARN_SPREADS * spread)}


def _norm(records, day, key, kind):
    """Średnia i zwykłe wahanie wartości ``key`` z 28 dni przed ``day`` (min. 7 pomiarów), inaczej None."""
    try:
        end = datetime.strptime(day, '%Y-%m-%d')
    except (TypeError, ValueError):
        return None
    start = (end - timedelta(days=_NORM_DAYS)).strftime('%Y-%m-%d')
    values = [record.get(key) for record in records or []
              if start <= str(record.get('date', ''))[:10] < day and isinstance(record.get(key), (int, float))]
    if len(values) < _NORM_MIN_READINGS:
        return None
    return _limits(statistics.fmean(values), max(statistics.pstdev(values), _MIN_SPREAD[kind]))


def personal_norms(data, day: str) -> dict:
    """Normy tej osoby z ostatnich 4 tygodni: tętno spoczynkowe, ocena snu, średni stres."""
    health = data.get('daily_health')
    return {"rhr": _norm(health, day, 'rhr', 'rhr'),
            "sleep": _norm(data.get('sleep'), day, 'score', 'sleep'),
            "stress": _norm(health, day, 'stress_avg', 'stress')}


def rhr_baseline(daily_health, day: str) -> float | None:
    """Osobista norma tętna spoczynkowego (średnia z 28 dni przed ``day``), inaczej None."""
    norm = _norm(daily_health, day, 'rhr', 'rhr')
    return norm["mean"] if norm else None


def _num(value) -> str:
    return f"{value:g}".replace(".", ",") if isinstance(value, (int, float)) else str(value)


def _range_text(points, low, high, unit=""):
    """„; 1 pkt — 27–32” albo nic, gdy przedział jest pusty (np. obcięty granicą Garmina)."""
    if low > high:
        return ""
    span = f"{low}" if low == high else f"{low}–{high}"
    return f"; {points} pkt — {span}{unit}"


def compute_readiness_breakdown(data, *, norms=None, rhr_baseline=None):
    """Ocena gotowości z punktami za każdy sygnał.

    ``norms`` (z ``personal_norms()``): tętno spoczynkowe, sen i stres są oceniane wobec normy tej osoby
    z ostatnich 4 tygodni (średnia i zwykłe wahania), z granicami według kategorii Garmina. HRV porównuje zegarek
    z zakresem tej osoby. Bez normy: tętno spoczynkowe nie jest oceniane, sen i stres — według kategorii Garmina.
    ``rhr_baseline`` — dawny sposób podania samej normy tętna (zgodność wsteczna).
    Każdy wiersz ``details`` ma ``scoring``: za co punkty, z liczbami tej osoby.
    """
    norms = dict(norms or {})
    if rhr_baseline is not None and not norms.get("rhr"):
        norms["rhr"] = _limits(rhr_baseline, _MIN_SPREAD["rhr"])
    rhr_norm, sleep_norm, stress_norm = norms.get("rhr"), norms.get("sleep"), norms.get("stress")
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

    weights = {'rhr': 2.5, 'hrv': 3.0, 'sleep': 2.5, 'stress': 2.0}

    scoring = {}

    def unavailable(name, metric, message):
        missing_metrics.append(name)
        details.append({"metric": metric, "status": "UNKNOWN", "message": message,
                        "points": None, "max_points": weights[name], "scoring": scoring.get(name)})

    def measured(name, metric, status, points, message):
        """Oceniony sygnał: punkty trafiają do wyniku i do wiersza na stronie Analiza."""
        nonlocal raw_score
        available_metrics.append(name)
        raw_score += points
        details.append({"metric": metric, "status": status, "message": message,
                        "points": points, "max_points": weights[name], "scoring": scoring.get(name)})

    def decimal(value):
        return str(value).replace('.', ',')

    # 1. Tętno spoczynkowe — wobec normy tej osoby i jej zwykłych wahań.
    if rhr_norm:
        norm = f"norma {round(rhr_norm['mean'])}"
        scoring['rhr'] = (f"2,5 pkt — do {rhr_norm['ok']} bpm (Twoja norma {_num(rhr_norm['mean'])} bpm, "
                          f"zwykłe wahania ±{_num(rhr_norm['spread'])})"
                          f"{_range_text('1,5', rhr_norm['ok'] + 1, rhr_norm['warn'], ' bpm')}; "
                          f"0 pkt — powyżej {rhr_norm['warn']} bpm.")
    else:
        scoring['rhr'] = "Liczy się po tygodniu pomiarów — wtedy aplikacja zna Twoją normę i zwykłe wahania."
    if rhr is None:
        unavailable('rhr', 'RHR', "Brak pomiaru tętna spoczynkowego")
    elif not rhr_norm:
        unavailable('rhr', 'RHR', f"Za mało pomiarów, by poznać Twoją normę tętna spoczynkowego ({rhr} bpm; potrzeba tygodnia)")
    elif rhr <= rhr_norm['ok']:
        measured('rhr', 'RHR', "OK", 2.5, f"Tętno spoczynkowe w Twojej normie ({rhr} bpm, {norm})")
    elif rhr <= rhr_norm['warn']:
        measured('rhr', 'RHR', "WARN", 1.5, f"Tętno spoczynkowe lekko podwyższone ({rhr} bpm, {norm})")
    else:
        measured('rhr', 'RHR', "FAIL", 0, f"Tętno spoczynkowe podwyższone ({rhr} bpm, {norm}) — postaw na regenerację")

    # 2. HRV — wobec Twojego zakresu z zegarka.
    hrv_band = (f" ({hrv_baseline_low}–{hrv_baseline_high} ms)"
                if hrv_baseline_low is not None and hrv_baseline_high is not None else "")
    scoring['hrv'] = (f"3 pkt — zegarek ocenia HRV jako „zrównoważone”, a ostatnia noc mieści się w Twoim zakresie{hrv_band}; "
                      "1 pkt — ocena nadal „zrównoważone”, ale ostatnia noc wypadła poniżej Twojego zakresu (pierwszy sygnał "
                      "zmęczenia); 0 pkt — zegarek ocenia HRV jako „niskie” albo „niezrównoważone”. Zakres liczy zegarek "
                      "z Twoich ostatnich ok. 3 tygodni, więc jest osobisty.")
    if any(value is None for value in (hrv_status, hrv_last, hrv_baseline_low, hrv_baseline_high)):
        unavailable('hrv', 'HRV', "Brak pełnych danych HRV (ocena zegarka, wartość lub zakres bazowy)")
    else:
        hrv_range = f"{hrv_last} ms, Twój zakres {hrv_baseline_low}–{hrv_baseline_high}"
        if hrv_status == "BALANCED" and hrv_last >= hrv_baseline_low:
            measured('hrv', 'HRV', "OK", 3, f"HRV zrównoważone ({hrv_range})")
        elif hrv_status == "BALANCED":
            measured('hrv', 'HRV', "WARN", 1, f"HRV zrównoważone, ale poniżej Twojego zakresu ({hrv_range})")
        else:
            measured('hrv', 'HRV', "FAIL", 0, f"HRV {_HRV_WORDS.get(hrv_status, 'niezrównoważone')} ({hrv_range}) — zwolnij")

    # 3. Sen — wobec Twojej średniej; zawsze: 90+ to dobry sen, poniżej 60 słaby (kategorie Garmina).
    hours = f", {decimal(sleep_total)} h" if sleep_total else ""
    if sleep_norm:
        sleep_ok = max(min(sleep_norm['ok_low'], 90), 60)
        sleep_warn = max(sleep_norm['warn_low'], 60)
        scoring['sleep'] = (f"2,5 pkt — ocena {sleep_ok} i więcej (Twoja średnia {_num(sleep_norm['mean'])}, "
                            f"zwykłe wahania ±{_num(sleep_norm['spread'])})"
                            f"{_range_text('1,5', sleep_warn, sleep_ok - 1)}; 0 pkt — poniżej {sleep_warn}. "
                            "Zawsze: 90 i więcej to 2,5 pkt, poniżej 60 — 0 pkt (kategorie Garmina).")
        sleep_note = f"; Twoja średnia {round(sleep_norm['mean'])}"
    else:
        sleep_ok, sleep_warn = 80, 60
        scoring['sleep'] = ("Przez pierwszy tydzień według kategorii Garmina: 2,5 pkt — 80 i więcej; 1,5 pkt — 60–79; "
                            "0 pkt — poniżej 60. Potem wobec Twojej średniej.")
        sleep_note = ""
    if sleep_score_val is None:
        unavailable('sleep', 'Sleep', "Brak oceny snu")
    elif sleep_score_val >= 90:
        measured('sleep', 'Sleep', "OK", 2.5, f"Sen bardzo dobry (ocena {sleep_score_val}/100{hours}{sleep_note})")
    elif sleep_score_val >= sleep_ok:
        label = "Sen w Twojej normie" if sleep_norm else "Sen dobry"
        measured('sleep', 'Sleep', "OK", 2.5, f"{label} (ocena {sleep_score_val}/100{hours}{sleep_note})")
    elif sleep_score_val >= sleep_warn:
        label = "Sen słabszy niż zwykle" if sleep_norm else "Sen przeciętny"
        measured('sleep', 'Sleep', "WARN", 1.5, f"{label} (ocena {sleep_score_val}/100{hours}{sleep_note})")
    else:
        measured('sleep', 'Sleep', "FAIL", 0, f"Słaby sen (ocena {sleep_score_val}/100{hours}{sleep_note})")

    # 4. Stres — wobec Twojej średniej; zawsze: do 25 niski, powyżej 50 wysoki (kategorie Garmina).
    if stress_norm:
        stress_ok = min(max(stress_norm['ok'], 25), 50)
        stress_warn = min(max(stress_norm['warn'], stress_ok), 50)
        scoring['stress'] = (f"2 pkt — do {stress_ok} (Twoja średnia {_num(stress_norm['mean'])}, "
                             f"zwykłe wahania ±{_num(stress_norm['spread'])})"
                             f"{_range_text(1, stress_ok + 1, stress_warn)}; 0 pkt — powyżej {stress_warn}. "
                             "Zawsze: do 25 to 2 pkt, powyżej 50 — 0 pkt (kategorie Garmina).")
        stress_note = f"; Twoja średnia {round(stress_norm['mean'])}"
    else:
        stress_ok, stress_warn = 25, 50
        scoring['stress'] = ("Przez pierwszy tydzień według kategorii Garmina: 2 pkt — do 25; 1 pkt — 26–50; "
                             "0 pkt — powyżej 50. Potem wobec Twojej średniej.")
        stress_note = ""
    if stress is None:
        unavailable('stress', 'Stress', "Brak pomiaru stresu")
    elif stress <= stress_ok:
        label = "Niski poziom stresu" if stress <= 25 or not stress_norm else "Stres w Twojej normie"
        measured('stress', 'Stress', "OK", 2, f"{label} ({stress}{stress_note})")
    elif stress <= stress_warn:
        label = "Stres wyższy niż zwykle" if stress_norm else "Umiarkowany stres"
        measured('stress', 'Stress', "WARN", 1, f"{label} ({stress}{stress_note})")
    else:
        measured('stress', 'Stress', "FAIL", 0, f"Wysoki stres ({stress}{stress_note})")
    available_max_score = sum(weights[name] for name in available_metrics)
    score = round(raw_score / available_max_score * max_score, 1) if available_max_score else 0
    if not available_metrics:
        # Zegarek nic nie zmierzył (np. noc na ładowarce): to brak danych, a nie zła ocena.
        level = "no_data"
    elif score >= 8:
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
        "rhr_baseline": rhr_norm["mean"] if rhr_norm else None,
        "norms": norms,
        "hrv_status": hrv_status,
        "hrv_last": hrv_last,
        "hrv_baseline": f"{hrv_baseline_low}-{hrv_baseline_high}",
        "sleep_score_val": sleep_score_val,
        "sleep_total": sleep_total,
        "stress": stress,
        "details": details,
    }


def readiness_for_day(data, day):
    """Compute readiness using records matching the requested calendar day."""
    health = next(
        (record for record in data.get('daily_health', []) if record.get('date') == day),
        None,
    )
    if health is None:
        return None

    sleep = next(
        (record for record in data.get('sleep', []) if record.get('date') == day),
        None,
    )
    hrv = next(
        (record for record in data.get('hrv', []) if record.get('date') == day),
        None,
    )
    return compute_readiness_breakdown({
        'daily_health': [health],
        'sleep': [sleep] if sleep is not None else [],
        'hrv': [hrv] if hrv is not None else [],
    }, norms=personal_norms(data, day))


def signal_trends(data, day):
    """Return day-over-day trends for readiness signals."""
    previous_day = (datetime.strptime(day, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')

    def record_for(records, target_day):
        return next((record for record in records if record.get('date') == target_day), None)

    health_today = record_for(data.get('daily_health', []), day)
    health_previous = record_for(data.get('daily_health', []), previous_day)
    sleep_today = record_for(data.get('sleep', []), day)
    sleep_previous = record_for(data.get('sleep', []), previous_day)

    def trend(current, previous, favorable_direction):
        if current is None or previous is None:
            direction = None
        elif current > previous:
            direction = 'up'
        elif current < previous:
            direction = 'down'
        else:
            direction = 'flat'
        return {
            'current': current,
            'previous': previous,
            'direction': direction,
            'favorable': direction == favorable_direction if direction in ('up', 'down') else None,
        }

    return {
        'rhr': trend(
            health_today.get('rhr') if health_today else None,
            health_previous.get('rhr') if health_previous else None,
            'down',
        ),
        'stress_avg': trend(
            health_today.get('stress_avg') if health_today else None,
            health_previous.get('stress_avg') if health_previous else None,
            'down',
        ),
        'sleep_score': trend(
            sleep_today.get('score') if sleep_today else None,
            sleep_previous.get('score') if sleep_previous else None,
            'up',
        ),
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

        status = ""
        details = ""
        is_today = (day_date == today_str)
        matched_activity = None
        match_method = 'unmatched'

        if wtype == 'rest':
            if matched_activity is None:
                matched_activity, match_method = find_activity_for_workout(
                    workout=w, activities=activities)
            if matched_activity:
                status = "REST_VIOLATION"
                details = f"Rest day, a zrobiono: {matched_activity['name']} ({matched_activity['distance_km']}km)"
            else:
                status = "OK"
                details = "Odpoczynek — zgodnie z planem"
                match_method = 'unmatched'
        else:
            if matched_activity is None:
                matched_activity, match_method = find_activity_for_workout(
                    workout=w, activities=activities)
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
