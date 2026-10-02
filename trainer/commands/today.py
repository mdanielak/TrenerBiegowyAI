"""Krótki, lokalny widok planu i gotowości na dziś."""
from __future__ import annotations

from datetime import datetime

from services.data_extract import SnapshotStatus, read_snapshot_status
from services.readiness import compute_readiness_breakdown
from services.workout_registry import load_events
from trainer.config import SNAPSHOT_TTL_SECONDS
from trainer.preferences import get_weekly_availability
from trainer.profile_store import load_profile


def _today_registry_entry(today: str):
    """Rejestr jest append-only; ostatni pasujący wpis jest rozstrzygający."""
    found = None
    for entry in load_events():
        if entry.get("event") == "added" and entry.get("date") == today:
            found = entry
    return found


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
    # Zegarek zapisuje spacer po biegu jako osobną, późniejszą aktywność tego
    # samego dnia, a lista jest posortowana od najnowszych. Bez filtru typu
    # wygrywałby więc spacer. Bieg ma pierwszeństwo; inną aktywność pokazujemy
    # tylko wtedy, gdy danego dnia nie było biegu.
    day_activities = [item for item in activities if str(item.get("date", ""))[:10] == yesterday]
    runs = [item for item in day_activities if str(item.get("type", "")).startswith("running")]
    yesterday_activity = next(iter(runs or day_activities), None)
    if yesterday_activity:
        print(f"Wczoraj: {yesterday_activity.get('name') or 'bieg'}, {yesterday_activity.get('distance_km', '?')} km, {yesterday_activity.get('duration_min', '?')} min, HR {yesterday_activity.get('avg_hr', '?')}")
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
