# Security Audit — Trener Biegowy AI

**Data:** 2026-09-28
**Zakres:** konfiguracja lokalna, CLI i zasady publikacji.

## Stan ochrony danych

- Prywatny stan single-user jest przechowywany w ignorowanym `local/`: `profile.json`, `data_latest.json`, `memory/` i `workout-registry.jsonl`.
- Dane Garmin, bazy SQLite, FIT/TCX/GPX, snapshoty, logi i cache są wykluczane przez `.gitignore`.
- `.env` i warianty są ignorowane; śledzony pozostaje wyłącznie niesekretny `.env.example`.
- Tokeny, cookies, klucze i certyfikaty są ignorowane. Zmienne AI (`AI_API_KEY` w szczególności) ustawiaj wyłącznie lokalnie.
- `GarminDb/` i `.GarminDb/` są ignorowane, ponieważ mogą zawierać konfigurację i tokeny.
- Legacy prywatne ścieżki (`HealthData/`, `memory/`, główny `data_latest.json`, `runner_profile.local.json` i `training-plans/_garmin_workouts.jsonl`) nadal są ochronnie ignorowane.
- `python -m trainer privacy-check` sprawdza śledzone i staged ścieżki bez wypisywania ich zawartości.

## Zasady operacyjne

1. Nie umieszczaj credentials, tokenów ani danych zdrowotnych w kodzie, dokumentacji lub planach publicznych.
2. Przed publikacją uruchom `python -m trainer privacy-check` i sprawdź zmiany pod kątem danych osobowych.
3. Nie modyfikuj bezpośrednio baz zarządzanych przez GarminDB.
4. `python -m trainer workouts create ...` i `python -m trainer workouts usage --delete` mogą wykonywać operacje na Garminie; używaj ich świadomie.

## Ograniczenia

Audyt opisuje konfigurację i mechanizmy repozytorium. Nie stanowi potwierdzenia testów z rzeczywistym API Garmin ani zewnętrzną usługą AI.
