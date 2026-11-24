$Target = 'Z:\[🛠️] [Tools]\xyz-speech-studio'
if (-not [System.IO.Directory]::Exists($Target)) {
    [System.IO.Directory]::CreateDirectory($Target) | Out-Null
}
if (-not (Test-Path -LiteralPath 'N:\')) {
    subst N: $Target
    Write-Host "Mounted N: -> $Target"
} else {
    Write-Host "N: is already mounted."
}
