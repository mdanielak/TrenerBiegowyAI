# Prompt techniczny — Trener Biegowy AI

Jesteś asystentem technicznym projektu wspierającego lokalną analizę treningów, GarminDB i rekomendacje AI.

## Środowisko

- Uruchamiaj skrypty przez `python <script>.py` w środowisku zgodnym z `requirements.txt`.
- Testy uruchamiaj przez `python -m pytest tests/ -v`.
- `services/data_extract.py` korzysta z `sys.executable`; zależność `garmindb` musi być dostępna w aktywnym środowisku.

## Dane i konfiguracja

- Architektura single-user używa wyłącznie prywatnego, ignorowanego `local/`: `local/profile.json`, `local/data_latest.json`, `local/memory/` i `local/workout-registry.jsonl`.
- Dane Garmin, bazy SQLite, pliki aktywności, snapshoty JSON, logi i cache są lokalne oraz ignorowane przez Git. Starsze `memory/`, `data_latest.json` i `training-plans/_garmin_workouts.jsonl` pozostają ignorowane na czas migracji.
- Nie odczytuj, nie wypisuj i nie publikuj tokenów, credentials ani prywatnych danych zdrowotnych.
- `runner_profile.example.json` jest neutralnym, śledzonym wzorem. Profil runtime przechowuj w `local/profile.json`; `runner_profile.local.json` jest starszą, ignorowaną lokalizacją.
- Lokalny `garmindb_cli.py` jest ignorowaną zależnością. Synchronizacja szuka go w katalogu projektu, w `GarminDB/` albo jako `garmindb_cli` w `PATH`.

## Struktura

```text
config.py                         # Ścieżki i zmienne środowiskowe
ai/context.py                     # Kontekst AI i ładowanie profilu runtime
services/data_extract.py          # Synchronizacja oraz ekstrakcja danych
analyze_and_readiness.py          # Analiza gotowości
training-plans/long-term/half-marathon-2027.md
                                  # Aktualna strategia długoterminowa
local/workout-registry.jsonl
                                  # Lokalny, ignorowany rejestr uploadów
```

## Zasady modyfikacji

1. Nie modyfikuj bezpośrednio baz zarządzanych przez GarminDB.
2. Nie dodawaj credentials, tokenów ani danych osobowych do kodu i dokumentacji.
3. Zachowaj separację: czysty kod w `core.py`, logika w `services/`, konfiguracja w `config.py`.
4. Strategię i zasady treningowe czytaj z odpowiednich plików Markdown; dane konkretnego biegacza nie należą do promptów technicznych.
