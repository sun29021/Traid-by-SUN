# Run Traid for everyday use: production mode, one process serving the UI and API on
# http://127.0.0.1:8765 (this computer only). Builds the UI the first time, or when
# -Build is given. A backup is taken automatically before any database upgrade.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\start.ps1 [-Build] [-NoBrowser]
param([switch]$Build, [switch]$NoBrowser)
. "$PSScriptRoot\common.ps1"
Assert-BackendEnv

$dist = Join-Path $FrontendDir 'dist\index.html'
if ($Build -or -not (Test-Path $dist)) {
    Assert-FrontendDeps
    Write-Host '==> Building the user interface'
    Push-Location $FrontendDir
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    } finally {
        Pop-Location
    }
}

$env:TRAID_ENV = 'production'
$port = if ($env:TRAID_PORT) { $env:TRAID_PORT } else { '8765' }
$url = "http://127.0.0.1:$port"
Write-Host "==> Starting Traid on $url (Ctrl+C to stop)"
$server = Start-Process -FilePath $BackendPython -ArgumentList '-m', 'app' `
    -WorkingDirectory $BackendDir -NoNewWindow -PassThru

try {
    if (-not $NoBrowser) {
        # Open the browser once the server answers (up to 60 s: first start may migrate).
        for ($i = 0; $i -lt 120; $i++) {
            if ($server.HasExited) { throw "Traid stopped during startup (exit code $($server.ExitCode)). See data\logs." }
            try {
                Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "$url/api/v1/health" | Out-Null
                Start-Process $url
                break
            } catch {
                Start-Sleep -Milliseconds 500
            }
        }
    }
    Wait-Process -Id $server.Id
} finally {
    if ($server -and -not $server.HasExited) {
        & taskkill /PID $server.Id /T /F | Out-Null
    }
}
