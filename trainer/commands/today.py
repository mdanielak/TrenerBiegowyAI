"""Krótki, lokalny widok planu i gotowości na dziś."""
from __future__ import annotations

from datetime import datetime

from services.data_extract import SnapshotStatus, read_snapshot_status
from services.readiness import compute_readiness_breakdown
from services.workout_registry import list_workouts
from trainer.config import SNAPSHOT_TTL_SECONDS
from trainer.preferences import get_weekly_availability
from trainer.profile_store import load_profile


def _activity_line(item) -> str:
    """Nazwa nie musi być biegiem, więc fallback jest neutralny."""
    return (f"{item.get('name') or 'aktywność'}, {item.get('distance_km', '?')} km, "
            f"{item.get('duration_min', '?')} min, HR {item.get('avg_hr', '?')}")


def _today_registry_entry(today: str):
    """Zwróć najnowszy aktywny trening na datę z aktualnej projekcji rejestru."""
    return next(
        (entry for entry in list_workouts("active") if entry.get("date") == today),
        None,
    )


def main() -> int:
    try:
        load_profile()
    except FileNotFoundError:
        print("Brakuje lokalnego profilu. Uruchom: python -m trainer setup")
        return 5
    snapshot = read_snapshot_status()
    if snapshot.status is SnapshotStatus.MISSING:
        print("Brakuje lokalnego snapshotu danych. Uruchom: python -m trainer sync")
        print("Jeśli to pierwsze uruchomienie, zacznij od: python -m trainer setup")
        return 1
    if snapshot.status is SnapshotStatus.INVALID:
        print("Lokalny snapshot danych jest niepoprawny. Uruchom: python -m trainer sync")
        return 1
    now = datetime.now()
    today = now.date().isoformat()
    print(f"DZIŚ: {today} ({['poniedziałek', 'wtorek', 'środa', 'czwartek', 'piątek', 'sobota', 'niedziela'][now.weekday()]})")
    if snapshot.status is SnapshotStatus.STALE:
        print(f"⚠ Snapshot nieaktualny (limit {SNAPSHOT_TTL_SECONDS}s). Odśwież: python -m trainer sync")
    else:
        print("Snapshot: aktualny")
    planned = _today_registry_entry(today)
    if planned:
        print(f"Plan z rejestru: {planned.get('name', 'trening')} ({planned.get('spec', {}).get('kind', 'typ nieznany')})")
    else:
        print("Plan z rejestru: brak")
    data = snapshot.data or {}
    activities = data.get("activities", [])
    yesterday = (now.date().fromordinal(now.date().toordinal() - 1)).isoformat()
    # Jeden dzień może mieć wiele aktywności: dwa biegi, bieg i pływanie, a
    # zegarek dopisuje jeszcze krótki spacer po treningu. Pokazujemy wszystkie
    # w kolejności chronologicznej, żeby żadna nie chowała się za inną.
    day_activities = sorted(
        (item for item in activities if str(item.get("date", ""))[:10] == yesterday),
        key=lambda item: str(item.get("date", "")),
    )
    if len(day_activities) == 1:
        print(f"Wczoraj: {_activity_line(day_activities[0])}")
    elif day_activities:
        print(f"Wczoraj ({len(day_activities)} aktywności):")
        for item in day_activities:
            print(f"  {str(item.get('date', ''))[11:16]} {_activity_line(item)}")
    breakdown = compute_readiness_breakdown(data)
    print(f"Gotowość: {breakdown['level']} ({breakdown['score']}/{breakdown['max_score']})")
    health = (data.get("daily_health") or [{}])[0]
    sleep = (data.get("sleep") or [{}])[0]
    hrv = (data.get("hrv") or [{}])[0]
    print(f"Sygnały: sen {sleep.get('score', '?')}, HRV {hrv.get('status', '?')}, RHR {health.get('rhr', '?')}, stres {health.get('stress_avg', '?')}")
    availability = get_weekly_availability(("mon", "tue", "wed", "thu", "fri", "sat", "sun")[now.weekday()])
    if availability["available"]:
        print(f"Dostępność: dzień treningowy ({availability['min_minutes']}–{availability['max_minutes']} min)")
    else:
        print("Dostępność: dzień bez zaplanowanej dostępności")
    suggestion = "realizuj zaplanowany trening spokojnie" if planned and breakdown["level"] != "not_ready" else "postaw na odpoczynek lub bardzo lekki ruch"
    print(f"Sugestia (heurystyka): {suggestion}.")
    print("To nie jest porada medyczna.")
    return 0
