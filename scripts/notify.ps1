param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Message,
    [int]$Progress = -1,
    [string]$IconPath = ""
)

$ErrorActionPreference = 'SilentlyContinue'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppRoot = Split-Path -Parent $ScriptDir

$Candidates = @()
if ($IconPath) { $Candidates += $IconPath }
$Candidates += 'U:\Pictures\Icons\unicorn.jpg'
$Candidates += (Join-Path $env:USERPROFILE 'Pictures\Icons\unicorn.jpg')
$Candidates += (Join-Path $AppRoot 'src-tauri\icons\icon.png')
$Candidates += (Join-Path $env:USERPROFILE '.grok\skills\windows-notify\assets\icons\unicorn.jpg')
$Candidates += (Join-Path $env:USERPROFILE '.gemini\config\skills\windows-notify\assets\icons\unicorn.jpg')
$Candidates += (Join-Path $env:USERPROFILE 'Pictures\Icons\custom.png')

$AppLogo = $Candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1

Import-Module BurntToast -ErrorAction SilentlyContinue
if (-not (Get-Command New-BurntToastNotification -ErrorAction SilentlyContinue)) {
    exit 0
}

$DisplayTitle = if ($Progress -ge 0) { "$Title ($Progress%)" } else { $Title }
if ($AppLogo) {
    New-BurntToastNotification -Text $DisplayTitle, $Message -AppLogo $AppLogo -Sound 'Default' | Out-Null
} else {
    New-BurntToastNotification -Text $DisplayTitle, $Message -Sound 'Default' | Out-Null
}
