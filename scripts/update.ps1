# Aktualizacja Trenera Biegowego AI. Uruchamiana przez update.bat.
# Kopiuje tylko pliki aplikacji z paczki wydania; nigdy nie dotyka danych użytkownika:
# local\, .env, .venv\, planów tygodniowych ani własnej strategii.
param(
    [string]$ZipPath = "",
    [string]$Repo = "mdanielak/TrenerBiegowyAI",
    [int]$Port = 8001
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot

function Get-LocalVersion {
    $text = Get-Content -Raw -Encoding UTF8 (Join-Path $root "pyproject.toml")
    if ($text -match '(?m)^version\s*=\s*"([^"]+)"') { return $Matches[1] }
    return "0.0.0"
}

function Test-AppRunning {
    $listening = netstat -ano | Select-String -Pattern "127\.0\.0\.1:$Port\s.*LISTENING"
    return [bool]$listening
}

function Copy-AppFiles([string]$source) {
    # Dane użytkownika są poza paczką, ale wykluczamy je jeszcze raz na wszelki wypadek.
    $excludeDirs = @("local", ".venv", ".git", "logs")
    $excludeFiles = @(".env")
    robocopy $source $root /E /NFL /NDL /NJH /NJS /NP /XD @excludeDirs /XF @excludeFiles | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Kopiowanie plików nie powiodło się (robocopy $LASTEXITCODE)." }
}

$current = Get-LocalVersion
Write-Host "Zainstalowana wersja: $current"

if (Test-AppRunning) {
    if ($env:TRENER_NONINTERACTIVE -eq "1") { throw "Aplikacja jest uruchomiona. Zamknij ją i uruchom aktualizację ponownie." }
    Write-Host ""
    Write-Host "Aplikacja jest uruchomiona. Zamknij okno ""Trener Biegowy"" (to z napisem uvicorn),"
    Write-Host "a potem naciśnij Enter, żeby kontynuować."
    Read-Host | Out-Null
    if (Test-AppRunning) { throw "Aplikacja nadal działa. Zamknij ją i uruchom update.bat ponownie." }
}

# Klon repozytorium: aktualizacja przez git, bez pobierania paczek.
if (-not $ZipPath -and (Test-Path (Join-Path $root ".git"))) {
    Write-Host "To kopia repozytorium git - pobieram zmiany (git pull)..."
    git -C $root pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw "git pull się nie udał. Masz lokalne zmiany? Sprawdź: git status" }
    exit 0
}

$work = Join-Path $env:TEMP ("trener-update-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force $work | Out-Null
try {
    if ($ZipPath) {
        if (-not (Test-Path $ZipPath)) { throw "Nie ma pliku: $ZipPath" }
        $zip = (Resolve-Path $ZipPath).Path
        Write-Host "Aktualizuję z paczki: $zip"
    } else {
        Write-Host "Sprawdzam najnowsze wydanie na GitHubie..."
        try {
            $release = Invoke-RestMethod -UseBasicParsing -Headers @{ "User-Agent" = "TrenerBiegowyAI-update" } `
                -Uri "https://api.github.com/repos/$Repo/releases/latest"
        } catch {
            throw "Nie udało się sprawdzić wydań (brak internetu albo repozytorium jest prywatne). " +
                  "Pobierz paczkę ZIP ręcznie i przeciągnij ją na update.bat."
        }
        $latest = ($release.tag_name -replace '^v', '')
        Write-Host "Najnowsze wydanie: $latest"
        if ([version]$latest -le [version]$current) {
            Write-Host "Masz najnowszą wersję - nic do zrobienia."
            exit 0
        }
        $asset = $release.assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1
        if (-not $asset) { throw "Wydanie $latest nie ma paczki ZIP." }
        $zip = Join-Path $work $asset.name
        Write-Host "Pobieram $($asset.name)..."
        Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $zip
    }

    $unpacked = Join-Path $work "unpacked"
    Expand-Archive -Path $zip -DestinationPath $unpacked -Force
    # Paczka ma jeden katalog główny (TrenerBiegowyAI\); bierzemy go, gdy jest jedyny.
    $top = @(Get-ChildItem $unpacked)
    $source = if ($top.Count -eq 1 -and $top[0].PSIsContainer) { $top[0].FullName } else { $unpacked }
    if (-not (Test-Path (Join-Path $source "pyproject.toml"))) { throw "To nie jest paczka Trenera Biegowego AI." }

    Write-Host "Kopiuję nowe pliki aplikacji (Twoje dane zostają bez zmian)..."
    Copy-AppFiles $source
    Write-Host "Zaktualizowano do wersji $(Get-LocalVersion)."
} finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}
