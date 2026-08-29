param([switch]$NoBrowser)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$cacheDir = Join-Path $projectRoot ".cache\launcher"
$logDir = Join-Path $cacheDir "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

function Import-KeyStore {
    $envFile = Join-Path $projectRoot ".env"
    if (-not (Test-Path -LiteralPath $envFile)) { throw "Не найден $envFile" }
    foreach ($rawLine in Get-Content -LiteralPath $envFile) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { continue }
        $parts = $line.Split("=", 2)
        [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
    }
    foreach ($required in @("SPIRIT_QUEUE_SECRET", "GROQ_API_KEY", "TELEGRAM_BOT_TOKEN")) {
        if (-not [Environment]::GetEnvironmentVariable($required, "Process")) { throw "В .env отсутствует $required" }
    }
}

function Test-Port([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Wait-Port([string]$Name, [int]$Port, [int]$Seconds = 90) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Port $Port) { return }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name не запустился на порту $Port. Проверь .cache\launcher\logs."
}

function Start-ScriptService([string]$Name, [int]$Port, [string]$ScriptPath) {
    if (Test-Port $Port) { Write-Host "$Name уже работает."; return }
    $stdout = Join-Path $logDir "$Name.out.log"
    $stderr = Join-Path $logDir "$Name.err.log"
    Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $ScriptPath) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr | Out-Null
    Wait-Port $Name $Port
    Write-Host "$Name запущен."
}

function Ensure-Cloudflared {
    $directory = Join-Path $projectRoot "MCPtools\cloudflare"
    $binary = Join-Path $directory "cloudflared.exe"
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $valid = $false
    if (Test-Path -LiteralPath $binary) {
        try { & $binary --version *> $null; $valid = $LASTEXITCODE -eq 0 } catch { $valid = $false }
    }
    if (-not $valid) {
        Write-Host "Скачиваю официальный cloudflared..."
        Invoke-WebRequest -UseBasicParsing "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $binary
        & $binary --version *> $null
        if ($LASTEXITCODE -ne 0) { throw "Не удалось установить cloudflared" }
    }
    return $binary
}

function Start-QuickTunnel([string]$Binary) {
    $resolvedBinary = (Resolve-Path -LiteralPath $Binary).Path
    Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "cloudflared.exe" -and $_.ExecutablePath -eq $resolvedBinary } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    $runId = Get-Date -Format "yyyyMMdd-HHmmss-fff"
    $log = Join-Path $logDir "cloudflared-$runId.log"
    $stdout = Join-Path $logDir "cloudflared-$runId.out.log"
    $stderr = Join-Path $logDir "cloudflared-$runId.err.log"
    Start-Process -FilePath $resolvedBinary -ArgumentList @("tunnel", "--url", "http://127.0.0.1:5678", "--no-autoupdate", "--loglevel", "info", "--logfile", $log) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr | Out-Null
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $text = (@($log, $stdout, $stderr) | Where-Object { Test-Path -LiteralPath $_ } | ForEach-Object { Get-Content -Raw -LiteralPath $_ -ErrorAction SilentlyContinue }) -join "`n"
        $match = [regex]::Match($text, "https://[a-z0-9-]+\.trycloudflare\.com", "IgnoreCase")
        if ($match.Success) {
            $url = $match.Value.TrimEnd("/")
            @{ url = $url; created_at = (Get-Date).ToString("o") } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $cacheDir "current-tunnel.json") -Encoding UTF8
            return $url
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Cloudflare Tunnel не выдал URL. Проверь $log"
}

function New-BootstrapUrl([string]$TunnelUrl) {
    $config = @{ url = $TunnelUrl; secret = $env:SPIRIT_QUEUE_SECRET } | ConvertTo-Json -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($config)
    $encoded = [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
    return "https://jeronion.github.io/SpiritJeronion/#setup=$encoded"
}

Import-KeyStore
$sharedPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $sharedPython)) {
    Write-Host "Настраиваю единое Python-окружение..."
    & (Join-Path $PSScriptRoot "Setup-Python.ps1")
}
Start-ScriptService "n8n" 5678 (Join-Path $PSScriptRoot "Start-n8n.ps1")
Start-ScriptService "mesh" 8900 (Join-Path $PSScriptRoot "Start-Mesh.ps1")
Start-ScriptService "content-worker" 8910 (Join-Path $PSScriptRoot "Start-ContentWorker.ps1")

if (-not (Test-Port 4173)) {
    $python = (Get-Command python.exe -ErrorAction Stop).Source
    Start-Process -FilePath $python -ArgumentList @("-m", "http.server", "4173", "--bind", "127.0.0.1", "--directory", (Join-Path $projectRoot "WebsiteHosting")) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "website.out.log") -RedirectStandardError (Join-Path $logDir "website.err.log") | Out-Null
    Wait-Port "website" 4173 30
}

$cloudflared = Ensure-Cloudflared
$tunnelUrl = Start-QuickTunnel $cloudflared
$bootstrapUrl = New-BootstrapUrl $tunnelUrl

Write-Host ""
Write-Host "SpiritJeronion запущен."
Write-Host "Сайт: https://jeronion.github.io/SpiritJeronion/"
Write-Host "n8n:  http://127.0.0.1:5678"
Write-Host "Cloudflare: $tunnelUrl"

if (-not $NoBrowser) { Start-Process $bootstrapUrl }
