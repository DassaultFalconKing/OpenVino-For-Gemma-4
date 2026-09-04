param(
    [Parameter(Mandatory=$true)]
    [string]$ModelPath,

    [ValidateSet("vlm-stable", "vlm-cb-experimental")]
    [string]$Profile = "vlm-stable",

    [string]$ModelName = "gemma4",

    [string]$OvmsExe = "ovms.exe",

    [int]$RestPort = 8000,

    [ValidateSet("JINJA", "MINJA")]
    [string]$ChatTemplateMode = "JINJA",

    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"

function To-OvmsPath([string]$PathValue) {
    return $PathValue.Replace('\', '/')
}

$PackRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResolvedModelPath = (Resolve-Path $ModelPath).Path

if (-not (Test-Path (Join-Path $ResolvedModelPath "config.json"))) {
    Write-Warning "Model directory has no config.json: $ResolvedModelPath"
}
if (-not (Test-Path (Join-Path $ResolvedModelPath "chat_template.jinja"))) {
    Write-Warning "Model directory has no chat_template.jinja. OVMS may use tokenizer/config template metadata instead."
}

$TemplateGraph = Join-Path $PackRoot "profiles\$Profile\graph.pbtxt"
if (-not (Test-Path $TemplateGraph)) {
    throw "Profile graph not found: $TemplateGraph"
}

$RuntimeRoot = Join-Path $PackRoot "runtime\$ModelName\$Profile"
New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null

$RuntimeGraph = Join-Path $RuntimeRoot "graph.pbtxt"
$RuntimeConfig = Join-Path $RuntimeRoot "config.json"

$modelForGraph = To-OvmsPath $ResolvedModelPath
$graphText = Get-Content -Raw -Encoding UTF8 $TemplateGraph
$graphText = $graphText.Replace("__MODEL_PATH__", $modelForGraph)
$graphText = $graphText.Replace("__CHAT_TEMPLATE_MODE__", $ChatTemplateMode)
Set-Content -Path $RuntimeGraph -Value $graphText -Encoding UTF8

$configObject = @{
    model_config_list = @()
    mediapipe_config_list = @(
        @{
            name = $ModelName
            graph_path = (To-OvmsPath $RuntimeGraph)
        }
    )
}
$configObject | ConvertTo-Json -Depth 8 | Set-Content -Path $RuntimeConfig -Encoding UTF8

Write-Host ""
Write-Host "Gemma-4 OVMS profile prepared"
Write-Host "  model:         $ResolvedModelPath"
Write-Host "  endpoint name: $ModelName"
Write-Host "  profile:       $Profile"
Write-Host "  template:      $ChatTemplateMode"
Write-Host "  config:        $RuntimeConfig"
Write-Host "  port:          $RestPort"
Write-Host ""

if ($NoLaunch) {
    Write-Host "NoLaunch requested; OVMS was not started."
    exit 0
}

$ovmsCommand = Get-Command $OvmsExe -ErrorAction SilentlyContinue
if (-not $ovmsCommand) {
    if (-not (Test-Path $OvmsExe)) {
        throw "OVMS executable not found: $OvmsExe"
    }
}

Write-Host "Starting OVMS..."
& $OvmsExe `
    --config_path $RuntimeConfig `
    --rest_port $RestPort `
    --rest_workers 1

exit $LASTEXITCODE
