[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ModelServerPath,

    [string]$UpstreamUrl = "https://github.com/openvinotoolkit/model_server.git",
    [string]$RemoteName = "gemma4-backport-upstream"
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
    throw "Not a git checkout: $ModelServerPath"
}

Push-Location $ModelServerPath
try {
    $status = git status --porcelain
    if ($LASTEXITCODE -ne 0) { throw "git status failed" }
    if ($status) { throw "Refusing to patch a dirty model_server worktree." }

    $head = (git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw "git rev-parse HEAD failed" }
    if ($head -ne $BaseCommit) {
        throw "Wrong model_server base. Expected $BaseCommit, found $head. Checkout the exact RC1 base before applying this backport."
    }

    $existingRemote = git remote get-url $RemoteName 2>$null
    if ($LASTEXITCODE -eq 0) {
        if ($existingRemote.Trim() -ne $UpstreamUrl) {
            throw "Remote '$RemoteName' exists but points to '$($existingRemote.Trim())', expected '$UpstreamUrl'."
        }
    } else {
        git remote add $RemoteName $UpstreamUrl
        if ($LASTEXITCODE -ne 0) { throw "Failed to add upstream remote '$RemoteName'." }
    }

    git fetch --no-tags $RemoteName main
    if ($LASTEXITCODE -ne 0) { throw "Failed to fetch upstream model_server main." }

    foreach ($commit in $Commits) {
        git cat-file -e "$commit^{commit}"
        if ($LASTEXITCODE -ne 0) { throw "Upstream commit $commit was not fetched." }
    }

    foreach ($commit in $Commits) {
        Write-Host "Cherry-picking upstream fix $commit"
        git cherry-pick $commit
        if ($LASTEXITCODE -ne 0) {
            git cherry-pick --abort 2>$null
            throw "Cherry-pick failed for $commit. Backport aborted and worktree restored."
        }
    }

    $patchedHead = (git rev-parse HEAD).Trim()
    Write-Host "Gemma4 OVMS parser backport applied."
    Write-Host "  base:    $BaseCommit"
    Write-Host "  patched: $patchedHead"
} finally {
    Pop-Location
}
