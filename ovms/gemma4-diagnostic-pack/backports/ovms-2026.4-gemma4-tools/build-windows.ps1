[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ModelServerPath,

    [string]$DependenciesRoot = "opt",
    [switch]$InstallDependencies,
    [switch]$SkipApply,
    [switch]$SkipParserTests,

    [string]$VisualStudioPath,
    [string]$DeployTo,
    [switch]$ForceDeploy
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

function Resolve-VisualStudioBuildTools {
    param([string]$RequestedPath)

    $candidates = New-Object System.Collections.Generic.List[string]
    if ($RequestedPath) {
        $candidates.Add([System.IO.Path]::GetFullPath($RequestedPath))
    }

    $ProgramFiles = [Environment]::GetEnvironmentVariable("ProgramFiles")
    $ProgramFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")

    foreach ($root in @($ProgramFiles, $ProgramFilesX86)) {
        if ($root) {
            $candidates.Add((Join-Path $root "Microsoft Visual Studio\2022\BuildTools"))
        }
    }

    # Keep literal fallbacks as well. They make diagnostics deterministic even
    # when a shell has inherited unusual ProgramFiles environment variables.
    $candidates.Add("C:\Program Files\Microsoft Visual Studio\2022\BuildTools")
    $candidates.Add("C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools")

    $seen = @{}
    foreach ($candidate in $candidates) {
        if (-not $candidate) { continue }
        $key = $candidate.TrimEnd('\').ToLowerInvariant()
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true

        if (-not (Test-Path -LiteralPath $candidate -PathType Container)) { continue }

        $msvcRoot = Join-Path $candidate "VC\Tools\MSVC"
        $clPattern = Join-Path $msvcRoot "*\bin\Hostx64\x64\cl.exe"
        $cl = Get-ChildItem -Path $clPattern -File -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            Select-Object -First 1

        if ($cl) {
            return [pscustomobject]@{
                Path = [System.IO.Path]::GetFullPath($candidate)
                ClExe = $cl.FullName
            }
        }
    }

    $checked = ($seen.Keys | Sort-Object) -join "`n  - "
    throw "Visual Studio 2022 Build Tools with x64 MSVC compiler was not found. Checked:`n  - $checked`nInstall Desktop development with C++ or pass -VisualStudioPath explicitly."
}

function Set-OvmsVisualStudioPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceRoot,
        [Parameter(Mandatory = $true)]
        [string]$VsPath
    )

    $scripts = @(
        "windows_install_build_dependencies.bat",
        "windows_build.bat"
    )
    $backups = @{}
    $hardcodedVs = 'set VS_2022_BT="C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"'
    $replacementVs = "set VS_2022_BT=`"$VsPath`""
    $hardcodedCmake = 'c:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\'
    $replacementCmake = (Join-Path $VsPath "Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin") + "\"

    try {
        foreach ($name in $scripts) {
            $path = Join-Path $SourceRoot $name
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                throw "Required OVMS Windows build script is missing: $path"
            }

            $backups[$path] = [System.IO.File]::ReadAllBytes($path)
            $text = [System.IO.File]::ReadAllText($path)
            if (-not $text.Contains($hardcodedVs)) {
                throw "Pinned OVMS script no longer contains the expected VS_2022_BT hardcode: $name"
            }

            $patched = $text.Replace($hardcodedVs, $replacementVs)
            if ($name -eq "windows_install_build_dependencies.bat") {
                $patched = $patched.Replace($hardcodedCmake, $replacementCmake)
            }

            [System.IO.File]::WriteAllText(
                $path,
                $patched,
                [System.Text.UTF8Encoding]::new($false)
            )
        }
    } catch {
        foreach ($entry in $backups.GetEnumerator()) {
            [System.IO.File]::WriteAllBytes($entry.Key, $entry.Value)
        }
        throw
    }

    return $backups
}

function Restore-OvmsWindowsBuildScripts {
    param([hashtable]$Backups)

    if (-not $Backups) { return }
    foreach ($entry in $Backups.GetEnumerator()) {
        [System.IO.File]::WriteAllBytes($entry.Key, $entry.Value)
    }
}

$ModelServerPath = (Resolve-Path $ModelServerPath).Path

if (-not $SkipApply) {
    & (Join-Path $PSScriptRoot "apply-backport.ps1") -ModelServerPath $ModelServerPath
}

$vs = Resolve-VisualStudioBuildTools -RequestedPath $VisualStudioPath
Write-Host "Using Visual Studio 2022 Build Tools:"
Write-Host "  $($vs.Path)"
Write-Host "Using MSVC compiler:"
Write-Host "  $($vs.ClExe)"

$batchBackups = $null
Push-Location $ModelServerPath
try {
    # OVMS 2026.4 RC1 hardcodes Build Tools under Program Files (x86) in two
    # batch files. Temporarily rewrite that pinned path so installations under
    # either Program Files root work, then restore the exact original bytes.
    $batchBackups = Set-OvmsVisualStudioPath -SourceRoot $ModelServerPath -VsPath $vs.Path

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
    try {
        Restore-OvmsWindowsBuildScripts -Backups $batchBackups
    } finally {
        Pop-Location
    }
}
