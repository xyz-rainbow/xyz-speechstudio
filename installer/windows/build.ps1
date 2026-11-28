# RAINBOW TECHNOLOGY - Speech Studio installer compiler
param([switch]$IncludeCuda)
$ErrorActionPreference = "Stop"

Write-Host "==============================================================================" -ForegroundColor Magenta
Write-Host "   RAINBOW TECHNOLOGY - SPEECH STUDIO INSTALLER" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Magenta
Write-Host ""

$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
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

if ((Get-Item -LiteralPath $exe).LastWriteTimeUtc -lt (Get-Item -LiteralPath (Join-Path $repo 'src-tauri\tauri.conf.json')).LastWriteTimeUtc) {
    throw 'Executable predates the version configuration. Run npx tauri build --no-bundle first.'
}
Write-Host "[INFO] Preparando app_payload" -ForegroundColor Cyan
$payloadAbsolute = [IO.Path]::GetFullPath($payload)
if ($payloadAbsolute -ne [IO.Path]::GetFullPath((Join-Path $repo 'installer\windows\app_payload'))) {
    throw 'Unexpected payload directory'
}
Get-ChildItem -LiteralPath $payloadAbsolute -Force | Where-Object { $_.Name -ne ".gitkeep" } | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
}
Copy-Item -LiteralPath $exe -Destination (Join-Path $payload "speech-studio.exe")
Copy-Item -LiteralPath $icon -Destination (Join-Path $payload "speech-studio.ico")
Copy-Item -LiteralPath (Join-Path $repo "backend") -Destination (Join-Path $payload "backend") -Recurse
Get-ChildItem -LiteralPath (Join-Path $payload "backend") -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $payload "scripts") | Out-Null
Copy-Item -LiteralPath (Join-Path $repo "scripts\notify.ps1") -Destination (Join-Path $payload "scripts\notify.ps1")
Copy-Item -LiteralPath (Join-Path $repo "scripts\fetch-crispasr.ps1") -Destination (Join-Path $payload "scripts\fetch-crispasr.ps1")
if (Test-Path -LiteralPath (Join-Path $repo "scripts\speechstudio.cmd")) {
    Copy-Item -LiteralPath (Join-Path $repo "scripts\speechstudio.cmd") -Destination (Join-Path $payload "scripts\speechstudio.cmd")
}
# Vertical voice-pack slice only (never copy manifest.full.v1.json into installer payload).
$packSrc = Join-Path $repo "packs\xyz-ioquendo"
if (Test-Path -LiteralPath $packSrc) {
    $packDst = Join-Path $payload "packs\xyz-ioquendo"
    New-Item -ItemType Directory -Force -Path $packDst | Out-Null
    foreach ($metaName in @("manifest.vertical.v1.json", "schema.v1.json", "README.md")) {
        $srcMeta = Join-Path $packSrc $metaName
        if (Test-Path -LiteralPath $srcMeta) {
            Copy-Item -LiteralPath $srcMeta -Destination (Join-Path $packDst $metaName)
        }
    }
    foreach ($relVoice in @("es-ES\alvaro", "en-GB\alfie")) {
        $vSrc = Join-Path $packSrc (Join-Path "voices" $relVoice)
        if (Test-Path -LiteralPath $vSrc) {
            $vDst = Join-Path $packDst (Join-Path "voices" $relVoice)
            New-Item -ItemType Directory -Force -Path $vDst | Out-Null
            Get-ChildItem -LiteralPath $vSrc -Force | ForEach-Object {
                Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $vDst $_.Name) -Recurse -Force
            }
        }
    }
}
# CrispASR: GPU (cuda/) + CPU (cpu/) follow the in-app device selector.
$crispasrSrc = Join-Path $repo "runtime\bin"
$crispasrDst = Join-Path $payload "runtime\bin"
New-Item -ItemType Directory -Force -Path $crispasrDst | Out-Null
if (Test-Path -LiteralPath (Join-Path $crispasrSrc "README.md")) {
    Copy-Item -LiteralPath (Join-Path $crispasrSrc "README.md") -Destination (Join-Path $crispasrDst "README.md")
}
$packed = 0
$variants = @('cpu')
if ($IncludeCuda) { $variants += 'cuda' }
foreach ($variant in $variants) {
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
# Legacy flat layout (pre cuda/cpu split) — only use if cpu/ was not packed.
$cpuPacked = Test-Path -LiteralPath (Join-Path $crispasrDst "cpu\crispasr.exe")
if (-not $cpuPacked) {
    Get-ChildItem -LiteralPath $crispasrSrc -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^(crispasr\.exe|crispasr)$' -or $_.Extension -in '.dll', '.so', '.dylib' } |
        ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $crispasrDst $_.Name)
            $packed++
        }
    $cpuPacked = Test-Path -LiteralPath (Join-Path $crispasrDst "crispasr.exe")
}
if (-not $cpuPacked) {
    throw "Missing CrispASR CPU binary in runtime\bin\cpu; run .\scripts\fetch-crispasr.ps1 -Variant cpu first."
}
Write-Host "[INFO] CrispASR empaquetado ($packed archivos; $($variants -join ', '))" -ForegroundColor Green
$stagedInstaller = Join-Path $payload "installer"
New-Item -ItemType Directory -Force -Path $stagedInstaller | Out-Null
Copy-Item -LiteralPath (Join-Path $repo "installer\setup-env.ps1") -Destination $stagedInstaller
Get-ChildItem -LiteralPath (Join-Path $repo "installer") -Filter "requirements-*.txt" | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $stagedInstaller
}

# uv is a build-time dependency. The installed app carries this interpreter.
# Native tools often write progress to stderr; do not treat that as a terminating error.
$buildPython = Join-Path $repo 'data\tmp\installer-core\Scripts\python.exe'
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    if (-not (Test-Path -LiteralPath $buildPython)) {
        & uv venv --managed-python --python 3.12 (Join-Path $repo 'data\tmp\installer-core')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the core packaging environment' }
    }
    & uv pip install --python $buildPython -r (Join-Path $repo 'installer\requirements-core.txt') -r (Join-Path $repo 'installer\requirements-stt-cpu.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not install core packaging dependencies' }
} finally {
    $ErrorActionPreference = $prevEap
}
$runtimeOut = Join-Path $payload 'runtime\python'
if (Test-Path -LiteralPath $runtimeOut) {
    Remove-Item -LiteralPath $runtimeOut -Recurse -Force
}
& $buildPython (Join-Path $repo 'scripts\package_runtime.py') --output $runtimeOut
if ($LASTEXITCODE -ne 0) { throw 'Could not package the standalone core runtime' }

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
& $isccPath /Qp "/DMyAppVersion=$appVersion" (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] La compilacion fallo (codigo $LASTEXITCODE)." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "[EXITO] Instalador compilado." -ForegroundColor Green
