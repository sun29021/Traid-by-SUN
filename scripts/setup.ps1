# Install all development dependencies (backend venv with Python 3.11 + frontend node_modules).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
. "$PSScriptRoot\common.ps1"

Write-Host '==> Backend: Python 3.11 + dependencies (uv)'
Push-Location $BackendDir
try {
    Invoke-Uv python install 3.11
    Invoke-Uv sync --frozen
} finally {
    Pop-Location
}

Write-Host '==> Frontend: dependencies (npm ci)'
Push-Location $FrontendDir
try {
    npm ci --no-fund --no-audit
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
} finally {
    Pop-Location
}

New-Item -ItemType Directory -Force (Join-Path $RepoRoot 'data') | Out-Null
Write-Host '==> Setup complete. Start development with: scripts\dev.ps1'
