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
    $candidates.Add("C:\BuildTools")

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
                MsvcVersion = $cl.Directory.Parent.Parent.Parent.Name
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
        [string]$VsPath,
        [Parameter(Mandatory = $true)]
        [string]$MsvcVersion
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
    $hardcodedMsvcVersion = 'set "BAZEL_VC_FULL_VERSION=14.44.35207"'
    $replacementMsvcVersion = "set `"BAZEL_VC_FULL_VERSION=$MsvcVersion`""

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

                # OpenCV 4.14's option(OPENCV_PYTHON3_VERSION) is a BOOL defaulting
                # to OFF. Combined with a stray python3.exe on PATH, cmake then
                # calls find_package(Python3 "OFF"), which is fatal. Intel also
                # appends raw /GS /DYNAMICBASE /LTCG flags as extra cmake args;
                # /DYNAMICBASE is parsed as -D and /LTCG as a path.
                $hardcodedOpencvCmake = 'cmake -T v142 .. -D CMAKE_INSTALL_PREFIX=%opencv_install% -D OPENCV_EXTRA_MODULES_PATH=%opencv_contrib_dir%\modules %opencv_flags% %SDL_OPS%'
                if (-not $patched.Contains($hardcodedOpencvCmake)) {
                    throw "Pinned OVMS windows_install_build_dependencies.bat no longer contains the expected OpenCV cmake command."
                }
                $v142Root = $null
                foreach ($candidate in @($VsPath, "C:\Program", "C:\BuildTools")) {
                    $v142Cl = Get-ChildItem -Path (Join-Path $candidate "VC\Tools\MSVC\14.29*\bin\Hostx64\x64\cl.exe") -File -ErrorAction SilentlyContinue |
                        Select-Object -First 1
                    if ($v142Cl) {
                        $v142Root = $candidate
                        break
                    }
                }
                if (-not $v142Root) {
                    throw "OpenCV configure requires MSVC v142 (14.29.x), but cl.exe was not found under $VsPath, C:\Program, or C:\BuildTools."
                }
                $replacementOpencvCmake = "cmake -G `"Visual Studio 17 2022`" -T v142 `"-DCMAKE_GENERATOR_INSTANCE=$v142Root`" -D CMAKE_INSTALL_PREFIX=%opencv_install% -D OPENCV_EXTRA_MODULES_PATH=%opencv_contrib_dir%\modules -D OPENCV_PYTHON_SKIP_DETECTION=ON -D PYTHON3_EXECUTABLE=C:\opt\Python312\python.exe %opencv_flags%"
                $patched = $patched.Replace($hardcodedOpencvCmake, $replacementOpencvCmake)
            }
            if ($name -eq "windows_build.bat") {
                if (-not $patched.Contains($hardcodedMsvcVersion)) {
                    throw "Pinned OVMS windows_build.bat no longer contains the expected BAZEL_VC_FULL_VERSION hardcode."
                }
                $patched = $patched.Replace($hardcodedMsvcVersion, $replacementMsvcVersion)
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

function Invoke-NativeProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$ArgumentList = @(),
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    # curl/wget/bazel/cl write progress and warnings to stderr. PowerShell turns
    # native stderr into ErrorRecords, which become terminating when
    # $ErrorActionPreference is Stop. Keep Stop for cmdlets, but not for these.
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($ArgumentList.Count -gt 0) {
            & $FilePath @ArgumentList
        } else {
            & $FilePath
        }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldEap
    }

    if ($null -eq $code) { $code = 0 }
    if ($code -ne 0) {
        throw "$FailureMessage (exit $code)"
    }
}

function Initialize-OvmsPythonEnvironment {
    $pythonHome = "C:\opt\Python312"
    $pythonExe = Join-Path $pythonHome "python.exe"
    if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
        throw "OVMS Python is missing: $pythonExe. Run with -InstallDependencies first."
    }

    # drogon.bzl uses repository_ctx.which("python3") before "python". This
    # machine's PATH has a Python 3.14 python3.exe; combined with PYTHONHOME
    # for 3.12 that produces "SRE module mismatch".
    $python3Exe = Join-Path $pythonHome "python3.exe"
    if (-not (Test-Path -LiteralPath $python3Exe -PathType Leaf)) {
        Copy-Item -LiteralPath $pythonExe -Destination $python3Exe -Force
    }

    $env:PYTHONHOME = $pythonHome
    $env:PYTHONPATH = ""
    $env:PATH = "$pythonHome;$pythonHome\Scripts;C:\opt;" + $env:PATH
    Write-Host "Using OVMS Python:"
    Write-Host "  $pythonExe"
}

function Assert-WindowsBuildSucceeded {
    param([Parameter(Mandatory = $true)][string]$SourceRoot)

    # windows_build.bat pipes bazel through tee, so cmd.exe's errorlevel is
    # tee's (usually 0) even when bazel fails.
    $buildLog = Join-Path $SourceRoot "win_build.log"
    if (Test-Path -LiteralPath $buildLog -PathType Leaf) {
        $failed = Select-String -LiteralPath $buildLog -Pattern '^FAILED: Build did NOT complete successfully' -Quiet
        if ($failed) {
            throw "windows_build.bat failed. See $buildLog"
        }
    }

    $ovmsExe = Join-Path $SourceRoot "bazel-bin\src\ovms.exe"
    if (-not (Test-Path -LiteralPath $ovmsExe -PathType Leaf)) {
        throw "windows_build.bat returned without producing $ovmsExe"
    }
}

function Assert-Gemma4GuidanceIntegrated {
    param([Parameter(Mandatory = $true)][string]$SourceRoot)

    $builderSource = Join-Path $SourceRoot "src\llm\io_processing\gemma4\generation_config_builder.cpp"
    $builderHeader = Join-Path $SourceRoot "src\llm\io_processing\gemma4\generation_config_builder.hpp"
    foreach ($required in @($builderSource, $builderHeader)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "Gemma4 generation guidance is not integrated: missing $required. Run without -SkipApply first."
        }
    }

    $factoryPath = Join-Path $SourceRoot "src\llm\io_processing\generation_config_builder.hpp"
    $buildPath = Join-Path $SourceRoot "src\llm\BUILD"
    $parserPath = Join-Path $SourceRoot "src\llm\io_processing\gemma4\gemma4_tool_parser.cpp"

    $factoryText = [System.IO.File]::ReadAllText($factoryPath)
    if (-not $factoryText.Contains('#include "gemma4/generation_config_builder.hpp"') -or
        -not $factoryText.Contains('toolParserName == "gemma4"')) {
        throw "Gemma4 GenerationConfigBuilder exists but is not wired into the OVMS factory. Re-apply the backport from a clean pinned baseline."
    }

    $buildText = [System.IO.File]::ReadAllText($buildPath)
    if (-not $buildText.Contains('io_processing/gemma4/generation_config_builder.cpp') -or
        -not $buildText.Contains('io_processing/gemma4/generation_config_builder.hpp')) {
        throw "Gemma4 GenerationConfigBuilder exists but is missing from src/llm/BUILD. Re-apply the backport from a clean pinned baseline."
    }

    $parserText = [System.IO.File]::ReadAllText($parserPath)
    if (-not $parserText.Contains('guidedArgsDoc') -or
        -not $parserText.Contains('guidedArgsDoc.IsObject()')) {
        throw "Gemma4 parser lacks guided JSON argument compatibility. Refusing to build a hard-choice generator that its parser cannot consume."
    }

    Write-Host "Verified Gemma4 guidance integration before build: builder + factory + BUILD + dual-dialect parser."
}

$ModelServerPath = (Resolve-Path $ModelServerPath).Path

if (-not $SkipApply) {
    & (Join-Path $PSScriptRoot "apply-backport.ps1") -ModelServerPath $ModelServerPath
}
Assert-Gemma4GuidanceIntegrated -SourceRoot $ModelServerPath

$vs = Resolve-VisualStudioBuildTools -RequestedPath $VisualStudioPath
Write-Host "Using Visual Studio 2022 Build Tools:"
Write-Host "  $($vs.Path)"
Write-Host "Using MSVC compiler:"
Write-Host "  $($vs.ClExe)"
Write-Host "Using MSVC toolset version:"
Write-Host "  $($vs.MsvcVersion)"

$batchBackups = $null
Push-Location $ModelServerPath
try {
    # OVMS 2026.4 RC1 hardcodes Build Tools under Program Files (x86) and a
    # specific MSVC toolset version. Temporarily rewrite those pinned values so
    # installations under either Program Files root work, then restore the exact
    # original bytes after build/package completes or fails.
    $batchBackups = Set-OvmsVisualStudioPath `
        -SourceRoot $ModelServerPath `
        -VsPath $vs.Path `
        -MsvcVersion $vs.MsvcVersion

    if ($InstallDependencies) {
        Invoke-NativeProcess `
            -FilePath ".\windows_install_build_dependencies.bat" `
            -ArgumentList @($DependenciesRoot) `
            -FailureMessage "windows_install_build_dependencies.bat failed."
    }

    Initialize-OvmsPythonEnvironment

    # JINJA mode requires the Python-enabled OVMS build. Build tests too so the
    # upstream Gemma4 suite plus our guided-JSON regression can run before packaging.
    Invoke-NativeProcess `
        -FilePath ".\windows_build.bat" `
        -ArgumentList @($DependenciesRoot, "--with_python", "--with_tests") `
        -FailureMessage "windows_build.bat failed."
    Assert-WindowsBuildSucceeded -SourceRoot $ModelServerPath

    if (-not $SkipParserTests) {
        $LlmModels = Join-Path $ModelServerPath "src\test\llm_testing"
        Invoke-NativeProcess `
            -FilePath ".\windows_prepare_llm_models.bat" `
            -ArgumentList @($LlmModels) `
            -FailureMessage "windows_prepare_llm_models.bat failed."

        Invoke-NativeProcess `
            -FilePath "python" `
            -ArgumentList @(".\windows_change_test_configs.py") `
            -FailureMessage "windows_change_test_configs.py failed."

        Invoke-NativeProcess `
            -FilePath ".\bazel-bin\src\ovms_test.exe" `
            -ArgumentList @("--gtest_filter=Gemma4OutputParserTest.*") `
            -FailureMessage "Gemma4OutputParserTest regression suite failed."
    }

    $OvmsExe = Join-Path $ModelServerPath "bazel-bin\src\ovms.exe"
    if (-not (Test-Path $OvmsExe)) {
        throw "Build returned success but ovms.exe was not found at $OvmsExe"
    }

    # Package the matching EXE + OpenVINO/GenAI/tokenizer DLLs + self-contained Python.
    # Deploying only ovms.exe over an older unpacked directory can create ABI/runtime skew.
    Invoke-NativeProcess `
        -FilePath ".\windows_create_package.bat" `
        -ArgumentList @($DependenciesRoot, "--with_python") `
        -FailureMessage "windows_create_package.bat failed."

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

        Invoke-NativeProcess `
            -FilePath $DeployedExe `
            -ArgumentList @("--version") `
            -FailureMessage "Deployed ovms.exe failed --version sanity check."

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
