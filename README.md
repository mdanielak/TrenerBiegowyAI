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

## Konfiguracja środowiska

Plik `.env` w katalogu głównym projektu jest wczytywany automatycznie i jest ignorowany przez Git. Rzeczywiste zmienne środowiskowe systemu mają pierwszeństwo przed wartościami z `.env`.

| Zmienna | Przeznaczenie |
| --- | --- |
| `HEALTH_DATA_DIR` | Katalog danych GarminDB, domyślnie `~/HealthData`; zawiera `DBs` lub `dbs`. |
| `SNAPSHOT_TTL_SECONDS` | Maksymalny wiek lokalnego snapshotu danych. |
| `GARMIN_EMAIL` | Adres konta Garmin używany przy uwierzytelnianiu. |
| `GARMIN_PASSWORD` | Hasło konta Garmin; potrzebne przy pierwszym logowaniu i do odtworzenia wygasłego tokenu. |
| `AI_BASE_URL` | Adres bazowy opcjonalnego dostawcy AI. |
| `AI_API_KEY` | Klucz API opcjonalnego dostawcy AI. |
| `AI_MODEL` | Nazwa modelu AI do analizy. |
| `AI_DATA_EXPORT_ENABLED` | Zezwolenie na eksport danych do integracji AI. |

### Logowanie do Garmina

Logowanie przechodzi przez jedno miejsce (`trainer/garmin_auth.py`) i działa tak:

1. Jeśli istnieje token `~/.GarminDb/garmin_tokens.json`, używany jest token — hasło nie jest potrzebne.
2. Jeśli tokenu nie ma albo stracił ważność, program loguje się hasłem z `GARMIN_PASSWORD` i **zapisuje nowy token**.
3. Jeśli nie ma ani tokenu, ani hasła, polecenie kończy się czytelnym błędem z instrukcją — nie przechodzi po cichu w tryb bez danych.

Dlatego hasło warto trzymać w pliku `.env`: token wygasa co jakiś czas, a hasło pozwala odtworzyć go automatycznie. Konfiguracja `~/.GarminDb/GarminConnectConfig.json` jest tworzona automatycznie przy pierwszym logowaniu i **nie zawiera hasła**. Nie umieszczaj sekretów w plikach śledzonych przez Git.

## Prywatność

`local/` to prywatny stan runtime. Nie dodawaj do repozytorium danych Garmin, baz SQLite, plików FIT/TCX/GPX, tokenów, danych zdrowotnych ani `local/profile.json`. Ochronnie ignorowane są też legacyjne ścieżki `HealthData/`, `memory/`, główny `data_latest.json` oraz `training-plans/_garmin_workouts.jsonl`.

Przed publikacją uruchom:

```bash
python -m trainer privacy-check
python -m pytest
```
