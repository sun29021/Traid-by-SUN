# Start the backend (http://127.0.0.1:8765, auto-reload) and the Vite dev server
# (http://localhost:5173, proxies /api). Press Ctrl+C to stop both.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
. "$PSScriptRoot\common.ps1"
Assert-BackendEnv
Assert-FrontendDeps

$env:TRAID_ENV = 'development'

Write-Host '==> Starting backend on http://127.0.0.1:8765'
$backend = Start-Process -FilePath $BackendPython -ArgumentList '-m', 'app' `
    -WorkingDirectory $BackendDir -NoNewWindow -PassThru

try {
    Write-Host '==> Starting frontend on http://localhost:5173'
    Push-Location $FrontendDir
    npm run dev
} finally {
    Pop-Location
    if ($backend -and -not $backend.HasExited) {
        Write-Host '==> Stopping backend'
        # The backend runs a reloader with a child process; stop the whole tree.
        & taskkill /PID $backend.Id /T /F | Out-Null
    }
}
