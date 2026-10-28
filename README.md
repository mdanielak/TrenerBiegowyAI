# Trener Biegowy AI

Lokalne narzędzie do synchronizacji danych GarminDB, analizy gotowości i zarządzania treningami Garmin. Jedynym wspieranym entry pointem jest `python -m trainer` — na Linuxie, macOS i Windows.

## Uruchom dashboard (frontend)

Dashboard to lokalny serwer FastAPI z szablonami Jinja; dane bierze wyłącznie z tego komputera.

**Windows** — kliknij dwukrotnie `start.bat` (albo w PowerShell `.\start.bat`). Skrypt sam znajdzie interpreter: `.venv\Scripts\python.exe`, a gdy go nie ma, `python` albo `py` z zainstalowanym `uvicorn`.

**Linux / macOS** — `./start.sh` (wymaga `.venv`, patrz Instalacja).

**Ręcznie, w dowolnym systemie:**

```bash
python -m uvicorn api.main:app --host 127.0.0.1 --port 8001
```

Po uruchomieniu otwórz **http://127.0.0.1:8001**:

| Adres | Widok |
| --- | --- |
| `/` | strona główna: gotowość, sygnały, trening na dziś, rekomendacja AI |
| `/plan` | plan tygodniowy: cel, obciążenie tygodnia, dzień po dniu, uwagi |
| `/week` | kalendarz treningów z rejestru Garmina |
| `/stats` | statystyki 4/8/12 tygodni: kilometry na tle fazy strategii, plan a wykonanie, trendy sygnałów |
| `/analysis` | rozkład pomiarów, z których liczona jest gotowość |
| `/journal` | dziennik samopoczucia: samopoczucie, RPE, ból i notatka dzień po dniu |
| `/goal` | cel długoterminowy: odliczanie, fazy strategii i kryteria gotowości |
| `/settings` | profil biegacza, tętno i forma, strefy tętna, cele oraz integracje (API AI) |

Serwer działa tylko na `127.0.0.1` — nie ma go w sieci. Zatrzymanie: `Ctrl+C` w oknie terminala.

Dashboard wymaga środowiska z `requirements.txt` oraz danych w katalogu `local/` — jeśli strona zgłasza brak profilu albo snapshotu, najpierw `python -m trainer setup` i `python -m trainer sync`.

## Instalacja

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p local
cp runner_profile.example.json local/profile.json
```

**Windows PowerShell**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
New-Item -ItemType Directory -Force local
Copy-Item runner_profile.example.json local/profile.json
```

Następnie uruchom `python -m trainer setup`. Kreator pobiera dane fizjologiczne i strefy tętna wprost z Garmin Connect, więc wystarczy je zatwierdzić — ręczne wpisywanie jest tylko wariantem awaryjnym, gdy połączenie zawiedzie. Plik `local/profile.json` można też uzupełnić samodzielnie. Pełne instrukcje: [Linux](docs/linux_setup.md) oraz [Windows](docs/windows_description.md).

## Codzienna praca

```bash
python -m trainer setup
python -m trainer sync
python -m trainer today
python -m trainer plan
python -m trainer plan --show
python -m trainer analyze
python -m trainer analyze --ai
python -m trainer zones --sync
python -m trainer profile
python -m trainer profile --sync
python -m trainer workouts new
python -m trainer doctor
python -m trainer privacy-check
```

`python -m trainer profile` pokazuje zapisany profil biegacza, a `profile --sync` odświeża z Garmin Connect wiek, wagę, wzrost, tętno maksymalne i spoczynkowe, próg mleczanowy, VO2max oraz strefy tętna — dzięki temu nie trzeba wpisywać ich ręcznie. Dni treningowe pozostają w preferencjach lokalnych i mają pierwszeństwo nad ustawieniami z Garmina. Jeśli profil zawiera wartości zapisane jako zakres (np. `75-76`), komenda to zgłosi i zaproponuje synchronizację.

Przy pierwszym pobraniu lub przebudowie danych użyj `python -m trainer sync --fresh`. Dostępne są też podkomendy `sync`, `analyze`, `workouts`, `privacy-check` i `doctor`; sprawdź `python -m trainer --help` oraz pomoc wybranej podkomendy. Wynik synchronizacji może być częściowy — przed decyzją treningową sprawdź aktualność i kompletność snapshotu.

### Plan tygodniowy

`python -m trainer plan` układa plan na bieżący tydzień (pon–niedz): AI dostaje profil, dostępność dni, przerwy, ostatnie biegi, gotowość, trendy z 12 tygodni i podsumowanie dziennika z 7 dni, a twarde reguły — dni wolne, okna minut, limit treningów jakościowych — egzekwuje lokalny kod. Plan zapisuje się w `training-plans/{YYYY-MM}/{d}-{d}.json` obok bliźniaczego pliku CSV.

- `python -m trainer plan --show` wypisuje zapisany plan bez wywołania AI.
- `python -m trainer plan --push` wysyła zapisany plan na zegarek (wymaga działającego logowania do Garmina).
- `python -m trainer plan --week 2026-10-26` wybiera tydzień zawierający podaną datę.

Generowanie planu wymaga włączonej zgody na eksport danych do AI (`AI_DATA_EXPORT_ENABLED=true` wraz z kluczem API). Ten sam plan można ułożyć i wysłać na zegarek z dashboardu.

#### Gdy plan lub treningi już istnieją

Ani „Ułóż plan”, ani „Wyślij do Garmina” niczego nie nadpisują bez pytania. Jeśli na tydzień jest już plan albo na zegarku są już treningi na te same dni, pojawia się lista kolidujących dni i trzy decyzje:

| Akcja | Nadpisz | Dodaj obok | Anuluj |
| --- | --- | --- | --- |
| Ułóż plan | obecne pliki tygodnia trafiają do `training-plans/{YYYY-MM}/archive/`, nowy plan obowiązuje | nowy plan zapisuje się jako druga wersja w `variants/`; na stronie planu porównasz ją dzień po dniu i możesz jej użyć albo odłożyć do archiwum | nic się nie zmienia |
| Wyślij do Garmina | kolidujące treningi są usuwane z Garmina (zostają w rejestrze i da się je odtworzyć), potem wysyłka | nowe treningi trafiają obok istniejących | nic nie jest wysyłane |

Treningi na zegarku rozpoznawane są z lokalnego rejestru, więc trening dodany ręcznie w Garmin Connect nie zostanie wykryty. Pliki nigdy nie są kasowane — archiwum i wersje to zwykłe pliki JSON obok planu.

W terminalu `python -m trainer plan` i `plan --push` zadają to samo pytanie. W skryptach użyj `--on-conflict overwrite|add|cancel`; bez terminala interaktywnego i bez flagi polecenie anuluje i nic nie zmienia.

## Lokalny dashboard

Dashboard uruchamiasz skryptem `start.bat` (Windows) albo `./start.sh` (Linux / macOS) — pełna instrukcja jest na górze tego pliku. Skrypty korzystają z `.venv` właściwego dla danego systemu, nie wymagają jego aktywowania i nie wykonują synchronizacji.

Dashboard wyłącznie pokazuje lokalne dane; ich odświeżanie wykonujesz w terminalu poleceniem `python -m trainer sync`.

### Zakres danych

Snapshot (`local/data_latest.json`) zawiera wszystkie aktywności z ostatnich 120 dni oraz 90 dni tętna spoczynkowego, stresu, snu i HRV. Okna liczone są od najnowszego rekordu w bazie GarminDB, więc starsza baza daje ten sam zakres. Strona statystyk i strona celu korzystają tylko z tego snapshotu; do AI trafiają wyłącznie agregaty (średnie z 7 dni wobec 12 tygodni, kilometry z 4 tygodni) oraz 7 ostatnich biegów.

### Dziennik i cel

Wpisy dziennika zapisują się w `local/journal.jsonl`. Plik tylko przyrasta, a obowiązuje ostatni wpis z danego dnia. Przy włączonej zgodzie na eksport danych podsumowanie 7 dni — samopoczucie, średnie RPE, zgłoszony ból i notatki ucięte do 120 znaków — trafia do układania planu i rekomendacji dziennej. Ból z dziennika ma dla AI pierwszeństwo przed metrykami zegarka.

Strona celu czyta fazy i kryteria z tabeli „Periodyzacja” oraz sekcji „Kryteria gotowości” w `training-plans/long-term/half-marathon-2027.md`, a datę i czas docelowy z profilu. Kryteria są przybliżone: snapshot nie ma splitów, więc „test 10 km” to najszybszy bieg o długości około 10 km.

Na stronie planu przycisk „Ułóż plan” uruchamia układanie tygodnia w tle, a „Wyślij do Garmina” tworzy treningi na zegarku. Nawigacja „Poprzedni tydzień / Ten tydzień / Następny tydzień” przełącza wyświetlany tydzień; na stronie widać gotowość zmierzoną przez zegarek w danym dniu, zaplanowany czas w tygodniu i obciążenie poprzedniego tygodnia z zegarka. Na stronie głównej przycisk „Zapytaj AI, co dziś zrobić” zapisuje rekomendację dzienną na tym komputerze.

## Konfiguracja środowiska

Plik `.env` w katalogu głównym projektu jest wczytywany automatycznie i jest ignorowany przez Git. Rzeczywiste zmienne środowiskowe systemu mają pierwszeństwo przed wartościami z `.env`.

| Zmienna | Przeznaczenie |
| --- | --- |
| `HEALTH_DATA_DIR` | Katalog danych GarminDB, domyślnie `~/HealthData`; zawiera `DBs` lub `dbs`. |
| `SNAPSHOT_TTL_SECONDS` | Maksymalny wiek lokalnego snapshotu danych. |
| `GARMIN_EMAIL` | Adres konta Garmin używany przy uwierzytelnianiu. |
| `AI_BASE_URL` | Adres bazowy opcjonalnego dostawcy AI. |
| `AI_API_KEY` | Klucz API opcjonalnego dostawcy AI. |
| `AI_MODEL` | Nazwa modelu AI do analizy. |
| `AI_DATA_EXPORT_ENABLED` | Zezwolenie na eksport danych do integracji AI. |

### Ustawienia API AI

W dashboardzie otwórz **Ustawienia → API AI** (`/settings/ai`). Na głównej stronie ustawień jest tylko odnośnik do tej podstrony. Formularz zapisuje adres API zgodnego z OpenAI, nazwę modelu, klucz oraz zgodę na eksport danych do pliku `.env`. Puste pole klucza zachowuje dotychczasowy wpis; osobna opcja pozwala go usunąć. Zapis nie wykonuje żadnego połączenia z AI.

**Testuj połączenie** sprawdza bieżące pola formularza przez pojedyncze zapytanie Chat Completions do wybranego modelu, bez zapisywania konfiguracji i bez restartu. Wysyła tylko „Connection test. Reply only OK.” — bez profilu i danych treningowych, również przy wyłączonej zgodzie na eksport. Dostawca może naliczyć opłatę. Test nie ponawia żądania i nie podąża za przekierowaniami; timeout wynosi 20 s. Puste pole klucza korzysta z zapisanego klucza również po zmianie ścieżki API u tego samego dostawcy (ta sama domena, protokół i port, np. `/v1` → `/v2`). Zapis zachowuje ten klucz. Zmiana serwera wymaga podania nowego klucza lub jawnego usunięcia poprzedniego — podobny prefiks domeny nie wystarcza. Pełna ścieżka pliku `.env` jest widoczna na podstronie API AI. Klucz wpisany na potrzeby testu nie jest odsyłany do przeglądarki — przed jego zapisem trzeba wpisać go ponownie.

Możesz też edytować `.env` ręcznie (wzór: `.env.example`):

```dotenv
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o
AI_API_KEY=
AI_DATA_EXPORT_ENABLED=false
```

Po zmianie ustawień **zrestartuj serwer** (`Ctrl+C`, potem `./start.sh` lub `start.bat`). Klucz jest zapisany jawnie na dysku, ale nie jest wyświetlany w formularzu. Nie udostępniaj pliku `.env`. Eksport danych do AI jest domyślnie wyłączony; włączaj go świadomie dla zaufanego adresu API.

### Logowanie do Garmina

Logowanie przechodzi przez jedno miejsce (`trainer/garmin_auth.py`) i działa tak:

1. Aplikacja korzysta z tokenów `~/.GarminDb/garmin_tokens.json`. Biblioteka odnawia token dostępu za pomocą refresh tokenu, bez hasła.
2. Jeśli tokenów brakuje lub nie da się ich odnowić, uruchom interaktywnie `python -m trainer setup` (Linux bez aktywacji środowiska: `./.venv/bin/python -m trainer setup`). Kreator pyta o hasło dopiero, gdy jest potrzebne, i obsługuje MFA.
3. Hasło służy wyłącznie do logowania. **Nie jest zapisywane ani pobierane z `.env` lub zmiennej `GARMIN_PASSWORD`.** Polecenia nieinteraktywne bez działającego tokenu kończą się komunikatem o konieczności ponownego logowania.

Usuń stary wpis `GARMIN_PASSWORD=...` z `.env` i ewentualnej konfiguracji środowiska, następnie zrestartuj aplikację. Kreator przy zatwierdzonym zapisie `.env` usuwa też stare wpisy hasła, zachowując inne ustawienia. Konfiguracja `~/.GarminDb/GarminConnectConfig.json` jest tworzona bez hasła. Jeśli była wcześniej konfigurowana osobno, usuń również zapisane w niej poświadczenia hasłowe.

Tokeny również są sekretami: zapewniają dostęp do konta. Biblioteka zapisuje je na Linuxie z uprawnieniami `600`, w katalogu `700`. Nie umieszczaj haseł ani tokenów w Git i nie udostępniaj ich.

## Prywatność

`local/` to prywatny stan runtime. Nie dodawaj do repozytorium danych Garmin, baz SQLite, plików FIT/TCX/GPX, tokenów, danych zdrowotnych ani `local/profile.json`. Ochronnie ignorowane są też legacyjne ścieżki `HealthData/`, `memory/`, główny `data_latest.json` oraz `training-plans/_garmin_workouts.jsonl`. Wygenerowane plany tygodniowe (`training-plans/{YYYY-MM}/`) zawierają dane biegacza, więc również są ignorowane — śledzona pozostaje tylko strategia długoterminowa w `training-plans/long-term/`.

Przed publikacją uruchom:

```bash
python -m trainer privacy-check
python -m pytest
```
