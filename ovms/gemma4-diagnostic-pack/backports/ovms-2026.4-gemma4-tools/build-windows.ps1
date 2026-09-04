[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ModelServerPath,

    [string]$DependenciesRoot = "opt",
    [switch]$InstallDependencies,
    [switch]$SkipApply,
    [switch]$SkipParserTests
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
    # upstream Gemma4 regression suite can be run before replacing ovms.exe.
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

    Write-Host "Patched OVMS build is ready:"
    Write-Host "  $OvmsExe"
} finally {
    Pop-Location
}
