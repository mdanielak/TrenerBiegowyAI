# Prompt techniczny — Trener Biegowy AI

Jesteś asystentem technicznym lokalnego projektu analizy treningów. Głównym interfejsem jest CLI `python -m trainer` (wersja 0.2.0); GarminDB jest backendem danych, a API uruchamia się niezależnie przez `uvicorn api.main:app --reload`.

## Uruchamianie

- Pomoc i wersja: `python -m trainer --help`, `python -m trainer --version`.
- Dane i analiza: `python -m trainer sync [--fresh]`, `python -m trainer analyze [--ai]`.
- Treningi Garmin: `python -m trainer workouts usage [--delete]` oraz `python -m trainer workouts create <easy|tempo|intervals|long|strides> ...`.
- Prywatność i testy: `python -m trainer privacy-check`, `python -m pytest tests/ -v`.
- Nie zakładaj, że przetestowano rzeczywiste API Garmin lub usługę AI; ich użycie wymaga lokalnej konfiguracji i danych dostępowych.

## Dane i odpowiedzialności

- `trainer/config.py` definiuje ścieżki runtime i obsługiwane zmienne środowiskowe: `HEALTH_DATA_DIR`, `SNAPSHOT_TTL_SECONDS`, `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`, `AI_DATA_EXPORT_ENABLED`.
- Prywatny stan single-user znajduje się w ignorowanym `local/`: `profile.json`, `data_latest.json`, `memory/` i `workout-registry.jsonl`.
- `runner_profile.example.json` jest neutralnym wzorem; przed uruchomieniem skopiuj go do `local/profile.json` i uzupełnij lokalnie.
- GarminDB zarządza lokalnymi danymi Garmin. Nie modyfikuj jego baz bezpośrednio. `create` i `usage --delete` mogą zmieniać treningi na Garminie.
- Nie odczytuj, nie wypisuj ani nie publikuj tokenów, credentials i prywatnych danych zdrowotnych.
- Legacy prywatne ścieżki (`HealthData/`, `memory/`, główny `data_latest.json` oraz `training-plans/_garmin_workouts.jsonl`) pozostają ochronnie ignorowane.

## Zasady zmian

1. Preferuj CLI zamiast wywoływania starszych skryptów; stare skrypty są wyłącznie kompatybilnością wsteczną.
2. Zachowaj separację odpowiedzialności: konfiguracja w `trainer/config.py`, ekstrakcja danych w `services/`, logika CLI w `trainer/`, API w `api/`.
3. Dane konkretnego biegacza nie należą do kodu, dokumentacji ani promptów publicznych.
