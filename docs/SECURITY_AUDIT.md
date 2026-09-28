# Security Audit — Trener Biegowy AI

**Data:** 2026-09-28
**Zakres:** bieżący kod, konfiguracja i zasady publikacji.

## Stan po przygotowaniu

- Dane Garmin, snapshoty danych, bazy SQLite, FIT/TCX/GPX, logi, cache i katalog `memory/` są wykluczone przez projektowy `.gitignore`.
- `.env` i jego warianty są ignorowane, z zachowaniem śledzonego `.env.example`.
- Tokeny, cookies, klucze i certyfikaty są ignorowane.
- `GarminDb/` i `.GarminDb/` są ignorowane, ponieważ mogą zawierać lokalną konfigurację i tokeny.
- `runner_profile.local.json` jest ignorowany; `runner_profile.example.json` jest neutralnym wzorem publicznym.
- Rejestr `training-plans/_garmin_workouts.jsonl` jest lokalny i ignorowany.
- Runtime nie zawiera hardcoded ścieżki do interpretera użytkownika; używa `sys.executable`.

## Zasady operacyjne

1. Nie umieszczaj credentials, tokenów ani danych zdrowotnych w kodzie, dokumentacji lub planach publicznych.
2. Utrzymuj dane dostępowe w lokalnym, bezpiecznym mechanizmie środowiska.
3. Przed publikacją sprawdź zawartość zmian pod kątem danych osobowych i lokalnych ścieżek.
4. Nie modyfikuj bezpośrednio baz zarządzanych przez GarminDB.

## Ograniczenia

GarminDB może wymagać lokalnej konfiguracji i tokenów. Są to dane wrażliwe, które muszą pozostać poza repozytorium.
