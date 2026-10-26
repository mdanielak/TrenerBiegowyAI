# Trener Biegowy AI

Lokalne narzędzie do synchronizacji danych GarminDB, analizy gotowości i zarządzania treningami Garmin. Jedynym wspieranym entry pointem jest `python -m trainer` — na Linuxie, macOS i Windows.

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

## Lokalny dashboard

Po przygotowaniu środowiska `.venv` i danych uruchom dashboard:

- **Linux / macOS:** `./start.sh`
- **Windows:** kliknij dwukrotnie `start.bat` lub uruchom `.\start.bat` w PowerShell.

Skrypty korzystają z `.venv` właściwego dla danego systemu, nie wymagają jego aktywowania i nie wykonują synchronizacji. Zatrzymanie serwera: `Ctrl+C`.

Otwórz w przeglądarce [http://127.0.0.1:8001](http://127.0.0.1:8001). Widok tygodnia jest dostępny pod adresem [http://127.0.0.1:8001/week](http://127.0.0.1:8001/week). Serwer jest dostępny tylko z tego komputera. Dashboard wyłącznie pokazuje lokalne dane; ich odświeżanie wykonujesz w terminalu poleceniem `python -m trainer sync`.

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

`local/` to prywatny stan runtime. Nie dodawaj do repozytorium danych Garmin, baz SQLite, plików FIT/TCX/GPX, tokenów, danych zdrowotnych ani `local/profile.json`. Ochronnie ignorowane są też legacyjne ścieżki `HealthData/`, `memory/`, główny `data_latest.json` oraz `training-plans/_garmin_workouts.jsonl`.

Przed publikacją uruchom:

```bash
python -m trainer privacy-check
python -m pytest
```
