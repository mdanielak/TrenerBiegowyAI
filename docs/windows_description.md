# Trener Biegowy AI na Windows

## Uruchamianie

Uruchamiaj skrypty w aktywnym środowisku Pythona:

```powershell
python data_sync.py
python analyze_and_readiness.py
python -m pytest tests/ -v
```

## Dane i konfiguracja lokalna

GarminDB przechowuje lokalnie bazy aktywności, dane zdrowotne i konfigurację. Nie publikuj tych danych ani tokenów. Architektura single-user trzyma prywatny stan w całym ignorowanym katalogu `local/`: `profile.json`, `data_latest.json`, `memory/` i `workout-registry.jsonl`. Projekt ignoruje też katalogi danych Garmin, bazy SQLite, pliki aktywności, snapshoty JSON, logi i cache; starsze lokalizacje prywatne pozostają chronione na czas migracji.

`runner_profile.example.json` jest publicznym wzorem. Docelowy profil runtime przechowuj w `local/profile.json`; cały katalog pozostaje ignorowany przez Git. `runner_profile.local.json` jest starszą, nadal ignorowaną lokalizacją.

## GarminDB CLI

Synchronizacja używa bieżącego interpretera Pythona oraz lokalnego `garmindb_cli.py`, kopii w `GarminDB/` albo polecenia `garmindb_cli` w `PATH`. Lokalny skrypt CLI jest ignorowaną zależnością. Można też zainstalować `garmindb` w aktywnym środowisku.

## Plany

Aktualna strategia znajduje się w `training-plans/long-term/half-marathon-2027.md`. Rejestr `local/workout-registry.jsonl` jest lokalny i ignorowany; nie jest planem treningowym.
