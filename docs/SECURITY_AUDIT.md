# Security Audit — Trener Biegowy AI

**Data:** 2026-09-28
**Zakres:** bieżący kod, konfiguracja i zasady publikacji.

## Stan po przygotowaniu

- Architektura single-user przechowuje prywatny stan wyłącznie w ignorowanym `local/`: `profile.json`, `data_latest.json`, `memory/` i `workout-registry.jsonl`. Katalog `local/` jest wykluczony w całości.
- Dane Garmin, snapshoty danych, bazy SQLite, FIT/TCX/GPX, logi i cache są wykluczone przez projektowy `.gitignore`.
- `.env` i jego warianty są ignorowane, z zachowaniem śledzonego `.env.example`.
- Tokeny, cookies, klucze i certyfikaty są ignorowane.
- `GarminDb/` i `.GarminDb/` są ignorowane, ponieważ mogą zawierać lokalną konfigurację i tokeny.
- `runner_profile.example.json` jest neutralnym wzorem publicznym. `runner_profile.local.json` pozostaje ignorowaną starszą lokalizacją na czas migracji.
- Starsze lokalizacje prywatne (`data_latest.json`, `memory/`, `HealthData/` i `training-plans/_garmin_workouts.jsonl`) pozostają ignorowane na czas migracji.
- Runtime nie zawiera hardcoded ścieżki do interpretera użytkownika; używa `sys.executable`.
- `python scripts/check_privacy.py` sprawdza nazwy plików śledzonych i staged; wynik nie zawiera treści plików.

## Zasady operacyjne

1. Nie umieszczaj credentials, tokenów ani danych zdrowotnych w kodzie, dokumentacji lub planach publicznych.
2. Utrzymuj dane dostępowe w lokalnym, bezpiecznym mechanizmie środowiska.
3. Przed publikacją uruchom `python scripts/check_privacy.py` oraz sprawdź zawartość zmian pod kątem danych osobowych.
4. Nie modyfikuj bezpośrednio baz zarządzanych przez GarminDB.

## Ograniczenia

GarminDB może wymagać lokalnej konfiguracji i tokenów. Są to dane wrażliwe, które muszą pozostać poza repozytorium.
