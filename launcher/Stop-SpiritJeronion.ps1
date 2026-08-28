[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$statusPath = Join-Path $projectRoot '.spirit-data\launcher-status.json'
if (-not (Test-Path -LiteralPath $statusPath)) {
    Write-Host 'SpiritJeronion launcher status was not found.'
    exit 0
}

$status = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
foreach ($name in @('cloudflared', 'n8n', 'worker')) {
    $entry = $status.$name
    if (-not $entry -or -not $entry.pid) { continue }
    $process = Get-Process -Id ([int]$entry.pid) -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    Write-Host "Stopping $name..."
    & taskkill.exe /PID ([int]$entry.pid) /T /F | Out-Null
}
Remove-Item -LiteralPath $statusPath -Force -ErrorAction SilentlyContinue
Write-Host 'SpiritJeronion stopped.' -ForegroundColor Green

