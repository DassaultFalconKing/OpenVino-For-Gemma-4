[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ModelServerPath,

    [string]$UpstreamUrl = "https://github.com/openvinotoolkit/model_server.git"
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$BaseCommit = "530dc63f816507d18bc14629e8cffeb55e3985e6"
$Commits = @(
    "503ff866278e9236d08bc9b6ddd18ec879660f72",
    "95628b45a082bd3d9562a3ad2f3d0762d5883ca4"
)

$ModelServerPath = (Resolve-Path $ModelServerPath).Path
if (-not (Test-Path (Join-Path $ModelServerPath ".git"))) {
    throw "ModelServerPath must point to an OVMS source checkout, not to an unpacked binary distribution: $ModelServerPath"
}

Push-Location $ModelServerPath
try {
    $status = git status --porcelain
    if ($LASTEXITCODE -ne 0) { throw "git status failed" }
    if ($status) { throw "Refusing to patch a dirty model_server source worktree." }

    $head = (git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw "git rev-parse HEAD failed" }
    if ($head -ne $BaseCommit) {
        throw "Wrong model_server source base. Expected $BaseCommit, found $head. Checkout the exact RC1 source baseline first."
    }

    Write-Host "Fetching upstream objects only. No remote or commit will be created in your checkout."
    git fetch --no-tags $UpstreamUrl main
    if ($LASTEXITCODE -ne 0) { throw "Failed to fetch upstream model_server main." }

    foreach ($commit in $Commits) {
        git cat-file -e "$commit^{commit}"
        if ($LASTEXITCODE -ne 0) { throw "Upstream commit $commit was not fetched." }
    }

    try {
        Write-Host "Applying Gemma4 parser fixes to the local worktree without creating Git commits:"
        foreach ($commit in $Commits) {
            Write-Host "  $commit"
        }

        git cherry-pick --no-commit @Commits
        if ($LASTEXITCODE -ne 0) {
            throw "git cherry-pick --no-commit failed"
        }

        # Leave a normal locally-patched worktree rather than staged changes.
        git reset --mixed HEAD
        if ($LASTEXITCODE -ne 0) { throw "Failed to unstage locally applied backport." }
    } catch {
        git cherry-pick --abort 2>$null
        git reset --hard $BaseCommit | Out-Null
        throw "Backport application failed. The source worktree was restored to $BaseCommit. Details: $($_.Exception.Message)"
    }

    $patched = git status --short
    if ($LASTEXITCODE -ne 0) { throw "git status failed after backport application" }
    if (-not $patched) { throw "Backport produced no local source changes; refusing to report success." }

    Write-Host "Gemma4 OVMS parser backport applied locally."
    Write-Host "  source base: $BaseCommit"
    Write-Host "  Git commits created: none"
    Write-Host "  local modified files:"
    $patched | ForEach-Object { Write-Host "    $_" }
} finally {
    Pop-Location
}
