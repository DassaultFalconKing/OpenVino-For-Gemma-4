[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ModelServerPath,

    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    foreach ($candidate in @("python", "python3", "py")) {
        $resolved = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($null -ne $resolved) {
            $PythonExe = $resolved.Source
            break
        }
    }
}

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    throw "Python 3 is required. Pass -PythonExe or put python/python3/py on PATH."
}

$portableApplier = Join-Path $PSScriptRoot "apply_backport.py"
if (-not (Test-Path -LiteralPath $portableApplier -PathType Leaf)) {
    throw "Portable applier not found: $portableApplier"
}

& $PythonExe $portableApplier --model-server $ModelServerPath
if ($LASTEXITCODE -ne 0) {
    throw "Portable Gemma4 backport applier failed with exit code $LASTEXITCODE"
}
