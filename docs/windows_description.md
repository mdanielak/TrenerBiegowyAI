# Trener Biegowy AI na Windows

## Uruchamianie

W aktywnym środowisku Pythona używaj głównego CLI:

```powershell
python -m trainer --help
python -m trainer sync --fresh
python -m trainer analyze --ai
python -m trainer privacy-check
python -m pytest tests/ -v
```

API jest niezależne od CLI i uruchamia się osobno:

```powershell
uvicorn api.main:app --reload
```

## Konfiguracja i dane lokalne

Skopiuj `runner_profile.example.json` do `local/profile.json` i uzupełnij go lokalnie. Zmienne środowiskowe (`HEALTH_DATA_DIR`, `SNAPSHOT_TTL_SECONDS`, ustawienia AI) opisuje `.env.example`; nie zapisuj w repozytorium sekretów ani danych zdrowotnych.

GarminDB jest backendem danych lokalnych. Nie publikuj jego baz, tokenów, danych aktywności ani snapshotów. Katalog `local/` zawiera prywatny stan: `profile.json`, `data_latest.json`, `memory/` oraz `workout-registry.jsonl`.

## Treningi Garmin

```powershell
python -m trainer workouts usage
python -m trainer workouts create easy "Łatwy 40 min" 40 2026-10-01
```

`workouts create` tworzy trening na Garminie, a `workouts usage --delete` może usuwać nieużywane treningi. Rzeczywiste połączenie z Garminem lub AI wymaga lokalnej konfiguracji i nie jest potwierdzane przez tę dokumentację.

Prywatne ścieżki legacy, w tym `HealthData/`, `memory/`, główny `data_latest.json` i `training-plans/_garmin_workouts.jsonl`, nadal są ochronnie ignorowane przez Git.
