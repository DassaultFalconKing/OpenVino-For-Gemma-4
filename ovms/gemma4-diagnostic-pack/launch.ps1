param(
    [Parameter(Mandatory=$true)]
    [string]$ModelPath,

    [ValidateSet("vlm-stable", "vlm-cb-experimental")]
    [string]$Profile = "vlm-stable",

    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]*$')]
    [string]$ModelName = "gemma4",

    [string]$OvmsExe = "ovms.exe",

    [ValidateRange(1, 65535)]
    [int]$RestPort = 8000,

    [string]$RuntimeDirectory,

    [ValidateRange(1, 2147483647)]
    [int]$MaxTokensLimit = 65536,

    [ValidateSet("JINJA", "MINJA")]
    [string]$ChatTemplateMode = "JINJA",

    [switch]$SkipCanonicalTemplate,
    [switch]$RefreshCanonicalTemplate,
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"

$CanonicalTemplateRevision = "711c1368e39f1712f48ff0eb7bcdbbb760d52db0"
$CanonicalTemplateSource = "google/gemma-4-12B-it"
$CanonicalTemplateUrl = "https://huggingface.co/$CanonicalTemplateSource/resolve/$CanonicalTemplateRevision/chat_template.jinja?download=true"

function To-OvmsPath([string]$PathValue) {
    return $PathValue.Replace('\', '/')
}

function Get-FileSha256([string]$PathValue) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $PathValue).Hash.ToUpperInvariant()
}

function Test-CanonicalGemma4Template([string]$PathValue) {
    if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) { return $false }
    $text = Get-Content -Raw -Encoding UTF8 -LiteralPath $PathValue
    return $text.Contains("Template: Google Gemma 4 Canonical Chat Template") -and
           $text.Contains("<|tool_call>") -and
           $text.Contains("<tool_call|>") -and
           $text.Contains("<|tool_response>") -and
           $text.Contains("<tool_response|>") -and
           $text.Contains("macro format_argument")
}

function Install-CanonicalGemma4Template([string]$ResolvedModelPath) {
    $templatePath = Join-Path $ResolvedModelPath "chat_template.jinja"
    $statePath = Join-Path $ResolvedModelPath ".gemmamonster-chat-template.json"

    if (-not $RefreshCanonicalTemplate -and
        (Test-Path -LiteralPath $templatePath -PathType Leaf) -and
        (Test-Path -LiteralPath $statePath -PathType Leaf)) {
        try {
            $state = Get-Content -Raw -Encoding UTF8 -LiteralPath $statePath | ConvertFrom-Json
            $currentHash = Get-FileSha256 $templatePath
            if ($state.revision -eq $CanonicalTemplateRevision -and
                $state.sha256 -eq $currentHash -and
                (Test-CanonicalGemma4Template $templatePath)) {
                Write-Host "Canonical Gemma-4 template already installed ($($CanonicalTemplateRevision.Substring(0,8)), SHA256 $currentHash)."
                return
            }
        } catch {
            Write-Warning "Ignoring stale template state file: $($_.Exception.Message)"
        }
    }

    $tmp = Join-Path $env:TEMP ("gemma4-chat-template-{0}.jinja" -f ([Guid]::NewGuid().ToString("N")))
    try {
        Write-Host "Fetching Google canonical Gemma-4 chat template..."
        Write-Host "  source:   $CanonicalTemplateSource"
        Write-Host "  revision: $CanonicalTemplateRevision"
        Invoke-WebRequest -UseBasicParsing -Uri $CanonicalTemplateUrl -OutFile $tmp

        if (-not (Test-CanonicalGemma4Template $tmp)) {
            throw "Downloaded file does not satisfy the canonical Gemma-4 template markers. Refusing to install it."
        }
        $newHash = Get-FileSha256 $tmp

        if (Test-Path -LiteralPath $templatePath -PathType Leaf) {
            $oldHash = Get-FileSha256 $templatePath
            if ($oldHash -eq $newHash) {
                Write-Host "Model template content already matches canonical SHA256 $newHash."
            } else {
                $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
                $backupPath = "$templatePath.pre-gemmamonster-$stamp.bak"
                Copy-Item -LiteralPath $templatePath -Destination $backupPath
                Write-Host "Backed up previous template: $backupPath"
                Copy-Item -LiteralPath $tmp -Destination $templatePath -Force
            }
        } else {
            Copy-Item -LiteralPath $tmp -Destination $templatePath -Force
        }

        $installedHash = Get-FileSha256 $templatePath
        if ($installedHash -ne $newHash) {
            throw "Template hash changed while installing (download=$newHash installed=$installedHash)."
        }

        $stateObject = [ordered]@{
            source = $CanonicalTemplateSource
            revision = $CanonicalTemplateRevision
            url = $CanonicalTemplateUrl
            sha256 = $installedHash
            installed_utc = [DateTime]::UtcNow.ToString("o")
        }
        $stateJson = $stateObject | ConvertTo-Json -Depth 4
        $utf8NoBomLocal = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText($statePath, $stateJson, $utf8NoBomLocal)
        Write-Host "Canonical Gemma-4 template installed: $templatePath"
        Write-Host "  SHA256: $installedHash"
    } finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
}

$PackRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResolvedModelPath = (Resolve-Path -LiteralPath $ModelPath).Path

if (-not (Test-Path (Join-Path $ResolvedModelPath "config.json"))) {
    Write-Warning "Model directory has no config.json: $ResolvedModelPath"
}

if ($SkipCanonicalTemplate) {
    Write-Warning "SkipCanonicalTemplate requested; keeping the model's existing chat_template.jinja unchanged."
    if (-not (Test-Path (Join-Path $ResolvedModelPath "chat_template.jinja"))) {
        Write-Warning "Model directory has no chat_template.jinja. OVMS may use tokenizer/config template metadata instead."
    }
} else {
    Install-CanonicalGemma4Template $ResolvedModelPath
}

$TemplateGraph = Join-Path $PackRoot "profiles\$Profile\graph.pbtxt"
if (-not (Test-Path $TemplateGraph)) {
    throw "Profile graph not found: $TemplateGraph"
}

$RuntimeRoot = if ($RuntimeDirectory) {
    [System.IO.Path]::GetFullPath($RuntimeDirectory)
} else {
    Join-Path $PackRoot "runtime\$ModelName\$Profile"
}
New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null

$RuntimeGraph = Join-Path $RuntimeRoot "graph.pbtxt"
$RuntimeConfig = Join-Path $RuntimeRoot "config.json"

$modelForGraph = (To-OvmsPath $ResolvedModelPath).Replace('"', '\"')
$graphText = Get-Content -Raw -Encoding UTF8 $TemplateGraph
$graphText = $graphText.Replace("__MODEL_PATH__", $modelForGraph)
$graphText = $graphText.Replace("__CHAT_TEMPLATE_MODE__", $ChatTemplateMode)
$graphText = $graphText.Replace("__MAX_TOKENS_LIMIT__", $MaxTokensLimit.ToString())
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($RuntimeGraph, $graphText, $utf8NoBom)

$configObject = @{
    model_config_list = @()
    mediapipe_config_list = @(
        @{
            name = $ModelName
            graph_path = (To-OvmsPath $RuntimeGraph)
        }
    )
}
$configJson = $configObject | ConvertTo-Json -Depth 8
[System.IO.File]::WriteAllText($RuntimeConfig, $configJson, $utf8NoBom)

Write-Host ""
Write-Host "Gemma-4 OVMS profile prepared"
Write-Host "  model:         $ResolvedModelPath"
Write-Host "  endpoint name: $ModelName"
Write-Host "  profile:       $Profile"
Write-Host "  template mode: $ChatTemplateMode"
Write-Host "  template pin:  $CanonicalTemplateRevision"
Write-Host "  config:        $RuntimeConfig"
Write-Host "  port:          $RestPort"
Write-Host "  max tokens:    $MaxTokensLimit"
Write-Host "  client URL:    http://127.0.0.1:$RestPort/v3"
Write-Host ""

if ($NoLaunch) {
    Write-Host "NoLaunch requested; OVMS was not started."
    exit 0
}

$ResolvedOvmsExe = if (Test-Path -LiteralPath $OvmsExe -PathType Leaf) {
    (Resolve-Path -LiteralPath $OvmsExe).Path
} else {
    (Get-Command $OvmsExe -CommandType Application -ErrorAction Stop).Source
}
$ServerDirectory = Split-Path -Parent $ResolvedOvmsExe
$BundledPython = Join-Path $ServerDirectory 'python'
if (-not (Test-Path -LiteralPath (Join-Path $BundledPython 'python.exe') -PathType Leaf)) {
    throw "Bundled Python missing: $BundledPython. Extract the complete OVMS Windows package, including DLLs and python/."
}

$savedPythonHome = $env:PYTHONHOME
$savedPythonPath = $env:PYTHONPATH
$savedPath = $env:PATH
$serverExitCode = 1
try {
    $env:PYTHONHOME = $BundledPython
    $env:PYTHONPATH = $BundledPython
    $env:PATH = "$ServerDirectory;$BundledPython;" + $savedPath

    Write-Host "Starting OVMS. Wait for AVAILABLE before sending requests. Press Ctrl+C to stop."
    & $ResolvedOvmsExe `
        --config_path $RuntimeConfig `
        --rest_port $RestPort `
        --rest_workers 1
    $serverExitCode = $LASTEXITCODE
} finally {
    $env:PYTHONHOME = $savedPythonHome
    $env:PYTHONPATH = $savedPythonPath
    $env:PATH = $savedPath
}

exit $serverExitCode
