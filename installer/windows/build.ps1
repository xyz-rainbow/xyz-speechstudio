# XYZ-PRODUCTIONS - Speech Studio installer compiler
$ErrorActionPreference = "Stop"

Write-Host "==============================================================================" -ForegroundColor Magenta
Write-Host "   XYZ-PRODUCTIONS - SPEECH STUDIO INSTALLER" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Magenta
Write-Host ""

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$tauriConf = Get-Content -LiteralPath (Join-Path $repo "src-tauri\tauri.conf.json") -Raw | ConvertFrom-Json
$appVersion = [string]$tauriConf.version
if (-not $appVersion) {
    Write-Host "[ERROR] No se pudo leer version desde src-tauri\tauri.conf.json" -ForegroundColor Red
    exit 1
}
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
# CrispASR: GPU (cuda/) + CPU (cpu/) follow the in-app device selector.
$crispasrSrc = Join-Path $repo "runtime\bin"
$crispasrDst = Join-Path $payload "runtime\bin"
New-Item -ItemType Directory -Force -Path $crispasrDst | Out-Null
if (Test-Path -LiteralPath (Join-Path $crispasrSrc "README.md")) {
    Copy-Item -LiteralPath (Join-Path $crispasrSrc "README.md") -Destination (Join-Path $crispasrDst "README.md")
}
$packed = 0
foreach ($variant in @("cuda", "cpu")) {
    $srcVar = Join-Path $crispasrSrc $variant
    if (-not (Test-Path -LiteralPath $srcVar)) { continue }
    $dstVar = Join-Path $crispasrDst $variant
    New-Item -ItemType Directory -Force -Path $dstVar | Out-Null
    Get-ChildItem -LiteralPath $srcVar -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^(crispasr\.exe|crispasr)$' -or $_.Extension -in '.dll', '.so', '.dylib' } |
        ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $dstVar $_.Name)
            $packed++
        }
}
# Legacy flat layout (pre cuda/cpu split) — still ship if present.
Get-ChildItem -LiteralPath $crispasrSrc -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^(crispasr\.exe|crispasr)$' -or $_.Extension -in '.dll', '.so', '.dylib' } |
    ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $crispasrDst $_.Name)
        $packed++
    }
if ($packed -gt 0) {
    Write-Host "[INFO] CrispASR empaquetado ($packed archivos; cuda/ + cpu/ si existen)" -ForegroundColor Green
} else {
    Write-Host "[WARN] Sin crispasr en runtime\bin\cuda|cpu — ejecuta scripts\fetch-crispasr.ps1" -ForegroundColor Yellow
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

Write-Host "[INFO] Compilador: $isccPath (v$appVersion)" -ForegroundColor Green
& $isccPath "/DMyAppVersion=$appVersion" (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] La compilacion fallo (codigo $LASTEXITCODE)." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "[EXITO] Instalador compilado." -ForegroundColor Green
