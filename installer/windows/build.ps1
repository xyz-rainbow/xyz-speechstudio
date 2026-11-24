# XYZ-PRODUCTIONS - Speech Studio installer compiler
$ErrorActionPreference = "Stop"

Write-Host "==============================================================================" -ForegroundColor Magenta
Write-Host "   XYZ-PRODUCTIONS - SPEECH STUDIO INSTALLER" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Magenta
Write-Host ""

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$payload = Join-Path $PSScriptRoot "app_payload"
$exe = Join-Path $repo "src-tauri\target\release\speech-studio.exe"
$icon = Join-Path $repo "src-tauri\icons\icon.ico"

if (-not (Test-Path -LiteralPath $exe)) {
    Write-Host "[ERROR] No esta el ejecutable: $exe" -ForegroundColor Red
    Write-Host "Compila antes con: npx tauri build" -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path -LiteralPath $icon)) {
    Write-Host "[ERROR] No esta el icono: $icon" -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Preparando app_payload" -ForegroundColor Cyan
Get-ChildItem -LiteralPath $payload -Force | Where-Object { $_.Name -ne ".gitkeep" } | Remove-Item -Recurse -Force
Copy-Item -LiteralPath $exe -Destination (Join-Path $payload "speech-studio.exe")
Copy-Item -LiteralPath $icon -Destination (Join-Path $payload "speech-studio.ico")
Copy-Item -LiteralPath (Join-Path $repo "backend") -Destination (Join-Path $payload "backend") -Recurse
Get-ChildItem -LiteralPath (Join-Path $payload "backend") -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $payload "scripts") | Out-Null
Copy-Item -LiteralPath (Join-Path $repo "scripts\notify.ps1") -Destination (Join-Path $payload "scripts\notify.ps1")
if (Test-Path -LiteralPath (Join-Path $repo "scripts\speechstudio.cmd")) {
    Copy-Item -LiteralPath (Join-Path $repo "scripts\speechstudio.cmd") -Destination (Join-Path $payload "scripts\speechstudio.cmd")
}
$stagedInstaller = Join-Path $payload "installer"
New-Item -ItemType Directory -Force -Path $stagedInstaller | Out-Null
Copy-Item -LiteralPath (Join-Path $repo "installer\setup-env.ps1") -Destination $stagedInstaller
Get-ChildItem -LiteralPath (Join-Path $repo "installer") -Filter "requirements-*.txt" | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $stagedInstaller
}

$isccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$isccPath = $null
foreach ($path in $isccCandidates) {
    if (Test-Path -LiteralPath $path) {
        $isccPath = $path
        break
    }
}
if (-not $isccPath) {
    $cmd = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($cmd) { $isccPath = $cmd.Source }
}
if (-not $isccPath) {
    Write-Host "[ERROR] Inno Setup 6 (ISCC.exe) no fue encontrado." -ForegroundColor Red
    Write-Host "Descargalo desde: https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
    exit 1
}

Write-Host "[INFO] Compilador: $isccPath" -ForegroundColor Green
& $isccPath (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] La compilacion fallo (codigo $LASTEXITCODE)." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "[EXITO] Instalador compilado." -ForegroundColor Green
