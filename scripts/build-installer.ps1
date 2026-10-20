# Build the Windows installer: build\Traid-Setup-<version>.exe
# Steps: UI build -> desktop dependencies -> icon -> PyInstaller bundle -> NSIS installer.
# Needs NSIS (makensis.exe): winget install NSIS.NSIS
# Usage: powershell -ExecutionPolicy Bypass -File scripts\build-installer.ps1
. "$PSScriptRoot\common.ps1"
Assert-BackendEnv
Assert-FrontendDeps

$packaging = Join-Path $RepoRoot 'packaging'
$build = Join-Path $RepoRoot 'build'
$makensis = @(
    "${env:ProgramFiles(x86)}\NSIS\makensis.exe",
    "$env:ProgramFiles\NSIS\makensis.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $makensis) { throw 'NSIS not found. Install it with: winget install NSIS.NSIS' }

Write-Host '==> 1/5 Building the user interface'
Push-Location $FrontendDir
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally { Pop-Location }

Write-Host '==> 2/5 Desktop dependencies (pywebview, PyInstaller)'
Push-Location $BackendDir
try { Invoke-Uv sync --frozen --group desktop } finally { Pop-Location }

Write-Host '==> 3/5 Models present and verified'
& $BackendPython -I (Join-Path $PSScriptRoot 'fetch_models.py')
if ($LASTEXITCODE -ne 0) { throw 'Model check failed' }
& $BackendPython (Join-Path $packaging 'make_icon.py')

Write-Host '==> 4/5 Bundling Traid (PyInstaller)'
Push-Location $BackendDir
try {
    & $BackendPython -m PyInstaller (Join-Path $packaging 'traid.spec') --noconfirm --clean `
        --distpath (Join-Path $build 'dist') --workpath (Join-Path $build 'work')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
} finally { Pop-Location }

Write-Host '==> 5/5 Creating the installer (NSIS)'
Push-Location $packaging
try {
    & $makensis -V2 installer.nsi
    if ($LASTEXITCODE -ne 0) { throw 'makensis failed' }
} finally { Pop-Location }

$setup = Get-ChildItem (Join-Path $build 'Traid-Setup-*.exe') | Sort-Object LastWriteTime | Select-Object -Last 1
Write-Host ("==> Done: {0} ({1:N0} MB)" -f $setup.FullName, ($setup.Length / 1MB))
