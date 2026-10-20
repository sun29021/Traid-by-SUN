# Shared helpers for Traid scripts. Dot-source it: . "$PSScriptRoot\common.ps1"
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$BackendPython = Join-Path $BackendDir '.venv\Scripts\python.exe'

# Run uv whether it is on PATH or only installed as a Python module.
function Invoke-Uv {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$UvArgs)
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv @UvArgs
    } else {
        & python -m uv @UvArgs
    }
    if ($LASTEXITCODE -ne 0) { throw "uv $($UvArgs -join ' ') failed with exit code $LASTEXITCODE" }
}

function Assert-BackendEnv {
    if (-not (Test-Path $BackendPython)) {
        throw "Backend environment missing. Run scripts\setup.ps1 first."
    }
}

function Assert-FrontendDeps {
    if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
        throw "Frontend dependencies missing. Run scripts\setup.ps1 first."
    }
}
