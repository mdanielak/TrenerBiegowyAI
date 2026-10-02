# Trener Biegowy AI

Lokalne narzędzie do synchronizacji danych GarminDB, analizy gotowości i zarządzania treningami Garmin. Jedynym wspieranym entry pointem jest `python -m trainer` — na Linuxie, macOS i Windows.

## Instalacja

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p local
cp runner_profile.example.json local/profile.json
```

**Windows PowerShell**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
New-Item -ItemType Directory -Force local
Copy-Item runner_profile.example.json local/profile.json
```

Uzupełnij lokalnie `local/profile.json`. Pełne instrukcje: [Linux](docs/linux_setup.md) oraz [Windows](docs/windows_description.md).

## Codzienna praca

```bash
python -m trainer setup
python -m trainer sync
python -m trainer today
python -m trainer analyze
python -m trainer analyze --ai
python -m trainer zones --sync
python -m trainer workouts new
python -m trainer doctor
python -m trainer privacy-check
```

Przy pierwszym pobraniu lub przebudowie danych użyj `python -m trainer sync --fresh`. Dostępne są też podkomendy `sync`, `analyze`, `workouts`, `privacy-check` i `doctor`; sprawdź `python -m trainer --help` oraz pomoc wybranej podkomendy. Wynik synchronizacji może być częściowy — przed decyzją treningową sprawdź aktualność i kompletność snapshotu.

## Konfiguracja środowiska

Plik `.env` w katalogu głównym projektu jest wczytywany automatycznie i jest ignorowany przez Git. Rzeczywiste zmienne środowiskowe systemu mają pierwszeństwo przed wartościami z `.env`.

| Zmienna | Przeznaczenie |
| --- | --- |
| `HEALTH_DATA_DIR` | Katalog danych GarminDB, domyślnie `~/HealthData`; zawiera `DBs` lub `dbs`. |
| `SNAPSHOT_TTL_SECONDS` | Maksymalny wiek lokalnego snapshotu danych. |
| `GARMIN_EMAIL` | Adres konta Garmin używany przy uwierzytelnianiu. |
| `GARMIN_PASSWORD` | Hasło konta Garmin używane przy uwierzytelnianiu. |
| `AI_BASE_URL` | Adres bazowy opcjonalnego dostawcy AI. |
| `AI_API_KEY` | Klucz API opcjonalnego dostawcy AI. |
| `AI_MODEL` | Nazwa modelu AI do analizy. |
| `AI_DATA_EXPORT_ENABLED` | Zezwolenie na eksport danych do integracji AI. |

GarminDB może użyć tokenów `~/.GarminDb/garmin_tokens.json` i konfiguracji `~/.GarminDb/GarminConnectConfig.json` albo poświadczeń Garmin z powyższych zmiennych. Nie umieszczaj sekretów w plikach śledzonych przez Git.

## Prywatność

`local/` to prywatny stan runtime. Nie dodawaj do repozytorium danych Garmin, baz SQLite, plików FIT/TCX/GPX, tokenów, danych zdrowotnych ani `local/profile.json`. Ochronnie ignorowane są też legacyjne ścieżki `HealthData/`, `memory/`, główny `data_latest.json` oraz `training-plans/_garmin_workouts.jsonl`.

Przed publikacją uruchom:

```bash
python -m trainer privacy-check
python -m pytest
```
