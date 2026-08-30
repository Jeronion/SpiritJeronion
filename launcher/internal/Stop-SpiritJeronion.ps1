$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$ports = @(4173, 5678, 8900, 8910)
$ids = @()
foreach ($port in $ports) {
    $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($connection in $connections) { $ids += $connection.OwningProcess }
}
$cloudflared = Join-Path $projectRoot "launcher\bin\cloudflared.exe"
if (Test-Path -LiteralPath $cloudflared) {
    $resolved = (Resolve-Path -LiteralPath $cloudflared).Path
    Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "cloudflared.exe" -and $_.ExecutablePath -eq $resolved } | ForEach-Object { $ids += $_.ProcessId }
}
foreach ($id in ($ids | Sort-Object -Unique)) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
Write-Host "SpiritJeronion остановлен."
