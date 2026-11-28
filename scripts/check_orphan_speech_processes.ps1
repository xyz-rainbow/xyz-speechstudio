# After quitting Speech Studio, report leftover speech-related processes.
# Exit 0 if clean; exit 1 if orphans matching known names remain.
param(
    [switch]$Kill
)

$ErrorActionPreference = "Stop"
$patterns = @(
    "speech-studio",
    "crispasr",
    "Speech Studio"
)

# Ignore tools whose command line merely mentions the product path (e.g. git in this repo).
$ignoreNames = @("git.exe", "git", "rg.exe", "rg", "cursor.exe", "Code.exe")

$hits = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $name = $_.Name
    if ($name -and ($ignoreNames -contains $name)) { return $false }
    $cmd = $_.CommandLine
    foreach ($p in $patterns) {
        if ($name -like "*$p*" -or ($cmd -and $cmd -like "*$p*")) { return $true }
    }
    $false
}

if (-not $hits) {
    Write-Host "[OK] No Speech Studio / CrispASR processes found."
    exit 0
}

Write-Host "[WARN] Leftover processes:"
$hits | ForEach-Object {
    Write-Host ("  PID={0} Name={1}" -f $_.ProcessId, $_.Name)
    if ($Kill) {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}
if ($Kill) {
    Write-Host "[INFO] Kill requested; re-check recommended."
}
exit 1
