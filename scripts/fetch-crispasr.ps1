# Download CrispASR into runtime/bin for Speech Studio (Windows x86_64).
# Usage: .\scripts\fetch-crispasr.ps1 [-Variant cuda|cpu|vulkan]
param(
    [ValidateSet("cuda", "cpu", "vulkan")]
    [string]$Variant = "cuda"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$BinDir = Join-Path $Root "runtime\bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

$Release = Invoke-RestMethod -Uri "https://api.github.com/repos/CrispStrobe/CrispASR/releases/latest"
$AssetName = switch ($Variant) {
    "cpu" { "crispasr-windows-x86_64-cpu.zip" }
    "vulkan" { "crispasr-windows-x86_64-vulkan.zip" }
    default { "crispasr-windows-x86_64-cuda.zip" }
}
$Asset = $Release.assets | Where-Object { $_.name -eq $AssetName } | Select-Object -First 1
if (-not $Asset) {
    throw "Asset not found in latest release: $AssetName"
}

$ZipPath = Join-Path $env:TEMP $AssetName
Write-Host "Downloading $($Asset.browser_download_url) ..."
Invoke-WebRequest -Uri $Asset.browser_download_url -OutFile $ZipPath

$ExtractDir = Join-Path $env:TEMP ("crispasr-extract-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null
Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force

$Exe = Get-ChildItem -Path $ExtractDir -Recurse -Filter "crispasr.exe" | Select-Object -First 1
if (-not $Exe) {
    throw "crispasr.exe not found inside $AssetName"
}
Copy-Item -Force $Exe.FullName (Join-Path $BinDir "crispasr.exe")
Write-Host "Installed: $(Join-Path $BinDir 'crispasr.exe')"
Write-Host "Tag: $($Release.tag_name)"
