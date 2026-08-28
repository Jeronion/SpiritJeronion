[CmdletBinding()]
param()

$task = Get-ScheduledTask -TaskName 'SpiritJeronion' -ErrorAction SilentlyContinue
if ($task) {
    Unregister-ScheduledTask -TaskName 'SpiritJeronion' -Confirm:$false
    Write-Host 'SpiritJeronion autostart removed.' -ForegroundColor Green
} else {
    Write-Host 'SpiritJeronion autostart is not installed.'
}

