[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Source,
    [Parameter(Mandatory = $true)]
    [string]$Destination,
    [switch]$IncludeBackups,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
    throw "Katalog źródłowy nie istnieje: $Source"
}
if (-not ((Test-Path -LiteralPath (Join-Path -Path $Source -ChildPath 'DBs') -PathType Container) -or (Test-Path -LiteralPath (Join-Path -Path $Source -ChildPath 'dbs') -PathType Container))) {
    throw "Katalog źródłowy nie wygląda jak HealthData: brakuje DBs lub dbs."
}

$sourcePath = (Resolve-Path -LiteralPath $Source).Path
$destinationPath = [System.IO.Path]::GetFullPath($Destination)
if ($sourcePath.TrimEnd('\') -eq $destinationPath.TrimEnd('\')) {
    throw 'Źródło i cel wskazują tę samą ścieżkę.'
}

$destinationRoot = [System.IO.Path]::GetPathRoot($destinationPath)
$volume = Get-CimInstance -ClassName Win32_LogicalDisk | Where-Object { $_.DeviceID -eq $destinationRoot.TrimEnd('\') }
if ($null -ne $volume -and $volume.FileSystem -eq 'FAT32') {
    Write-Warning 'Nośnik docelowy używa FAT32. Dla danych HealthData zalecany jest exFAT lub NTFS.'
}

Write-Host "Źródło: $sourcePath"
Write-Host "Cel: $destinationPath"
if ($DryRun) { Write-Host 'TRYB PODGLĄDU: pliki nie zostaną skopiowane.' }

$robocopy = Get-Command -Name robocopy.exe -ErrorAction SilentlyContinue
if ($null -ne $robocopy) {
    $arguments = @($sourcePath, $destinationPath, '/E', '/COPY:DAT', '/DCOPY:DAT', '/R:1', '/W:1')
    if (-not $IncludeBackups) { $arguments += @('/XF', '*.bak*', '/XD', '*.bak*') }
    if ($DryRun) { $arguments += '/L' }
    & $robocopy.Source @arguments
    if ($LASTEXITCODE -gt 7) { throw "robocopy zakończył się kodem $LASTEXITCODE" }
} else {
    Write-Warning 'robocopy nie jest dostępny; używam Copy-Item.'
    $items = Get-ChildItem -LiteralPath $sourcePath -Force | Where-Object { $IncludeBackups -or $_.Name -notlike '*.bak*' }
    if (-not $DryRun) {
        New-Item -ItemType Directory -Path $destinationPath -Force | Out-Null
        foreach ($item in $items) { Copy-Item -LiteralPath $item.FullName -Destination $destinationPath -Recurse -Force }
    }
}

if (-not $DryRun) {
    $files = Get-ChildItem -LiteralPath $destinationPath -File -Recurse -Force
    $bytes = ($files | Measure-Object -Property Length -Sum).Sum
    Write-Host ("Wynik: {0:N0} plików, {1:N2} GB" -f $files.Count, ($bytes / 1GB))
}
Write-Host 'Katalog ~/.GarminDb (tokeny i konfiguracja logowania) celowo nie jest eksportowany.'
