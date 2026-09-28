# Trener Biegowy AI na Windows

## Uruchamianie

Uruchamiaj skrypty w aktywnym środowisku Pythona:

```powershell
python data_sync.py
python analyze_and_readiness.py
python -m pytest tests/ -v
```

## Dane i konfiguracja lokalna

GarminDB przechowuje lokalnie bazy aktywności, dane zdrowotne i konfigurację. Nie publikuj tych danych ani tokenów. Projekt ignoruje katalogi danych Garmin, bazy SQLite, pliki aktywności, snapshoty JSON, logi i cache.

`runner_profile.example.json` jest publicznym wzorem. Utwórz lokalny `runner_profile.local.json` na jego podstawie; runtime używa go przed przykładem, a plik lokalny pozostaje ignorowany przez Git.

## GarminDB CLI

Synchronizacja używa bieżącego interpretera Pythona oraz lokalnego `garmindb_cli.py`, kopii w `GarminDB/` albo polecenia `garmindb_cli` w `PATH`. Lokalny skrypt CLI jest ignorowaną zależnością. Można też zainstalować `garmindb` w aktywnym środowisku.

## Plany

Aktualna strategia znajduje się w `training-plans/long-term/mdanielak-half-marathon-2027.md`. Rejestr `training-plans/_garmin_workouts.jsonl` jest lokalny i ignorowany; nie jest planem treningowym.
