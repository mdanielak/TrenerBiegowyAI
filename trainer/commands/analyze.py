# -*- coding: utf-8 -*-
"""
Analiza gotowości treningowej + porównanie z planem.
Uruchomienie: python -m trainer analyze [--ai]
"""
import sys
import io
import logging
from datetime import datetime, timedelta

from ..logging_config import setup_logging
from ..core import check_hrv_alert
from ..config import DATA_LATEST, AI_DATA_EXPORT_ENABLED

logger = logging.getLogger(__name__)
from services.data_extract import SnapshotStatus, read_snapshot_status
from services.readiness import compute_readiness_breakdown, compare_plan_vs_actual
from services.plan_files import find_current_plan, get_today_workout_from_plan

# --- Windows encoding fix ---
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def print_weekly_activities(data, today):
    """Print this week's running activities."""
    monday = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')
    week_acts = [a for a in data['activities']
                 if a['date'][:10] >= monday and a['type'].startswith('running')]

    print(f"\n--- Treningi w tym tygodniu (pon {monday} — dzisiaj) ---")
    if week_acts:
        total_km = 0
        total_min = 0
        for a in sorted(week_acts, key=lambda x: x['date']):
            print(f"  {a['date']}: {a['name'] or 'bieg'}")
            print(f"    Dystans: {a['distance_km']}km | Tempo: {a['pace']} | "
                  f"HR: {a['avg_hr']}/{a['max_hr']} | TE: {a['te']}")
            total_km += a['distance_km']
            total_min += a['duration_min']
        print(f"  --- Suma: {total_km:.1f} km, ~{total_min:.0f} min ---")
    else:
        print("  Brak danych o treningach w tym tygodniu")


def print_health_data(data):
    """Print recent health, sleep, HRV, weight."""
    print("\n--- Ostatnie dni — zdrowie ---")
    for h in data['daily_health'][:7]:
        print(f"  {h['date']}: RHR={h['rhr']}, HR={h['hr_min']}-{h['hr_max']}, "
              f"kroki={h['steps']}, stres={h['stress_avg']}, SpO2={h['spo2']}%")

    print("\n--- Sen ---")
    for s in data['sleep'][:7]:
        print(f"  {s['date']}: {s['total_h']}h, gleboki={s['deep_h']}h, "
              f"REM={s['rem_h']}h, score={s['score']}, {s['qualifier'] or ''}")

    print("\n--- HRV ---")
    for h in data['hrv'][:7]:
        print(f"  {h['date']}: tydz={h['weekly_avg']}, ostatnia={h['last_night']}, "
              f"base={h['baseline_low']}-{h['baseline_high']}, status={h['status']}")

    print("\n--- Waga ---")
    for w in data['weight'][:3]:
        print(f"  {w['date']}: {w['weight_kg']} kg")


def print_hrv_alert(data):
    """Print HRV alert if active."""
    hrv_alert = check_hrv_alert(data.get('hrv', []))
    if hrv_alert:
        print(f"\n{'!' * 60}")
        print(f"  ALERT: HRV NISKIE OD {hrv_alert['days']} DNI!")
        print(f"  Statusy: {', '.join(hrv_alert['statuses'])}")
        print(f"  Wartości: {hrv_alert['values']} (baseline: {hrv_alert['baseline']})")
        print("  Organizm sie NIE regeneruje.")
        print("  REKOMENDACJA: Odpoczynek lub bardzo lekki bieg regeneracyjny.")
        print(f"{'!' * 60}")


def print_readiness(breakdown):
    """Print readiness score and breakdown."""
    print(f"\n{'=' * 60}")
    print("OCENA GOTOWOSCI")
    print('=' * 60)

    print(f"\n  RHR: {breakdown['rhr']}")
    print(f"  HRV: {breakdown['hrv_last']} (norma {breakdown['hrv_baseline']})")
    print(f"  Sen: {breakdown['sleep_total']}h (score: {breakdown['sleep_score_val']})")
    print(f"  Stres: {breakdown['stress']}")

    for d in breakdown['details']:
        tag = f"[{d['status']:>4}]"
        print(f"  {tag}  {d['message']}")

    print(f"\n{'=' * 60}")
    print(f"WYNIK GOTOWOSCI: {breakdown['score']}/{breakdown['max_score']}")
    print(f"POZIOM: {breakdown['level']}")
    print('=' * 60)

    if breakdown['insufficient_data']:
        print(f"\n[UWAGA: NIEPELNE DANE] Pokrycie: {breakdown['data_coverage'] * 100:.0f}% | Pewnosc: {breakdown['confidence']}")
        print(f"  Brakujace metryki: {', '.join(breakdown['missing_metrics'])}")
        print("  Wynik jest znormalizowany do dostepnych metryk i nie stanowi pelnej oceny fizjologicznej.")

    level = breakdown['level']
    if level == "no_data":
        print("\n[BRAK POMIAROW] Zegarek nie zmierzyl tej nocy snu, HRV, tetna ani stresu.")
        print("   Zdecyduj po samopoczuciu albo zsynchronizuj dane ponownie.")
    elif level == "ready":
        print("\n[GOTOWY] Organizm w pelni zregenerowany. Realizuj plan.")
    elif level == "ready_with_reserves":
        print("\n[GOTOWY Z REZERWA] Lekkie zmeczenie, trening OK.")
        print("   Uwazaj na tempo w pierwszych powtorzeniach.")
    else:
        print("\n[NIE GOTOWY] Potrzebujesz regeneracji.")
        print("   Zastap trening biegiem regeneracyjnym 30-40 min.")


def print_plan_comparison(plan, data, today):
    """Print plan vs actual comparison and today's workout."""
    results = compare_plan_vs_actual(plan, data['activities'], today)

    print("\n--- Porownanie: PLAN vs WYKONANIE ---")
    print(f"  Plan: {plan['start_date']} — {plan['end_date']}")
    print(f"  Priorytet: {plan['priority']}")
    print()

    status_symbols = {
        "OK": "✅ OK",
        "MISSING": "❌ POMINIĘCIE",
        "REST_VIOLATION": "❌ NARUSZENIE",
        "SCHEDULED": "⏳ PLAN",
        "HR_WARNING": "⚠️ HR",
        "DISTANCE_WARNING": "⚠️ DYSTANS",
    }

    for r in results:
        marker = "  " if not r['is_today'] else "▸ "
        symbol = status_symbols.get(r['status'], r['status'])
        print(f"  {marker}{r['day']} {r['date']}: {symbol}")
        print(f"      {r['name']} — {r['details']}")
    print()

    # Today's workout
    today_workout = get_today_workout_from_plan(plan, today)
    if today_workout:
        print(f"--- Dzisiejszy plan: {today_workout['name']} ---")
        print(f"  Typ: {today_workout['type']}")
        if today_workout['type'] != 'rest':
            print(f"  Dystans: {today_workout.get('distance_km', '?')} km")
            print(f"  Tempo: {today_workout.get('pace_target', '?')}")
            print(f"  HR: {today_workout.get('hr_target', '?')}")
        print(f"  {today_workout.get('notes', '')}")
    else:
        print("\n--- Brak planu na biezacy tydzien ---")
        print("  Brak aktywnego planu tygodniowego; analiza gotowości działa nadal.")


def main(use_ai=False, strict_ai=False):
    """Main CLI entry point."""
    setup_logging()

    # Load data
    logger.info("Loading data from %s", DATA_LATEST)
    snapshot = read_snapshot_status()
    if snapshot.status is SnapshotStatus.MISSING:
        logger.error("Data file not found: %s", DATA_LATEST)
        print(f"STATUS SNAPSHOTU: missing ({DATA_LATEST})")
        print(f"BLAD: Plik {DATA_LATEST} nie istnieje.")
        print("Uruchom najpierw: python -m trainer sync")
        return 1
    if snapshot.status is SnapshotStatus.INVALID:
        logger.error("Corrupted data file: %s — %s", DATA_LATEST, snapshot.error)
        print(f"STATUS SNAPSHOTU: invalid ({snapshot.error})")
        print(f"BLAD: Plik {DATA_LATEST} jest uszkodzony: {snapshot.error}")
        print("Uruchom ponownie: python -m trainer sync")
        return 1
    if snapshot.status is SnapshotStatus.STALE:
        print("STATUS SNAPSHOTU: stale — analiza użyje nieaktualnych danych.")
    else:
        print("STATUS SNAPSHOTU: fresh")
    data = snapshot.data
    logger.info("Loaded: %d activities, %d health, %d sleep, %d HRV records",
                len(data.get('activities', [])),
                len(data.get('daily_health', [])),
                len(data.get('sleep', [])),
                len(data.get('hrv', [])))

    today = datetime.now()
    print("=" * 60)
    print(f"OCENA GOTOWOSCI TRENINGOWEJ — {today.strftime('%Y-%m-%d %A')}")
    print("=" * 60)

    # 1. Weekly activities
    print_weekly_activities(data, today)

    # 2. Health data
    print_health_data(data)

    # 3. HRV alert
    print_hrv_alert(data)

    # 4. Readiness
    breakdown = compute_readiness_breakdown(data)
    print_readiness(breakdown)

    # 5. Plan comparison
    plan = find_current_plan(today)
    if plan:
        print_plan_comparison(plan, data, today)
    else:
        print("\n--- Brak planu na biezacy tydzien ---")
        print("  Brak aktywnego planu tygodniowego; analiza gotowości działa nadal.")

    # 6. AI recommendation (optional)
    if use_ai:
        print(f"\n{'=' * 60}")
        print("REKOMENDACJA AI")
        print('=' * 60)
        if not AI_DATA_EXPORT_ENABLED:
            print("  AI jest wyłączone: ustaw AI_DATA_EXPORT_ENABLED=true, aby zezwolić na eksport danych do providera.")
            return 3 if strict_ai else 0
        try:
            from ai.context import build_training_context
            from ai.recommendation import get_daily_recommendation
            from ai.openai_compatible import OpenAICompatibleProvider
            from ..config import AI_BASE_URL, AI_API_KEY, AI_MODEL

            if not AI_API_KEY:
                logger.error("AI_API_KEY not set")
                print("  BLAD: AI_API_KEY nie ustawione. Ustaw zmienne srodowiskowe.")
                from ..errors import env_hint
                print(f"  Przykład: {env_hint('AI_API_KEY')}")
                return 3 if strict_ai else 0

            logger.info("Initializing AI provider: model=%s, base_url=%s", AI_MODEL, AI_BASE_URL)
            provider = OpenAICompatibleProvider(AI_BASE_URL, AI_API_KEY, AI_MODEL)
            context = build_training_context(data, plan, today)
            logger.info("Requesting AI recommendation")
            recommendation = get_daily_recommendation(provider, context)
            logger.info("AI recommendation received: readiness=%s, adjustment=%s",
                        recommendation.readiness, recommendation.adjustment_needed)

            print(f"\n  Gotowosc: {recommendation.readiness}")
            print(f"  Rekomendacja: {recommendation.recommendation}")
            if recommendation.planned_workout:
                print(f"  Planowany trening: {recommendation.planned_workout}")
            if recommendation.adjustment_needed:
                print("  ⚠️  Zalecana korekta planu")
            print(f"  Uzasadnienie: {recommendation.reasoning_summary}")
            if recommendation.warnings:
                print("  Ostrzezenia:")
                for w in recommendation.warnings:
                    print(f"    - {w}")
        except ImportError as e:
            logger.error("AI module not found: %s", e)
            print(f"  BLAD: Modul AI nie znaleziony: {e}")
            print("  Zainstaluj zaleznosci: pip install openai pydantic")
            return 3 if strict_ai else 0
        except Exception as e:
            logger.exception("AI recommendation failed")
            print(f"  BLAD AI: {e}")
            return 1
    return 0


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Analizuje gotowość treningową")
    parser.add_argument('--ai', action='store_true', help='dołącz rekomendację AI')
    args = parser.parse_args()
    raise SystemExit(main(use_ai=args.ai))
