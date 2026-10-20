# Run every quality gate (AGENTS.md §10). Exits non-zero on the first failure.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\check.ps1
. "$PSScriptRoot\common.ps1"
Assert-BackendEnv
Assert-FrontendDeps

function Invoke-Step {
    param([string]$Name, [scriptblock]$Command)
    Write-Host "==> $Name"
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit code $LASTEXITCODE)" }
}

Push-Location $BackendDir
try {
    Invoke-Step 'backend: ruff check' { & $BackendPython -m ruff check . }
    Invoke-Step 'backend: ruff format --check' { & $BackendPython -m ruff format --check . }
    Invoke-Step 'backend: mypy' { & $BackendPython -m mypy }
    Invoke-Step 'backend: pytest' { & $BackendPython -m pytest -q }
} finally {
    Pop-Location
}

Push-Location $FrontendDir
try {
    Invoke-Step 'frontend: eslint' { npm run --silent lint }
    Invoke-Step 'frontend: prettier --check' { npm run --silent format:check }
    Invoke-Step 'frontend: tsc' { npm run --silent typecheck }
    Invoke-Step 'frontend: vitest' { npm run --silent test }
} finally {
    Pop-Location
}

Write-Host '==> All checks passed'
