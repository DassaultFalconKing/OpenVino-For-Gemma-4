# Portable Windows entry point. All relative paths are relative to this package.
param(
    [string]$ModelPath = 'models\gemma4',
    [string]$OvmsExe = 'server\ovms.exe',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]*$')]
    [string]$ModelName = 'gemma4',
    [ValidateRange(1, 65535)]
    [int]$Port = 9090,
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'
function Resolve-PackagePath([string]$Value) {
    if ([System.IO.Path]::IsPathRooted($Value)) { return $Value }
    return Join-Path $PSScriptRoot $Value
}

$modelDirectory = Resolve-PackagePath $ModelPath
$serverExecutable = Resolve-PackagePath $OvmsExe
if (-not (Test-Path -LiteralPath (Join-Path $modelDirectory 'config.json') -PathType Leaf)) {
    throw "Model not found: $modelDirectory. Put the complete OpenVINO model in models\gemma4, or pass -ModelPath. See START-HERE.md."
}
if (-not $NoLaunch -and -not (Test-Path -LiteralPath $serverExecutable -PathType Leaf)) {
    throw "Server not found: $serverExecutable. Extract the complete custom OVMS package into server, or pass -OvmsExe. See START-HERE.md."
}

$launch = Join-Path $PSScriptRoot 'ovms\gemma4-diagnostic-pack\launch.ps1'
& $launch -ModelPath $modelDirectory -OvmsExe $serverExecutable `
    -ModelName $ModelName -RestPort $Port -Profile 'vlm-stable' `
    -RuntimeDirectory (Join-Path $PSScriptRoot "generated-config\$ModelName") `
    -NoLaunch:$NoLaunch
exit $LASTEXITCODE
