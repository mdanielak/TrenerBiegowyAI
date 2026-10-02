"""Krótki, lokalny widok planu i gotowości na dziś."""
from __future__ import annotations

from services import today as today_service
from services.data_extract import SnapshotStatus
from trainer.config import SNAPSHOT_TTL_SECONDS


def _activity_line(item) -> str:
    """Nazwa nie musi być biegiem, więc fallback jest neutralny."""
    return (f"{item.get('name') or 'aktywność'}, {item.get('distance_km', '?')} km, "
            f"{item.get('duration_min', '?')} min, HR {item.get('avg_hr', '?')}")


def main() -> int:
    report = today_service.get_today_report()
    if report.status == "profile_missing":
        print("Brakuje lokalnego profilu. Uruchom: python -m trainer setup")
        return 5
    if report.status == "snapshot_missing":
        print("Brakuje lokalnego snapshotu danych. Uruchom: python -m trainer sync")
        print("Jeśli to pierwsze uruchomienie, zacznij od: python -m trainer setup")
        return 1
    if report.status == "snapshot_invalid":
        print("Lokalny snapshot danych jest niepoprawny. Uruchom: python -m trainer sync")
        return 1
    assert report.readiness is not None
    assert report.availability is not None
    print(f"DZIŚ: {report.date} ({['poniedziałek', 'wtorek', 'środa', 'czwartek', 'piątek', 'sobota', 'niedziela'][report.weekday_index]})")
    if report.snapshot_status is SnapshotStatus.STALE:
        print(f"⚠ Snapshot nieaktualny (limit {SNAPSHOT_TTL_SECONDS}s). Odśwież: python -m trainer sync")
    else:
        print("Snapshot: aktualny")
    if report.planned:
        print(f"Plan z rejestru: {report.planned.get('name', 'trening')} ({report.planned.get('spec', {}).get('kind', 'typ nieznany')})")
    else:
        print("Plan z rejestru: brak")
    # Jeden dzień może mieć wiele aktywności: dwa biegi, bieg i pływanie, a
    # zegarek dopisuje jeszcze krótki spacer po treningu. Pokazujemy wszystkie
    # w kolejności chronologicznej, żeby żadna nie chowała się za inną.
    day_activities = report.yesterday_activities
    if len(day_activities) == 1:
        print(f"Wczoraj: {_activity_line(day_activities[0])}")
    elif day_activities:
        print(f"Wczoraj ({len(day_activities)} aktywności):")
        for item in day_activities:
            print(f"  {str(item.get('date', ''))[11:16]} {_activity_line(item)}")
    print(f"Gotowość: {report.readiness['level']} ({report.readiness['score']}/{report.readiness['max_score']})")
    print(f"Sygnały: sen {report.signals['sleep_score'] if report.signals['sleep_score'] is not None else '?'}, HRV {report.signals['hrv_status'] if report.signals['hrv_status'] is not None else '?'}, RHR {report.signals['rhr'] if report.signals['rhr'] is not None else '?'}, stres {report.signals['stress_avg'] if report.signals['stress_avg'] is not None else '?'}")
    if report.availability["available"]:
        print(f"Dostępność: dzień treningowy ({report.availability['min_minutes']}–{report.availability['max_minutes']} min)")
    else:
        print("Dostępność: dzień bez zaplanowanej dostępności")
    suggestion = "realizuj zaplanowany trening spokojnie" if report.suggestion == "follow_plan" else "postaw na odpoczynek lub bardzo lekki ruch"
    print(f"Sugestia (heurystyka): {suggestion}.")
    print("To nie jest porada medyczna.")
    return 0
