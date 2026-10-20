# One-click start for Traid (used by "Start Traid.cmd" and the Desktop shortcut).
# First run: installs everything (scripts\setup.ps1). Every run: rebuilds the user
# interface if the code changed since the last build, then starts Traid and opens the
# browser. Keeps the window open on errors so they can be read.
. "$PSScriptRoot\common.ps1"

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
    Write-Host 'Details are in data\logs. Press Enter to close this window.'
    Read-Host | Out-Null
    exit 1
}
