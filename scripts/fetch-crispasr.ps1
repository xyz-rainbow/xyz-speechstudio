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
    [string]$Variant = "both",
    [string]$RootDir = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try {
    $Host.UI.RawUI.WindowTitle = "Speech Studio - CrispASR ($Variant)"
} catch {
}
Add-Type -AssemblyName System.IO.Compression.FileSystem

$Root = if ($RootDir) { $RootDir } else { Split-Path -Parent $PSScriptRoot }
$BinDir = Join-Path $Root "runtime\bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

$Release = Invoke-RestMethod -Uri "https://api.github.com/repos/CrispStrobe/CrispASR/releases/latest" -Headers @{ "User-Agent" = "SpeechStudio-Installer" }

function Get-AssetName([string]$v) {
    switch ($v) {
        "cpu" { return "crispasr-windows-x86_64-cpu.zip" }
        "vulkan" { return "crispasr-windows-x86_64-vulkan.zip" }
        default { return "crispasr-windows-x86_64-cuda.zip" }
    }
}

function Download-FileFast([string]$Uri, [string]$OutFile) {
    $curlExe = Join-Path $env:SystemRoot "System32\curl.exe"
    if (Test-Path -LiteralPath $curlExe) {
        $isInteractive = $false
        try {
            $isInteractive = -not [Console]::IsOutputRedirected
        } catch {
            $isInteractive = $false
        }
        $progressFlag = if ($isInteractive) { "-#" } else { "-sS" }
        $curlArgs = @("-fL", "--retry", "3", "--retry-delay", "2", "--connect-timeout", "30", $progressFlag, "-o", $OutFile, $Uri)
        & $curlExe @curlArgs
        if ($LASTEXITCODE -ne 0) {
            if (Test-Path -LiteralPath $OutFile) {
                Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue
            }
            throw "curl.exe failed with exit code $LASTEXITCODE downloading $Uri"
        }
        return
    }

    $wc = New-Object System.Net.WebClient
    try {
        $wc.Headers.Add("User-Agent", "SpeechStudio-Installer")
        $wc.DownloadFile($Uri, $OutFile)
    } finally {
        $wc.Dispose()
    }
}

function Get-FileSha256Hex([string]$Path) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $hashBytes = $sha.ComputeHash($stream)
        return ([BitConverter]::ToString($hashBytes).Replace("-", "").ToLowerInvariant())
    } finally {
        $stream.Dispose()
        $sha.Dispose()
    }
}

function Install-Variant([string]$v) {
    $AssetName = Get-AssetName $v
    $Asset = $Release.assets | Where-Object { $_.name -eq $AssetName } | Select-Object -First 1
    if (-not $Asset) {
        throw "Asset not found in latest release: $AssetName"
    }

    $ZipPath = Join-Path $env:TEMP ("crispasr-" + $v + "-" + [guid]::NewGuid().ToString("N") + ".zip")
    $ExtractDir = Join-Path $env:TEMP ("crispasr-extract-" + $v + "-" + [guid]::NewGuid().ToString("N"))
    $StagingDir = Join-Path $BinDir ($v + '.staging-' + [guid]::NewGuid().ToString('N'))
    $BackupDir = Join-Path $BinDir ($v + '.previous-' + [guid]::NewGuid().ToString('N'))

    try {
        $sizeMb = [math]::Round([double]$Asset.size / 1MB, 1)
        Write-Host "Downloading $($Asset.name) (~$sizeMb MB)..."
        Download-FileFast $Asset.browser_download_url $ZipPath

        Write-Host "Verifying size and SHA-256..."
        if ((Get-Item -LiteralPath $ZipPath).Length -ne [long]$Asset.size) {
            throw 'Downloaded runtime size does not match the release asset'
        }
        if (-not $Asset.digest -or $Asset.digest -notmatch '^sha256:([0-9a-fA-F]{64})$') {
            throw 'The release asset has no valid SHA-256 digest'
        }
        $ExpectedHash = $Matches[1].ToLowerInvariant()
        if ((Get-FileSha256Hex $ZipPath) -ne $ExpectedHash) {
            throw 'Downloaded runtime SHA-256 does not match the release asset'
        }

        Write-Host "Extracting archive..."
        [System.IO.Compression.ZipFile]::ExtractToDirectory($ZipPath, $ExtractDir)

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
        Write-Host "Installed [$v]: $(Join-Path $DestDir 'crispasr.exe') (+ $($Dlls.Count) DLLs)"
    } finally {
        $ResolvedBin = [IO.Path]::GetFullPath($BinDir)
        $ResolvedTemp = [IO.Path]::GetFullPath($env:TEMP)
        foreach ($TemporaryDir in @($BackupDir, $StagingDir, $ExtractDir)) {
            $ResolvedTemporary = [IO.Path]::GetFullPath($TemporaryDir)
            $AllowedParent = if ($TemporaryDir -eq $ExtractDir) { $ResolvedTemp } else { $ResolvedBin }
            if ([IO.Path]::GetDirectoryName($ResolvedTemporary) -eq $AllowedParent -and (Test-Path -LiteralPath $ResolvedTemporary)) {
                Remove-Item -LiteralPath $ResolvedTemporary -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        if (Test-Path -LiteralPath $ZipPath) {
            Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
        }
    }
}

$variants = if ($Variant -eq "both") { @("cuda", "cpu") } else { @($Variant) }
foreach ($v in $variants) {
    Install-Variant $v
}
Write-Host "Tag: $($Release.tag_name)"
Write-Host "Device selector: GPU -> runtime\bin\cuda , CPU -> runtime\bin\cpu"
