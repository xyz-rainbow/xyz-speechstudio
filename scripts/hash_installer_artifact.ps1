# Print SHA-256 for a Setup/deb/dmg artifact (never treat a bare speech-studio.exe as an installer).
param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$ErrorActionPreference = "Stop"
$item = Get-Item -LiteralPath $Path
$name = $item.Name.ToLowerInvariant()
if ($name -eq "speech-studio.exe" -or ($name.EndsWith(".exe") -and $name -notmatch "setup")) {
    throw "Refusing to hash a bare application EXE as an installer: $($item.Name)"
}
$hash = Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256
"{0}  {1}  {2} bytes" -f $hash.Hash.ToLowerInvariant(), $item.Name, $item.Length
