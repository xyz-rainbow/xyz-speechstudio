# Download CrispASR into runtime/bin for Speech Studio (Windows x86_64).
# Layout:
#   runtime/bin/cuda/crispasr.exe (+ DLLs)
#   runtime/bin/cpu/crispasr.exe  (+ DLLs)
# Usage:
#   .\scripts\fetch-crispasr.ps1              # both cuda + cpu (default)
#   .\scripts\fetch-crispasr.ps1 -Variant cuda
#   .\scripts\fetch-crispasr.ps1 -Variant cpu
#   .\scripts\fetch-crispasr.ps1 -Variant both
param(
    [ValidateSet("cuda", "cpu", "vulkan", "both")]
    [string]$Variant = "both"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$BinDir = Join-Path $Root "runtime\bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

$Release = Invoke-RestMethod -Uri "https://api.github.com/repos/CrispStrobe/CrispASR/releases/latest"

function Get-AssetName([string]$v) {
    switch ($v) {
        "cpu" { return "crispasr-windows-x86_64-cpu.zip" }
        "vulkan" { return "crispasr-windows-x86_64-vulkan.zip" }
        default { return "crispasr-windows-x86_64-cuda.zip" }
    }
}

function Install-Variant([string]$v) {
    $AssetName = Get-AssetName $v
    $Asset = $Release.assets | Where-Object { $_.name -eq $AssetName } | Select-Object -First 1
    if (-not $Asset) {
        throw "Asset not found in latest release: $AssetName"
    }

    $ZipPath = Join-Path $env:TEMP ("crispasr-" + $v + "-" + [guid]::NewGuid().ToString("N") + ".zip")
    Write-Host "Downloading $($Asset.browser_download_url) ..."
    Invoke-WebRequest -Uri $Asset.browser_download_url -OutFile $ZipPath

    $ExtractDir = Join-Path $env:TEMP ("crispasr-extract-" + $v + "-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null
    Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force

    $Exe = Get-ChildItem -Path $ExtractDir -Recurse -Filter "crispasr.exe" | Select-Object -First 1
    if (-not $Exe) {
        throw "crispasr.exe not found inside $AssetName"
    }

    $DestDir = Join-Path $BinDir $v
    New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
    # Clear previous install of this variant (keep sibling variants).
    Get-ChildItem -LiteralPath $DestDir -Force -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    Copy-Item -Force $Exe.FullName (Join-Path $DestDir "crispasr.exe")
    $Dlls = Get-ChildItem -Path $Exe.Directory.FullName -File -Filter "*.dll" -ErrorAction SilentlyContinue
    foreach ($dll in $Dlls) {
        Copy-Item -Force $dll.FullName (Join-Path $DestDir $dll.Name)
    }
    Write-Host "Installed [$v]: $(Join-Path $DestDir 'crispasr.exe') (+ $($Dlls.Count) DLLs)"
}

$variants = if ($Variant -eq "both") { @("cuda", "cpu") } else { @($Variant) }
foreach ($v in $variants) {
    Install-Variant $v
}
Write-Host "Tag: $($Release.tag_name)"
Write-Host "Device selector: GPU -> runtime\bin\cuda , CPU -> runtime\bin\cpu"
