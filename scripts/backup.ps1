# Back up the database and stored files to data\backups\traid-YYYYMMDD-HHMMSS.zip.
# Safe while Traid is running (SQLite online backup). The integrity of the copied
# database is checked; the script fails if the check does not pass.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\backup.ps1
. "$PSScriptRoot\common.ps1"
Assert-BackendEnv

Push-Location $BackendDir
try {
    & $BackendPython -m app.backup_cli
    if ($LASTEXITCODE -ne 0) { throw 'Backup failed' }
} finally {
    Pop-Location
}
