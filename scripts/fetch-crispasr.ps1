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
    if ((Get-Item -LiteralPath $ZipPath).Length -ne [long]$Asset.size) {
        throw 'Downloaded runtime size does not match the release asset'
    }
    if (-not $Asset.digest -or $Asset.digest -notmatch '^sha256:([0-9a-fA-F]{64})$') {
        throw 'The release asset has no valid SHA-256 digest'
    }
    $ExpectedHash = $Matches[1]
    if ((Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash -ne $ExpectedHash) {
        throw 'Downloaded runtime SHA-256 does not match the release asset'
    }

    $ExtractDir = Join-Path $env:TEMP ("crispasr-extract-" + $v + "-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null
    Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force

    $Exe = Get-ChildItem -Path $ExtractDir -Recurse -Filter "crispasr.exe" | Select-Object -First 1
    if (-not $Exe) {
        throw "crispasr.exe not found inside $AssetName"
    }

    $DestDir = Join-Path $BinDir $v
    $ResolvedBin = [IO.Path]::GetFullPath($BinDir)
    $ResolvedDest = [IO.Path]::GetFullPath($DestDir)
    if ([IO.Path]::GetDirectoryName($ResolvedDest) -ne $ResolvedBin) {
        throw 'Unexpected runtime destination'
    }
    $StagingDir = Join-Path $BinDir ($v + '.staging-' + [guid]::NewGuid().ToString('N'))
    $BackupDir = Join-Path $BinDir ($v + '.previous-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $StagingDir | Out-Null
    Copy-Item -LiteralPath $Exe.FullName -Destination (Join-Path $StagingDir "crispasr.exe")
    $Dlls = Get-ChildItem -Path $Exe.Directory.FullName -File -Filter "*.dll" -ErrorAction SilentlyContinue
    foreach ($dll in $Dlls) {
        Copy-Item -LiteralPath $dll.FullName -Destination (Join-Path $StagingDir $dll.Name)
    }
    if (Test-Path -LiteralPath $DestDir) {
        Move-Item -LiteralPath $DestDir -Destination $BackupDir
    }
    try {
        Move-Item -LiteralPath $StagingDir -Destination $DestDir
    } catch {
        if (Test-Path -LiteralPath $BackupDir) { Move-Item -LiteralPath $BackupDir -Destination $DestDir }
        throw
    }
    foreach ($TemporaryDir in @($BackupDir, $ExtractDir)) {
        $ResolvedTemporary = [IO.Path]::GetFullPath($TemporaryDir)
        $AllowedParent = if ($TemporaryDir -eq $BackupDir) { $ResolvedBin } else { [IO.Path]::GetFullPath($env:TEMP) }
        if ([IO.Path]::GetDirectoryName($ResolvedTemporary) -ne $AllowedParent) { throw 'Unexpected cleanup directory' }
        if (Test-Path -LiteralPath $ResolvedTemporary) { Remove-Item -LiteralPath $ResolvedTemporary -Recurse -Force }
    }
    Remove-Item -LiteralPath $ZipPath -Force
    Write-Host "Installed [$v]: $(Join-Path $DestDir 'crispasr.exe') (+ $($Dlls.Count) DLLs)"
}

$variants = if ($Variant -eq "both") { @("cuda", "cpu") } else { @($Variant) }
foreach ($v in $variants) {
    Install-Variant $v
}
Write-Host "Tag: $($Release.tag_name)"
Write-Host "Device selector: GPU -> runtime\bin\cuda , CPU -> runtime\bin\cpu"
