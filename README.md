# Trener Biegowy AI

Lokalne narzędzie do synchronizacji danych przez GarminDB, analizy gotowości i zarządzania treningami Garmin. Główny interfejs to CLI `trainer` (wersja 0.2.0); API uruchamia się niezależnie przez Uvicorn.

## Szybki start

```powershell
pip install -r requirements.txt
Copy-Item runner_profile.example.json local/profile.json
# ustaw zmienne z .env.example w środowisku systemowym
python -m trainer sync --fresh
python -m trainer analyze
```

`local/profile.json` jest prywatnym profilem runtime. Nie dodawaj go, danych Garmin, baz SQLite, plików FIT/TCX/GPX, tokenów ani danych zdrowotnych do repozytorium.

## Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p local
cp runner_profile.example.json local/profile.json
# opcjonalnie, gdy dane GarminDB są poza domyślnym ~/HealthData:
export HEALTH_DATA_DIR="$HOME/HealthData"
python -m trainer doctor
python -m trainer sync --fresh
python -m trainer analyze
```

Na systemach rozróżniających wielkość liter GarminDB używa katalogu `DBs` w
`HEALTH_DATA_DIR`. Doctor toleruje istniejący katalog `dbs`, ale zgłasza wtedy
ostrzeżenie, aby można było poprawić nazwę katalogu.

## Codzienny workflow

```powershell
python -m trainer sync
python -m trainer analyze
python -m trainer analyze --ai
```

Przy pierwszym pobraniu lub przebudowie danych użyj `sync --fresh`. Wynik synchronizacji może być częściowy; przed wnioskiem treningowym sprawdź aktualność i kompletność snapshotu.

## Komendy CLI

```powershell
python -m trainer --help
python -m trainer --version
python -m trainer sync [--fresh]
python -m trainer analyze [--ai]
python -m trainer doctor
python -m trainer privacy-check
python -m trainer workouts usage [--delete]
```

### Tworzenie treningów

```powershell
python -m trainer workouts create easy "Łatwy 40 min" 40 2026-10-01
python -m trainer workouts create tempo "Tempo" 45 5:40 5:55 2026-10-02
python -m trainer workouts create intervals "Interwały" 6 180 120 4:45 5:00 2026-10-03
python -m trainer workouts create long "Długie wybieganie" 90 2026-10-04
python -m trainer workouts create strides "Przebieżki" 35 6 2026-10-05
```

Daty mają format `RRRR-MM-DD`. `create` tworzy trening na Garminie, a `workouts usage --delete` może usuwać nieużywane treningi na Garminie — przed uruchomieniem sprawdź argumenty i konto.

## Konfiguracja, API i prywatność

Nazwy zmiennych środowiskowych opisuje `.env.example`; wartości dostępowe przechowuj wyłącznie lokalnie. `HEALTH_DATA_DIR` wskazuje lokalny katalog danych GarminDB (z podkatalogiem `DBs`). Dane, bazy SQLite i tokeny nie trafiają do repozytorium. `python -m trainer doctor` sprawdza wyłącznie lokalną konfigurację i integralność baz w trybie tylko do odczytu — nie synchronizuje danych ani nie loguje się do Garmin. GarminDB jest backendem synchronizacji i lokalnych danych. Opcjonalne API uruchom osobno, np.:

```powershell
uvicorn api.main:app --reload
```

Przed publikacją uruchom:

```powershell
python -m trainer privacy-check
python -m pytest tests/ -v
```

Prywatne ścieżki legacy (`HealthData/`, `memory/`, główny `data_latest.json`, bazy i pliki aktywności oraz `training-plans/_garmin_workouts.jsonl`) nadal są ochronnie ignorowane przez Git.

## Wspierany entry point

Jedynym wspieranym entry pointem aplikacji jest `python -m trainer`. Używaj go
w dokumentacji, automatyzacji i codziennej pracy zamiast rootowych skryptów.
