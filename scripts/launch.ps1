# One-click start for Traid (used by "Start Traid.cmd" and the Desktop shortcut).
# First run: installs everything (scripts\setup.ps1). Every run: checks that the Python
# environment really works (and repairs it if not), rebuilds the user interface if the
# code changed, then starts Traid and opens the browser. Everything shown in the window
# is also written to data\logs\launcher.log. On errors the window stays open.
. "$PSScriptRoot\common.ps1"

$logDir = Join-Path $RepoRoot 'data\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
Start-Transcript -Path (Join-Path $logDir 'launcher.log') -Force | Out-Null

function Test-BackendPython {
    if (-not (Test-Path $BackendPython)) { return $false }
    Push-Location $BackendDir
    try {
        & $BackendPython -c 'import app, fastapi, cv2, onnxruntime' 2>&1 | Write-Host
        return $LASTEXITCODE -eq 0
    } catch {
        Write-Host $_.Exception.Message
        return $false
    } finally {
        Pop-Location
    }
}

try {
    $models = (Get-Content -Raw (Join-Path $RepoRoot 'models\manifest.json') | ConvertFrom-Json).models
    $missingModel = $models | Where-Object { $_.required -and -not (Test-Path (Join-Path $RepoRoot "models\$($_.file)")) }
    $needsSetup = -not (Test-Path $BackendPython) -or
        -not (Test-Path (Join-Path $FrontendDir 'node_modules')) -or
        $missingModel
    if ($needsSetup) {
        Write-Host '==> First start: installing Traid (this takes a few minutes, once)'
        & (Join-Path $PSScriptRoot 'setup.ps1')
    }

    if (-not (Test-BackendPython)) {
        Write-Host '==> The Python environment does not start; repairing it (about a minute)'
        Push-Location $BackendDir
        try {
            Invoke-Uv python install 3.11
            Remove-Item -Recurse -Force (Join-Path $BackendDir '.venv') -ErrorAction SilentlyContinue
            Invoke-Uv sync --frozen
        } finally {
            Pop-Location
        }
        if (-not (Test-BackendPython)) { throw 'The Python environment is still broken after repair' }
    }

    # Rebuild the UI when any frontend source is newer than the last build.
    $dist = Join-Path $FrontendDir 'dist\index.html'
    $build = -not (Test-Path $dist)
    if (-not $build) {
        $built = (Get-Item $dist).LastWriteTime
        $sources = @('src', 'index.html', 'package.json', 'vite.config.ts') |
            ForEach-Object { Join-Path $FrontendDir $_ } | Where-Object { Test-Path $_ }
        $newer = Get-ChildItem -Recurse -File $sources | Where-Object { $_.LastWriteTime -gt $built } |
            Select-Object -First 1
        $build = [bool]$newer
    }

    if ($build) {
        & (Join-Path $PSScriptRoot 'start.ps1') -Build @args
    } else {
        & (Join-Path $PSScriptRoot 'start.ps1') @args
    }
} catch {
    Write-Host ''
    Write-Host "Traid could not start: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'The log is data\logs\launcher.log. Press Enter to close this window.'
    Stop-Transcript | Out-Null
    Read-Host | Out-Null
    exit 1
}
Stop-Transcript | Out-Null
