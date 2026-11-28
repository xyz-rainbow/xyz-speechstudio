# DEVELOPER / REPAIR ONLY — not the end-user install path.
# End users get runtime/python from installer/windows/build.ps1 (no system Python/uv).
# This script creates runtime/envs/{core,stt,pytts} with uv for local repair or optional engines.
param(
    [Parameter(Mandatory = $true)]
    [string]$AppRoot
)

$ErrorActionPreference = "Stop"

function Find-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    throw "uv no esta instalado. Instala uv y vuelve a ejecutar este script."
}

function Install-Env {
    param(
        [string]$Uv,
        [string]$Name,
        [string]$Requirements
    )
    $venv = Join-Path $AppRoot "runtime\envs\$Name"
    $python = Join-Path $venv "Scripts\python.exe"
    Write-Host "[Speech Studio] Entorno $Name"
    if (-not (Test-Path -LiteralPath $python)) {
        & $Uv venv --python 3.12 $venv
        if ($LASTEXITCODE -ne 0) { throw "uv venv fallo para $Name" }
    }
    if ($Name -eq "pytts") {
        Write-Host "[Speech Studio] PyTorch para pytts (--torch-backend=auto)"
        & $Uv pip install --python $python torch torchaudio --torch-backend=auto
        if ($LASTEXITCODE -ne 0) { throw "uv pip install de torch fallo para pytts" }
    }
    & $Uv pip install --python $python -r $Requirements
    if ($LASTEXITCODE -ne 0) { throw "uv pip install fallo para $Name" }
}

if (-not (Test-Path -LiteralPath $AppRoot)) {
    throw "No existe la carpeta de la app: $AppRoot"
}

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$uv = Find-Uv
Write-Host "[Speech Studio] uv: $uv"

foreach ($pair in @(
    @{ Name = "core"; File = "requirements-core.txt" },
    @{ Name = "stt"; File = "requirements-stt.txt" },
    @{ Name = "pytts"; File = "requirements-pytts.txt" }
)) {
    $req = Join-Path $here $pair.File
    if (-not (Test-Path -LiteralPath $req)) {
        throw "Falta $req"
    }
    Install-Env -Uv $uv -Name $pair.Name -Requirements $req
}

foreach ($dir in @("data", "data\models", "data\profiles", "data\outputs", "data\tmp")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $AppRoot $dir) | Out-Null
}
Write-Host "[Speech Studio] Entornos core, stt y pytts listos en runtime\envs."
