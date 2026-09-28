# Trener Biegowy AI

Lokalny system wspomagający analizę treningów biegowych, synchronizację GarminDB i rekomendacje AI.

## Instalacja i dane lokalne

```bash
pip install -r requirements.txt
python data_sync.py --fresh
```

Nie dodawaj danych dostępowych, tokenów ani danych zdrowotnych do plików projektu. Utrzymuj je wyłącznie w lokalnej konfiguracji środowiska zgodnej z GarminDB.

### Architektura single-user i prywatność

Cały katalog `local/` jest prywatnym stanem jednego użytkownika i jest ignorowany przez Git:

- `local/profile.json` — profil runtime biegacza;
- `local/data_latest.json` — aktualny snapshot danych;
- `local/memory/` — pamięć lokalnego agenta;
- `local/workout-registry.jsonl` — rejestr uploadów treningów.

Publiczne i przeznaczone do śledzenia pozostają `runner_profile.example.json` (neutralny wzór) oraz `training-plans/` (plany). Dotychczasowe prywatne lokalizacje, w tym `HealthData/`, bazy SQLite, pliki FIT/TCX/GPX, snapshoty, `memory/` i `training-plans/_garmin_workouts.jsonl`, nadal są ignorowane na czas migracji. Nie przenoś danych prywatnych automatycznie.

## Profil biegacza

- `runner_profile.example.json` jest neutralnym, publicznym wzorem konfiguracji.
- Docelowy profil single-user należy przechowywać w `local/profile.json`; cały katalog `local/` jest ignorowany przez Git.
- `runner_profile.local.json` pozostaje ignorowaną, starszą lokalizacją na czas migracji.

## Synchronizacja i analiza

```bash
python data_sync.py
python data_sync.py --fresh
python analyze_and_readiness.py
python analyze_and_readiness.py --ai
```

`local/data_latest.json` jest lokalnym, generowanym snapshotem. Zawiera ostatnie aktywności oraz dane zdrowotne, snu, HRV i wagi. Starszy `data_latest.json` przy katalogu projektu także pozostaje ignorowany na czas migracji.

`services/data_extract.py` korzysta z interpretera, który uruchomił aplikację. Szuka lokalnego (ignorowanego) `garmindb_cli.py`, kopii w `GarminDB/` lub polecenia `garmindb_cli` dostępnego w `PATH`. Alternatywnie zainstaluj `garmindb` w aktywnym środowisku.

## Strategia i plany

- `training-plans/long-term/half-marathon-2027.md` to aktualna długoterminowa strategia HM.
- Tygodniowe JSON-y są opcjonalnymi planami wykonawczymi.
- `local/workout-registry.jsonl` jest lokalnym, ignorowanym rejestrem uploadów Garmin, a nie planem. Starszy `training-plans/_garmin_workouts.jsonl` także pozostaje ignorowany na czas migracji.

## Testy

```bash
python -m pytest tests/ -v
```

## Bezpieczeństwo

- `.env` i `.env.*` są ignorowane, z wyjątkiem śledzonego `.env.example`.
- Tokeny, cookies, klucze i certyfikaty są ignorowane.
- Lokalna konfiguracja GarminDB oraz tokeny pozostają poza publicznym repozytorium.
- Przed publikacją uruchom `python scripts/check_privacy.py`; sprawdza on śledzone i staged ścieżki bez wypisywania ich zawartości.
