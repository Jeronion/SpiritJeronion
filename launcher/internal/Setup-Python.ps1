$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$venv = Join-Path $projectRoot ".venv"
$requirements = Join-Path $projectRoot "requirements.txt"

if (-not (Test-Path -LiteralPath $venv)) { python -m venv $venv }
$python = Join-Path $venv "Scripts\python.exe"
function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python command failed: $($Arguments -join ' ')" }
}
Invoke-Python -m pip install --upgrade pip

# ChatGPTAutomation pins pywin32 306, which has no Python 3.14 wheel.
# Install the complete top-level manifest without stale transitive pins,
# then resolve every supported dependency explicitly.
Invoke-Python -m pip install --no-deps -r $requirements
Invoke-Python -m pip install schoolmospy==0.2.5 "pypdf>=5.0,<7"
Invoke-Python -m pip install python-dotenv==1.0.0 "pywin32>=311" "pyzmq>=27,<28" requests==2.31.0 selenium==4.9.0 webdriver-manager==4.0.1 pyperclip==1.9.0 PyAutoIt==0.6.5
Invoke-Python -c "from schoolmospy import StudentClient; from chatgpt_automation.chatgpt_automation import ChatGPTAutomation; from pypdf import PdfReader; print('Python services are ready')"
