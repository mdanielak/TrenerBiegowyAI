# Trener Biegowy AI na Windows

Windows jest w pełni wspieraną platformą, podobnie jak Linux i macOS. Instrukcję dla Linuxa znajdziesz w [linux_setup.md](linux_setup.md).

## Uruchamianie

W aktywnym środowisku Pythona używaj głównego CLI:

```powershell
python -m trainer --help
python -m trainer sync --fresh
python -m trainer analyze --ai
python -m trainer privacy-check
python -m pytest
```

API jest niezależne od CLI i uruchamia się osobno:

```powershell
uvicorn api.main:app --reload
```

## Konfiguracja i dane lokalne

Skopiuj `runner_profile.example.json` do `local/profile.json` i uzupełnij go lokalnie. Plik `.env` w katalogu projektu jest wczytywany automatycznie, a rzeczywiste zmienne systemowe mają przed nim pierwszeństwo. Nie zapisuj w repozytorium sekretów ani danych zdrowotnych.

GarminDB jest backendem danych lokalnych. Nie publikuj jego baz, tokenów, danych aktywności ani snapshotów. Katalog `local/` zawiera prywatny stan: `profile.json`, `data_latest.json`, `memory/` oraz `workout-registry.jsonl`.

## Przenoszenie danych między Windows i Linuxem

Przed migracją na Linux skopiuj dane na pendrive skryptem `scripts/export_healthdata.ps1`; domyślnie pomija on kopie `*.bak*` i celowo nie eksportuje `~/.GarminDb`. Na Linuxie użyj `scripts/migrate_healthdata.sh`. Bazy SQLite są przenośne binarnie, ale Linux rozróżnia `DBs` i `dbs` wielkością liter. Po przeniesieniu zaloguj się ponownie do GarminDB i uruchom `python -m trainer doctor`.

## Treningi Garmin

```powershell
python -m trainer workouts usage
python -m trainer workouts create easy "Łatwy 40 min" 40 2026-10-01
```

`workouts create` tworzy trening na Garminie, a `workouts usage --delete` może usuwać nieużywane treningi. Rzeczywiste połączenie z Garminem lub AI wymaga lokalnej konfiguracji i nie jest potwierdzane przez tę dokumentację.

Prywatne ścieżki legacy, w tym `HealthData/`, `memory/`, główny `data_latest.json` i `training-plans/_garmin_workouts.jsonl`, nadal są ochronnie ignorowane przez Git.
