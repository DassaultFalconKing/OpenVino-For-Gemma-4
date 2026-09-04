[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ModelServerPath,

    [string]$DependenciesRoot = "opt",
    [switch]$InstallDependencies,
    [switch]$SkipApply,
    [switch]$SkipParserTests,

    [string]$DeployTo,
    [switch]$ForceDeploy
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$ModelServerPath = (Resolve-Path $ModelServerPath).Path

if (-not $SkipApply) {
    & (Join-Path $PSScriptRoot "apply-backport.ps1") -ModelServerPath $ModelServerPath
}

Push-Location $ModelServerPath
try {
    if ($InstallDependencies) {
        & .\windows_install_build_dependencies.bat $DependenciesRoot
        if ($LASTEXITCODE -ne 0) { throw "windows_install_build_dependencies.bat failed." }
    }

    # JINJA mode requires the Python-enabled OVMS build. Build tests too so the
    # upstream Gemma4 regression suite can be run before packaging the runtime.
    & .\windows_build.bat $DependenciesRoot --with_python --with_tests
    if ($LASTEXITCODE -ne 0) { throw "windows_build.bat failed." }

    if (-not $SkipParserTests) {
        $LlmModels = Join-Path $ModelServerPath "src\test\llm_testing"
        & .\windows_prepare_llm_models.bat $LlmModels
        if ($LASTEXITCODE -ne 0) { throw "windows_prepare_llm_models.bat failed." }

        & python .\windows_change_test_configs.py
        if ($LASTEXITCODE -ne 0) { throw "windows_change_test_configs.py failed." }

        & .\bazel-bin\src\ovms_test.exe "--gtest_filter=Gemma4OutputParserTest.*"
        if ($LASTEXITCODE -ne 0) { throw "Gemma4OutputParserTest regression suite failed." }
    }

    $OvmsExe = Join-Path $ModelServerPath "bazel-bin\src\ovms.exe"
    if (-not (Test-Path $OvmsExe)) {
        throw "Build returned success but ovms.exe was not found at $OvmsExe"
    }

    # Package the matching EXE + OpenVINO/GenAI/tokenizer DLLs + self-contained Python.
    # Deploying only ovms.exe over an older unpacked directory can create ABI/runtime skew.
    & .\windows_create_package.bat $DependenciesRoot --with_python
    if ($LASTEXITCODE -ne 0) { throw "windows_create_package.bat failed." }

    $PackageDir = Join-Path $ModelServerPath "dist\windows\ovms"
    $PackagedExe = Join-Path $PackageDir "ovms.exe"
    if (-not (Test-Path $PackagedExe)) {
        throw "Package creation returned success but packaged ovms.exe was not found at $PackagedExe"
    }

    Write-Host "Patched self-contained OVMS package is ready:"
    Write-Host "  $PackageDir"

    if ($DeployTo) {
        $DeployTo = [System.IO.Path]::GetFullPath($DeployTo)
        $PackageDirFull = [System.IO.Path]::GetFullPath($PackageDir)
        if ($DeployTo.TrimEnd('\') -ieq $PackageDirFull.TrimEnd('\')) {
            throw "DeployTo must be different from the build package directory."
        }

        if (Test-Path $DeployTo) {
            $existing = @(Get-ChildItem -LiteralPath $DeployTo -Force -ErrorAction Stop)
            if ($existing.Count -gt 0) {
                if (-not $ForceDeploy) {
                    throw "DeployTo is not empty: $DeployTo. Stop any running OVMS and either choose a new directory or pass -ForceDeploy."
                }

                $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
                $backup = "$DeployTo.backup-$stamp"
                Write-Host "Backing up existing OVMS deployment:"
                Write-Host "  $DeployTo"
                Write-Host "  -> $backup"
                Move-Item -LiteralPath $DeployTo -Destination $backup
            }
        }

        New-Item -ItemType Directory -Path $DeployTo -Force | Out-Null
        Copy-Item -Path (Join-Path $PackageDir "*") -Destination $DeployTo -Recurse -Force

        $DeployedExe = Join-Path $DeployTo "ovms.exe"
        if (-not (Test-Path $DeployedExe)) {
            throw "Deployment copy finished but ovms.exe is missing from $DeployTo"
        }

        & $DeployedExe --version
        if ($LASTEXITCODE -ne 0) { throw "Deployed ovms.exe failed --version sanity check." }

        Write-Host "Patched OVMS deployed successfully:"
        Write-Host "  $DeployTo"
    }
} finally {
    Pop-Location
}
