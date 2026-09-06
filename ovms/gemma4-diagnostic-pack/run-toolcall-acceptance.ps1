param(
    [string]$BaseUrl = "http://127.0.0.1:9090/v3",
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]*$')]
    [string]$Model = "gemma4",
    [ValidateSet("all", "none", "auto", "required", "named", "question", "stream", "roundtrip", "parallel")]
    [string]$Mode = "all",
    [string]$ModelPath,
    [string]$Python,
    [string]$OutputDirectory,
    [ValidateRange(1, 3600)]
    [int]$TimeoutSeconds = 240,
    [ValidateRange(1, 8192)]
    [int]$MaxTokens = 256,
    [switch]$SkipTokenizerCheck
)

$ErrorActionPreference = "Stop"
$PackRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-Python([string]$Requested) {
    if ($Requested) {
        if (Test-Path -LiteralPath $Requested -PathType Leaf) {
            return (Resolve-Path -LiteralPath $Requested).Path
        }
        return (Get-Command $Requested -ErrorAction Stop).Source
    }
    foreach ($candidate in @("python", "py")) {
        try {
            $cmd = Get-Command $candidate -ErrorAction Stop
            return $cmd.Source
        } catch {}
    }
    throw "Python was not found. Pass -Python C:\path\to\python.exe."
}

$PythonExe = Resolve-Python $Python
$Matrix = Join-Path $PackRoot "toolcall_matrix.py"
$TokenizerDiag = Join-Path $PackRoot "tokenizer_markers.py"

if (-not (Test-Path -LiteralPath $Matrix -PathType Leaf)) {
    throw "Acceptance matrix missing: $Matrix"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Evidence = if ($OutputDirectory) {
    [System.IO.Path]::GetFullPath($OutputDirectory)
} else {
    Join-Path $PackRoot "runtime\acceptance\$stamp"
}
New-Item -ItemType Directory -Force -Path $Evidence | Out-Null

Write-Host "Gemma-4 tool-call acceptance"
Write-Host "  endpoint: $BaseUrl"
Write-Host "  model:    $Model"
Write-Host "  mode:     $Mode"
Write-Host "  python:   $PythonExe"
Write-Host "  evidence: $Evidence"

if (-not $SkipTokenizerCheck) {
    if (-not $ModelPath) {
        Write-Warning "Tokenizer check skipped because -ModelPath was not supplied."
    } elseif (-not (Test-Path -LiteralPath $TokenizerDiag -PathType Leaf)) {
        Write-Warning "Tokenizer diagnostic script missing: $TokenizerDiag"
    } else {
        $resolvedModelPath = (Resolve-Path -LiteralPath $ModelPath).Path
        $tokenizerOutput = Join-Path $Evidence "tokenizer-markers.json"
        Write-Host ""
        Write-Host "[tokenizer] inspecting structural markers"
        & $PythonExe $TokenizerDiag --model-path $resolvedModelPath --output $tokenizerOutput
        $tokenizerExit = $LASTEXITCODE
        if ($tokenizerExit -eq 1) {
            throw "Tokenizer structural-marker diagnostic failed. See $tokenizerOutput"
        }
        if ($tokenizerExit -eq 4) {
            Write-Warning "Tokenizer diagnostic unavailable on this installation; continuing with runtime acceptance."
        } elseif ($tokenizerExit -ne 0) {
            throw "Tokenizer diagnostic failed with exit code $tokenizerExit"
        }
    }
}

Write-Host ""
Write-Host "[runtime] running $Mode matrix"
& $PythonExe $Matrix `
    --base-url $BaseUrl `
    --model $Model `
    --mode $Mode `
    --output-dir $Evidence `
    --timeout $TimeoutSeconds `
    --max-tokens $MaxTokens
$matrixExit = $LASTEXITCODE

Write-Host ""
if ($matrixExit -eq 0) {
    Write-Host "ACCEPTANCE PASS"
} else {
    Write-Host "ACCEPTANCE FAIL (exit $matrixExit)"
}
Write-Host "Evidence: $Evidence"
exit $matrixExit
