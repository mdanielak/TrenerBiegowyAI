# Poziom biegacza nadąża za biegaczem — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Staż z kreatora rośnie z czasem, poziom biegacza ustala się ze stabilnej historii tygodni, a zmiana poziomu jest ogłaszana na Stronie głównej i widoczna (z ręcznym ustawieniem) w Ustawieniach.

**Architecture:** Bez nowego zapisu stanu: `build_runner_profile` liczy surową ocenę poziomu dla każdego z ostatnich 12 poniedziałków z danych w `data_latest.json` i przepuszcza je przez histerezę (awans po 3, spadek po 4 tygodniach). Warstwa web dostaje jeden nowy wstrzykiwany `runner_provider`, z którego korzystają Strona główna i Ustawienia.

**Tech Stack:** Python 3, FastAPI, Jinja2, pytest.

**Spec:** `docs/superpowers/specs/2026-11-15-poziom-biegacza-design.md`

## Global Constraints

- Teksty po polsku, dla osoby nietechnicznej, neutralnie płciowo (czas teraźniejszy „biegasz” jest neutralny; bez form „biegałeś/aś”).
- Progi poziomów bez zmian: 2 biegi/tydz., 45/30 min (`EXPERIENCED_SHORT_RUN_MIN`), 4 biegi + 90 min albo 40 km, staż 6 i 24 mies.
- Awans: 3 oceniane tygodnie z rzędu wskazują wyższy poziom. Spadek: 4 z rzędu niższy. Jeden stopień naraz. Historia: do 12 poniedziałków.
- Tygodnie bez biegania i punkty z krótką historią (< 21 dni od pierwszego biegu) nie są oceniane.
- Powrót po przerwie (`_returning`) → `level = "poczatkujacy"`, ważniejsze niż `level_override`.
- Limity planu nadal z jednego źródła; poziom wpływa na nie dokładnie tak jak dziś.
- Commity po angielsku z linią `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; ścieżki podawane wprost.
- Wydanie `0.8.1`.

## Review Focus

1. Profil bez `running_since` (jak u autora) — staż `None`, poziom z samych danych; histereza działa, nic się nie wysypuje.
2. Mniej niż 3 oceniane tygodnie historii — poziom = pierwsza ocena, bez komunikatu o zmianie.
3. Tydzień ze zmianą poziomu wypada w poniedziałek: komunikat widoczny cały tydzień od tego poniedziałku, w następnym znika.
4. `level_override` z nieznaną wartością (ręcznie edytowany plik) — traktowany jak „automatycznie”.
5. Brak danych z zegarka (`snapshot.data` puste) — Strona główna i Ustawienia działają bez sekcji poziomu.

---

### Task 1: Staż rośnie z kalendarzem

**Files:**
- Modify: `services/wizard.py` (`save`), `api/routers/wizard.py:118` (przekazanie bieżącego profilu)
- Modify: `services/runner_profile.py` (nowa funkcja + użycie w `build_runner_profile`)
- Test: `tests/test_runner_profile.py`, `tests/test_wizard.py`

**Interfaces:**
- Produces: `running_months(profile: dict, on: date) -> int | None` w `services/runner_profile.py` — `RUNNING_SINCE[odp.] + pełne miesiące od running_since_at (albo onboarding_completed_at) do on`, nie mniej niż `RUNNING_SINCE[odp.]`; `None` gdy brak odpowiedzi.
- Produces: `wizard.save(values, *, update_profile, set_availability, set_quality_limit=None, now=None, current_profile=None)` zapisuje `running_since_at` (data ISO `YYYY-MM-DD`).

- [ ] **Step 1: Testy**

```python
def test_years_of_running_grow_from_the_wizard_answer():
    p = _profile(running_since="start", running_since_at="2025-10-01")
    assert running_months(p, date(2026, 11, 4)) == 13
    assert running_months(_profile(running_since="start", onboarding_completed_at="2026-05-04T10:00:00"),
                          date(2026, 11, 4)) == 6
    assert running_months(_profile(running_since="under6"), date(2026, 11, 4)) == 3   # bez daty — jak dziś
    assert running_months(_profile(), date(2026, 11, 4)) is None

def test_a_year_after_starting_a_frequent_runner_is_no_longer_a_beginner():
    runs = _runs(range(3, 85, 2), 50)   # ~3,5 biegu/tydz. przez 12 tygodni
    runner = build_runner_profile(activities=runs, today=TODAY,
                                  profile=_profile(running_since="start", running_since_at="2025-10-01"))
    assert runner["level"] == "regularny"
```

W `tests/test_wizard.py`: `test_saving_the_same_running_since_keeps_its_date` — `current_profile={"running_since": "under6", "running_since_at": "2026-01-10"}` i ta sama odpowiedź → `running_since_at == "2026-01-10"`; inna odpowiedź → data z `now`.

- [ ] **Step 2:** `python -m pytest -q tests/test_runner_profile.py tests/test_wizard.py` → nowe testy FAIL.
- [ ] **Step 3:** Zaimplementować `running_months`, zastąpić nim `RUNNING_SINCE.get(since)` w `build_runner_profile` (na razie dla `today`), dodać `current_profile` w `wizard.save` i przekazać `profile_provider()` z `api/routers/wizard.py` (gdy odczyt się nie uda — `None`).
- [ ] **Step 4:** Te same testy → PASS; `python -m pytest -q` cały zestaw zielony.
- [ ] **Step 5:** Commit `Years of running grow with the calendar` (pliki z listy).

### Task 2: Poziom z historii tygodni

**Files:**
- Modify: `services/runner_profile.py`
- Modify: `docs/superpowers/specs/2026-11-15-poziom-biegacza-design.md` (doprecyzowanie `level_changed`, niżej)
- Test: `tests/test_runner_profile.py`

**Interfaces:**
- Consumes: `running_months` (Task 1).
- Produces: w wyniku `build_runner_profile` nowe klucze:
  `level_auto: str` (poziom z historii, przed ręcznym ustawieniem i powrotem),
  `level_since: str | None` (ISO poniedziałku, od którego obowiązuje `level_auto`),
  `level_changed: "up" | "down" | None` (zmiana nastąpiła w bieżącym tygodniu — w poniedziałek `monday`),
  `level_override: str | None`, `level_reason: str | None`.
  `level` = `"poczatkujacy"` przy powrocie; inaczej `level_override` (gdy w `LEVEL_LABELS`), inaczej `level_auto`.
- Produces: `level_message(runner: dict) -> str | None` — zdanie na Stronę główną (powód + skutek), `None` gdy `level_changed is None` albo ustawienie ręczne.

Algorytm (nie wynika z sygnatury):
```text
_raw_level(runs, profile, monday_k, until) -> str | None   # dzisiejsza reguła na oknie 28 dni przed monday_k;
    None, gdy brak biegów w [monday_k-7, monday_k) albo krótka historia w monday_k
    (dla k=0 najdłuższy bieg jak dziś: 28 dni do `today`)
oceny = [_raw_level(...) dla k = 11..0], pomiń None
brak ocen -> level_auto = dzisiejszy wynik (krótka historia), level_since = None
poziom = pierwsza ocena; since = jej poniedziałek; up = down = 0
dla każdej kolejnej oceny r:  r > poziom -> up += 1, down = 0;  r < poziom -> down += 1, up = 0;  r == poziom -> up = down = 0
    up == 3 -> poziom o stopień w górę, since = ten poniedziałek, zeruj;  down == 4 -> o stopień w dół, analogicznie
level_changed = kierunek ostatniej zmiany, jeśli since == monday
```
Kolejność stopni: `poczatkujacy < regularny < zaawansowany`.

Teksty (`level_reason` / `level_message`), liczby z bieżącego okna, ułamki z przecinkiem:
- powód: `"W ostatnich 4 tygodniach biegasz średnio {runs_per_week} razy w tygodniu, najdłużej {longest_min} min."` (`raz` dla 1)
- awans → regularny: `"{powód} Trener traktuje Cię teraz jak osobę biegającą regularnie."`
- awans → zaawansowany: `"{powód} Trener traktuje Cię teraz jak osobę zaawansowaną."`
- spadek → regularny: `"Ostatnie tygodnie były lżejsze, więc trener planuje teraz jak dla osoby biegającej regularnie."`
- spadek → początkujący: `"Ostatnie tygodnie były lżejsze, więc trener na razie planuje ostrożniej — jak dla osoby, która zaczyna biegać."`

- [ ] **Step 1: Testy** (pomocnik `_weeks(per_week, minutes, weeks)` tworzący biegi w ostatnich `weeks` pełnych tygodniach przed `TODAY`):
  - `test_three_steady_weeks_promote_and_two_do_not` — 8 tyg. po 1 biegu 30 min, potem 3 tyg. po 3×50 → `level == "regularny"`, `level_changed == "up"`, `"biegasz średnio" in level_message(runner)`; to samo z 2 tyg. → `"poczatkujacy"`, `level_changed is None`.
  - `test_one_light_month_does_not_demote_but_four_weeks_do` — 8 tyg. 3×50, potem 3 tyg. 1×30 → `"regularny"`; potem 4 tyg. → `"poczatkujacy"`, `level_changed == "down"`.
  - `test_weeks_without_running_are_not_evidence` — 8 tyg. 3×50, 3 tyg. przerwy, potem 3 biegi w ostatnich 14 dniach → `returning`, `level == "poczatkujacy"`, `level_auto == "regularny"`.
  - `test_manual_level_wins_except_after_a_break` — `level_override="zaawansowany"` → `level == "zaawansowany"`, `level_message(runner) is None`; z powrotem → `"poczatkujacy"`; `level_override="cokolwiek"` → jak automatycznie.
  - `test_a_change_is_announced_only_in_its_own_week` — scenariusz awansu oceniony z `today = TODAY + 7 dni` → `level_changed is None`, `level_since` = poniedziałek tygodnia awansu.
  - Istniejące testy (`test_a_new_watch_trusts…`, `test_a_long_standing_frequent_runner_is_advanced`, `test_coming_back…`) mają przejść bez zmian.
- [ ] **Step 2:** `python -m pytest -q tests/test_runner_profile.py` → nowe FAIL.
- [ ] **Step 3:** Wydzielić dzisiejszą regułę do `_raw_level`, dodać histerezę, nowe klucze i `level_message`. W specyfikacji zamienić „w bieżącym albo poprzednim tygodniu” na „w bieżącym tygodniu (od poniedziałku zmiany)”.
- [ ] **Step 4:** `python -m pytest -q` → cały zestaw zielony.
- [ ] **Step 5:** Przegląd agentem `straznik-limitow` (zmiana w `services/runner_profile.py`); poprawić uwagi, które są trafne.
- [ ] **Step 6:** Commit `Runner level follows a steady history of weeks`.

### Task 3: Strona główna i Ustawienia

**Files:**
- Modify: `api/main.py` (`create_app`: parametr `runner_provider`, przekazanie do dwóch routerów)
- Create: `services/runner_level.py` — `current_runner(*, snapshot_provider, profile_provider, today: date) -> dict | None`
- Modify: `api/routers/dashboard.py`, `templates/today.html`
- Modify: `api/routers/settings.py`, `templates/settings.html`
- Test: `tests/test_today.py`, `tests/test_runner_level_web.py` (nowy)

**Interfaces:**
- Consumes: `build_runner_profile`, `level_message`, `LEVEL_LABELS` (Task 2).
- Produces: `create_app(..., runner_provider: Callable[[], dict | None] | None = None)`; domyślnie `current_runner` z `snapshot_provider`, `profile_provider` i dniem z `now_provider` (lokalnie). `current_runner` zwraca `None` przy braku danych albo dowolnym wyjątku (log `warning` bez treści danych).
- Produces: `POST /settings/level` (pole `level_override`: `""`, `poczatkujacy`, `regularny`, `zaawansowany`, token CSRF) → `update_profile(level_override=...)`, przekierowanie 303 na `/settings#level`; nieprawidłowa wartość → 400 z komunikatem „Wybierz jeden z poziomów.”; `get_settings_router` dostaje `runner_provider` i `update_profile`.

Wygląd:
```text
Strona główna (pod nagłówkiem, przed alertami):  [i] Trener zmienił Twój poziom
                                                     W ostatnich 4 tygodniach biegasz średnio 3,5 razy… 
Ustawienia, karta „Poziom” (id="level"):  Poziom: regularny · od 3 listopada
                                          W ostatnich 4 tygodniach biegasz…
                                          (•) Automatycznie (zalecane)  ( ) początkujący  ( ) regularny  ( ) zaawansowany  [Zapisz]
                                          Przy ręcznym wyborze, po przerwie w bieganiu trener i tak zaczyna ostrożnie.
```
Banner: istniejąca klasa `banner info`; karta: wzorzec `section.card` z `settings.html`; ikona z `/assets/07_ui_icons/` (np. `tile_person.png`).

- [ ] **Step 1: Testy** (`TestClient(create_app(..., runner_provider=lambda: {...}))`, wzorzec z `tests/test_today.py`):
  - `test_home_shows_the_level_change_only_when_there_is_one` — runner z `level_changed="up"` i powodem → tekst na `/`; z `None` → brak „Trener zmienił Twój poziom”; `runner_provider` zwracający `None` → strona 200.
  - `test_settings_show_the_level_and_save_a_manual_choice` — `/settings` zawiera „regularny” i powód; POST z `level_override=zaawansowany` → 303 i `update_profile` wywołane z `level_override="zaawansowany"`; POST `""` → `level_override=""`; POST `xyz` → 400; POST bez CSRF → odrzucony jak inne formularze Ustawień.
  - `test_current_runner_is_none_without_watch_data`.
- [ ] **Step 2:** Uruchomić nowe testy → FAIL.
- [ ] **Step 3:** Zaimplementować `services/runner_level.py`, parametry routerów, trasę, szablony.
- [ ] **Step 4:** `python -m pytest -q` → zielono; `.venv/bin/python -m pyflakes api services ai trainer` → brak uwag.
- [ ] **Step 5:** Agent `korektor-tekstow` dla nowych tekstów; zrzuty skillem `zrzut-testowy` (Strona główna, Ustawienia; jasny i ciemny) — obejrzeć.
- [ ] **Step 6:** Commit `The runner sees the coach's level and can set it`.

### Task 4: Wydanie 0.8.1 (po akceptacji użytkownika)

- [ ] **Step 1:** Pokazać użytkownikowi zrzuty i podsumowanie; po akceptacji `git merge --no-ff feature/runner-level-learning` do `main`.
- [ ] **Step 2:** `python -m pytest -q` na `main` → zielono.
- [ ] **Step 3:** Podbić `pyproject.toml` i `trainer/__init__.py` do `0.8.1`, commit `Release 0.8.1`, tag `v0.8.1`, `git archive --format=zip --prefix=TrenerBiegowyAI/ -o dist/TrenerBiegowyAI-0.8.1.zip v0.8.1`; sprawdzić `unzip -l … | grep -c testowanie` → 0.
- [ ] **Step 4:** `git push origin main v0.8.1`; `gh release create v0.8.1 dist/TrenerBiegowyAI-0.8.1.zip --title "TrenerBiegowyAI 0.8.1" --notes-file <polskie notatki>`; `gh release list --limit 1` → 0.8.1 Latest.
