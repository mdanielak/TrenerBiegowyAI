# TrenerBiegowyAI — wskazówki dla asystenta AI

Lokalna aplikacja dla biegaczy: dane z Garmina (GarminDB/garminconnect), ocena gotowości, plan tygodnia
układany przez AI (DeepSeek, Gemini, OpenAI — dowolny dostawca zgodny z API OpenAI), wysyłka treningów na zegarek.
Jedna osoba na komputer; serwer nasłuchuje tylko na 127.0.0.1.

## Komunikacja
- Odpowiadaj po polsku, z poprawnymi polskimi znakami. Identyfikatory kodu zostają w oryginale.
- O innych osobach (np. „osoba testująca”) pisz neutralnie płciowo, nie zgaduj płci z imienia.
- Teksty w aplikacji są dla osoby nietechnicznej: bez żargonu i angielskich kodów z danych.

## Prywatność (bezwzględnie)
- Nigdy nie czytaj pliku `.env` (hook to blokuje) ani nie wypisuj kluczy API.
- Nie commituj: `local/` (profil, dziennik, dane zdrowotne), `training-plans/` poza `long-term/przyklad-strategii.md`,
  zrzutów ekranu z danymi, `.impeccable/`, `.claude/`. Hook `.githooks/pre-commit` uruchamia `scripts/check_privacy.py`
  (włączenie: `git config core.hooksPath .githooks`).
- Commituj tylko własne pliki, podając ścieżki wprost (użytkownik pracuje równolegle).
- Hasło do Garmina nie jest nigdzie zapisywane; nie nadpisuj prawdziwego tokenu w `~/.GarminDb`.
- Aplikacja nie pokazuje surowych komunikatów błędów dostawców AI — tylko własne, zmapowane.

## Sposób pracy
- Zmiany UI i większe funkcje: na osobnej gałęzi `feature/...`; do `main` dopiero po akceptacji użytkownika.
- Push tylko przy zielonych testach. Bez `git push --force` i `git reset --hard` (hook blokuje); bezpieczne zamienniki.
- Komunikaty commitów po angielsku, z linią `Co-Authored-By` podaną w instrukcjach sesji.

## Polecenia
- Testy: `python -m pytest -q` (ok. 960 testów, ~1 min). Lint: `.venv/Scripts/python.exe -m pyflakes <pliki>`.
- Aplikacja: `start.bat` (http://127.0.0.1:8001). Pierwsza instalacja: `install.bat`; aktualizacja: `update.bat`.
- **Testowanie na zmyślonych danych:** `testowanie.bat` (http://127.0.0.1:8002) — kopia kodu w `%TEMP%\trener-testowanie`,
  zegar przesunięty, Garmin i AI udawane, prawdziwe dane nietknięte. Flagi: `--dzien czwartek`,
  `--biegacz poczatkujacy|regularny|zaawansowany`, `--verbose` (HTTP, Garmin, pełne prompty w `logs/`),
  `--zachowaj` (dane z poprzedniego testu zostają). Nie trafia do paczki wydania (`export-ignore`).
- Zrzuty stron: Chrome headless na działającym testowaniu (`--screenshot`, `--force-prefers-color-scheme=light`).

## Mapa
- `api/` — FastAPI: `main.py` (`create_app` z wstrzykiwanymi dostawcami), `routers/` (strony i akcje), `views/` (dane dla szablonów).
- `templates/`, `static/` — Jinja i CSS (tokeny kolorów w `static/css/styles.css`, zasady w `DESIGN.md`), `static/js/interface.js`.
- `services/` — logika: `today.py`, `plan.py` (normalizacja planu AI i **bezpieczniki**), `runner_profile.py`
  (profil biegacza, decyzja tygodnia, limity), `actions.py` (zadania w tle: synchronizacja, plan, wysyłka, usuwanie),
  `jobs.py` (stan zadań w `local/jobs`), `wizard.py` (kreator celu), `strategy.py` (opcjonalna strategia z `training-plans/long-term/strategia.md`).
- `ai/` — wywołania AI: `plan_generation.py` (plan tygodnia, schemat JSON i twarde reguły), `recommendation.py`
  (rekomendacja dnia), `workout_review.py` (komentarz do treningu), `context.py` (dane do promptu).
- `ai/prompts/` — prompty trenera: `trener.md`, `jezyk/` (forma męska/żeńska/bez form), `core/01–05`, `poziom/`, `cel/`,
  `zdrowie/`, `tryby/`, `przyklady.md`. Ładowarka: `ai/prompts/__init__.py::coach_prompt(runner, mode=...)`.
  Prywatne dodatki autora: `local/moje-zasady-trenera.md`. Ręczna ocena odpowiedzi modelu: `docs/ewaluacja-ai/`.
- `trainer/` — CLI (`python -m trainer`), konfiguracja (`config.py`), Garmin (`garmin_auth.py`, `garmin_workouts.py`).

## Zasady, które łatwo złamać
- Limity planu muszą być te same w prompcie i w kodzie: model dostaje je w linii „LIMITY APLIKACJI”
  (`services/runner_profile.py::profile_lines`), a egzekwuje `services/plan.py::normalize_plan`.
- Okno dostępności dnia tylko skraca trening, nigdy go nie wydłuża.
- Nowa wersja: podbić `pyproject.toml` i `trainer/__init__.py`, commit „Release X.Y.Z”, tag `vX.Y.Z`,
  `git archive --format=zip --prefix=TrenerBiegowyAI/ -o dist/TrenerBiegowyAI-X.Y.Z.zip vX.Y.Z`,
  `gh release create` z polskimi notatkami (zip jako asset — z niego korzysta `update.bat`).
- Aktualne prompty są wyłącznie w `ai/prompts/`; `docs/TRAINING_RULES.md` to opis dla ludzi i do promptu nie trafia.
