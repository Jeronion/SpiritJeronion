[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $projectRoot '.spirit-data'
$logsDir = Join-Path $runtimeDir 'logs'
$statusPath = Join-Path $runtimeDir 'launcher-status.json'
$configPath = Join-Path $runtimeDir 'launcher.json'
$siteUrl = 'https://jeronion.github.io/SpiritJeronion/'

New-Item -ItemType Directory -Force -Path $runtimeDir, $logsDir | Out-Null

$config = [ordered]@{
    n8nPort = 5678
    workerPort = 8899
    siteUrl = $siteUrl
    cloudflareTunnelToken = ''
}
if (Test-Path -LiteralPath $configPath) {
    $saved = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    foreach ($name in @('n8nPort', 'workerPort', 'siteUrl', 'cloudflareTunnelToken')) {
        if ($null -ne $saved.$name -and [string]$saved.$name -ne '') { $config[$name] = $saved.$name }
    }
} else {
    $config | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
}

function Test-Endpoint([string]$Url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch { return $false }
}

function Wait-Endpoint([string]$Name, [string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        if (Test-Endpoint $Url) { Write-Host "[OK] $Name" -ForegroundColor Green; return }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "$Name did not start in $Seconds seconds. Check $logsDir"
}

function Get-PortProcess([int]$Port) {
    $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $connection) { return $null }
    return [ordered]@{ pid = [int]$connection.OwningProcess; startedAt = (Get-Date).ToString('o'); adopted = $true }
}

function Start-LoggedProcess([string]$Name, [string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $stdout = Join-Path $logsDir "$Name-$stamp.out.log"
    $stderr = Join-Path $logsDir "$Name-$stamp.err.log"
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    return [ordered]@{ pid = $process.Id; startedAt = (Get-Date).ToString('o'); stdout = $stdout; stderr = $stderr }
}

$running = $null
if (Test-Path -LiteralPath $statusPath) {
    try { $running = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json } catch { $running = $null }
}

$state = [ordered]@{ startedAt = (Get-Date).ToString('o'); n8n = $null; worker = $null; cloudflared = $null; publicUrl = '' }

$workerHealth = "http://127.0.0.1:$($config.workerPort)/api/health"
if (Test-Endpoint $workerHealth) {
    Write-Host '[OK] AI Worker is already running' -ForegroundColor Green
    $state.worker = Get-PortProcess ([int]$config.workerPort)
} else {
    $python = (Get-Command python.exe -ErrorAction Stop).Source
    $env:PYTHONPATH = Join-Path $projectRoot 'ai-worker\src'
    $env:SPIRIT_DATA_DIR = $runtimeDir
    $env:SPIRIT_WORKER_PORT = [string]$config.workerPort
    $state.worker = Start-LoggedProcess 'worker' $python @('-m', 'spirit_worker') (Join-Path $projectRoot 'ai-worker')
    Wait-Endpoint 'AI Worker' $workerHealth 30
}

$n8nHealth = "http://127.0.0.1:$($config.n8nPort)/healthz"
if (Test-Endpoint $n8nHealth) {
    Write-Host '[OK] n8n is already running' -ForegroundColor Green
    $state.n8n = Get-PortProcess ([int]$config.n8nPort)
} else {
    $n8nCommand = (Get-Command n8n.cmd -ErrorAction Stop).Source
    $env:N8N_USER_FOLDER = $projectRoot
    $env:N8N_PORT = [string]$config.n8nPort
    $commandLine = '"' + $n8nCommand + '" start'
    $state.n8n = Start-LoggedProcess 'n8n' $env:ComSpec @('/d', '/s', '/c', $commandLine) $projectRoot
    Wait-Endpoint 'n8n' $n8nHealth 90
}

$cloudflared = Join-Path $projectRoot 'cloudflared.exe'
if (-not (Test-Path -LiteralPath $cloudflared)) { throw "cloudflared.exe not found: $cloudflared" }
$existingCloudflared = Get-Process -Name cloudflared -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existingCloudflared) {
    Write-Host '[OK] Cloudflare Tunnel is already running' -ForegroundColor Green
    $state.cloudflared = [ordered]@{ pid = $existingCloudflared.Id; startedAt = (Get-Date).ToString('o'); adopted = $true }
    if ($running) { $state.publicUrl = [string]$running.publicUrl }
} else {
    $cfLog = Join-Path $logsDir ('cloudflared-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
    if ([string]$config.cloudflareTunnelToken) {
        $arguments = @('tunnel', '--no-autoupdate', 'run', '--token', [string]$config.cloudflareTunnelToken)
    } else {
        $arguments = @('tunnel', '--url', "http://127.0.0.1:$($config.n8nPort)", '--no-autoupdate', '--logfile', $cfLog, '--loglevel', 'info')
    }
    $state.cloudflared = Start-LoggedProcess 'cloudflared' $cloudflared $arguments $projectRoot
    if (-not [string]$config.cloudflareTunnelToken) {
        $deadline = (Get-Date).AddSeconds(45)
        do {
            Start-Sleep -Milliseconds 500
            if (Test-Path -LiteralPath $cfLog) {
                $match = Select-String -LiteralPath $cfLog -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -AllMatches | Select-Object -Last 1
                if ($match) { $state.publicUrl = $match.Matches[0].Value; break }
            }
        } while ((Get-Date) -lt $deadline)
        if (-not $state.publicUrl) { throw "Cloudflare started, but no public URL was found. Check $cfLog" }
    }
    Write-Host '[OK] Cloudflare Tunnel' -ForegroundColor Green
}

$state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statusPath -Encoding UTF8
Write-Host ''
Write-Host 'SpiritJeronion is running.' -ForegroundColor Cyan
Write-Host "n8n:       http://127.0.0.1:$($config.n8nPort)"
Write-Host "AI Worker: http://127.0.0.1:$($config.workerPort)"
if ($state.publicUrl) {
    Write-Host "Public n8n: $($state.publicUrl)" -ForegroundColor Yellow
    try { Set-Clipboard -Value $state.publicUrl } catch {}
    Write-Host 'The public n8n URL has been copied to the clipboard.'
}
Write-Host "Logs:      $logsDir"

if (-not $NoBrowser) {
    $openUrl = [string]$config.siteUrl
    if ($state.publicUrl -and $state.publicUrl -match '^https://[a-z0-9-]+\.trycloudflare\.com$') {
        $separator = if ($openUrl.Contains('?')) { '&' } else { '?' }
        $openUrl += $separator + 'api=' + [Uri]::EscapeDataString([string]$state.publicUrl)
    }
    Start-Process $openUrl
}
