param(
    [ValidateSet('agents','claude')]
    [string]$Target = 'agents',
    [string]$Destination
)
$ErrorActionPreference = 'Stop'
$Source = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Destination) {
    $root = if ($Target -eq 'claude') { Join-Path $HOME '.claude\skills' } else { Join-Path $HOME '.agents\skills' }
    $Destination = Join-Path $root 'gemma4-roundtrip-forensics'
}
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
Get-ChildItem -LiteralPath $Source -Force | Where-Object { $_.Name -notin @('.git') } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force
}
Write-Host "Installed gemma4-roundtrip-forensics to $Destination"
Write-Host "Verify: python -m unittest discover `"$Destination\tests`" -p 'test_roundtrip_probe*.py' -v"
