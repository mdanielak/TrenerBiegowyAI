# Trener Biegowy AI na Linuxie

## Instalacja

Zainstaluj Python 3 oraz narzędzia wymagane do utworzenia środowiska wirtualnego (w wielu dystrybucjach pakiet `python3-venv`), a następnie w katalogu projektu wykonaj:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -c constraints.txt
mkdir -p local
cp runner_profile.example.json local/profile.json
```

Pakiet `garmindb` jest instalowany przez `requirements.txt`. Najłatwiej utworzyć profil poleceniem `python -m trainer setup`; alternatywnie uzupełnij lokalny plik `local/profile.json`. Nie dodawaj go do Git.

## Dane, `.env` i uwierzytelnianie

GarminDB szuka danych w `~/HealthData`, chyba że ustawisz `HEALTH_DATA_DIR`:

```bash
export HEALTH_DATA_DIR="$HOME/HealthData"
```

Katalog musi zawierać podkatalog `DBs` albo `dbs`. Linux rozróżnia wielkość liter, dlatego przy nowej migracji używaj nazwy `DBs`.

Plik `.env` w głównym katalogu projektu jest wczytywany automatycznie i nie jest śledzony przez Git. Wartości ustawione w rzeczywistym środowisku systemowym mają pierwszeństwo przed `.env`. Możesz w nim lokalnie ustawić między innymi `HEALTH_DATA_DIR`, `GARMIN_EMAIL` oraz ustawienia AI. Hasła Garmin nie zapisuj w pliku — podaje się je tylko interaktywnie w `python -m trainer setup`.

Aplikacja używa tokenów w `~/.GarminDb/garmin_tokens.json` i konfiguracji `~/.GarminDb/GarminConnectConfig.json` bez hasła. Gdy tokenu nie da się odnowić, zaloguj ponownie przez `python -m trainer setup`. Stary wpis `GARMIN_PASSWORD` w `.env` jest ignorowany; usuń go ręcznie lub zatwierdź zapis ustawień w kreatorze. Po przejściu z Windows zalecane jest ponowne logowanie na Linuxie; nie kopiuj tokenów ani haseł na pendrive.

## Migracja HealthData z nośnika

Na Windows najpierw użyj `scripts/export_healthdata.ps1`, aby wyeksportować katalog na pendrive. Na Linuxie podłącz nośnik i uruchom z katalogu projektu:

```bash
bash scripts/migrate_healthdata.sh --source "/media/$USER/PENDRIVE/HealthData"
```

Domyślnym celem jest `~/HealthData`; skrypt pomija `*.bak*`. Aby uwzględnić kopie zapasowe, dodaj `--include-backups`. Opcja `--dry-run` pokazuje działanie bez kopiowania. Skrypt nie kopiuje `~/.GarminDb` i po zakończeniu wypisuje właściwy eksport `HEALTH_DATA_DIR`.

Sprawdź konfigurację bez synchronizacji:

```bash
python -m trainer doctor
```

## Rozwiązywanie problemów

| Objaw | Rozwiązanie |
| --- | --- |
| Brak katalogu `DBs`/`dbs` | Wskaż główny katalog HealthData, nie samą bazę; użyj `--source` z właściwą ścieżką. |
| Ostrzeżenie o `dbs` | Na Linuxie zmigruj dane do `DBs`, aby uniknąć problemów z wielkością liter. |
| `doctor` nie widzi danych | Ustaw i wyeksportuj `HEALTH_DATA_DIR`, potem otwórz nową powłokę. |
| Błąd logowania Garmin | Uruchom `python -m trainer setup` i podaj hasło interaktywnie; nie zapisuj go w `.env`. |
| Brak miejsca na dysku | Skrypt pokazuje wolne miejsce przed kopiowaniem; wybierz większy katalog docelowy przez `--target`. |
| Brak modułu Pythona | Aktywuj `.venv` i ponownie uruchom `python -m pip install -r requirements.txt -c constraints.txt`. |

## Opcjonalna automatyzacja codziennej synchronizacji

Przykład dla crona (zastąp ścieżkę ścieżką do klonu):

```cron
0 6 * * * cd /ścieżka/do/TrenerBiegowyAi && /ścieżka/do/TrenerBiegowyAi/.venv/bin/python -m trainer sync >> "$HOME/.local/state/trener-sync.log" 2>&1
```

Alternatywnie utwórz `~/.config/systemd/user/trener-sync.service`:

```ini
[Unit]
Description=Codzienna synchronizacja Trener Biegowy AI

[Service]
Type=oneshot
WorkingDirectory=/ścieżka/do/TrenerBiegowyAi
ExecStart=/ścieżka/do/TrenerBiegowyAi/.venv/bin/python -m trainer sync
```

oraz `~/.config/systemd/user/trener-sync.timer`:

```ini
[Unit]
Description=Timer synchronizacji Trener Biegowy AI

[Timer]
OnCalendar=*-*-* 06:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Włącz timer: `systemctl --user daemon-reload && systemctl --user enable --now trener-sync.timer`.
