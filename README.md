# Trener Biegowy AI

Lokalny system wspomagający analizę treningów biegowych, synchronizację GarminDB i rekomendacje AI.

## Instalacja i dane lokalne

```bash
pip install -r requirements.txt
python data_sync.py --fresh
```

Nie dodawaj danych dostępowych, tokenów ani danych zdrowotnych do plików projektu. Utrzymuj je wyłącznie w lokalnej konfiguracji środowiska zgodnej z GarminDB.

Projekt ignoruje dane Garmin (`HealthData/`, bazy SQLite, pliki FIT/TCX/GPX), snapshoty JSON, logi, cache, lokalny rejestr uploadów i katalog `memory/`.

## Profil biegacza

- `runner_profile.example.json` jest neutralnym, publicznym wzorem konfiguracji.
- Skopiuj go lokalnie jako `runner_profile.local.json` i uzupełnij własne dane. Ten plik jest ignorowany przez Git.
- Runtime wybiera profil lokalny, a gdy go nie ma — bezpieczny przykład.

## Synchronizacja i analiza

```bash
python data_sync.py
python data_sync.py --fresh
python analyze_and_readiness.py
python analyze_and_readiness.py --ai
```

`data_latest.json` jest lokalnym, generowanym snapshotem. Zawiera ostatnie aktywności oraz dane zdrowotne, snu, HRV i wagi.

`services/data_extract.py` korzysta z interpretera, który uruchomił aplikację. Szuka lokalnego (ignorowanego) `garmindb_cli.py`, kopii w `GarminDB/` lub polecenia `garmindb_cli` dostępnego w `PATH`. Alternatywnie zainstaluj `garmindb` w aktywnym środowisku.

## Strategia i plany

- `training-plans/long-term/mdanielak-half-marathon-2027.md` to aktualna długoterminowa strategia HM.
- Tygodniowe JSON-y są opcjonalnymi planami wykonawczymi.
- `training-plans/_garmin_workouts.jsonl` jest lokalnym, ignorowanym rejestrem uploadów Garmin, a nie planem.

## Testy

```bash
python -m pytest tests/ -v
```

## Bezpieczeństwo

- `.env` i `.env.*` są ignorowane, z wyjątkiem śledzonego `.env.example`.
- Tokeny, cookies, klucze i certyfikaty są ignorowane.
- Lokalna konfiguracja GarminDB oraz tokeny pozostają poza publicznym repozytorium.
