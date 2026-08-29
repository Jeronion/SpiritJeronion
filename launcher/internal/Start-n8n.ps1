$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$envFile = Join-Path $projectRoot ".env"
if (-not (Test-Path -LiteralPath $envFile)) { throw "Не найден $envFile" }
foreach ($rawLine in Get-Content -LiteralPath $envFile) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { continue }
    $parts = $line.Split("=", 2)
    [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
}
foreach ($required in @("GROQ_API_KEY", "SPIRIT_QUEUE_SECRET")) {
    if (-not [Environment]::GetEnvironmentVariable($required, "Process")) { throw "В .env отсутствует $required" }
}
$env:N8N_USER_FOLDER = $projectRoot
$env:N8N_BLOCK_ENV_ACCESS_IN_NODE = "false"
$n8n = Get-Command "n8n.cmd" -ErrorAction Stop
& $n8n.Source start
