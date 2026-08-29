$ErrorActionPreference = "Stop"
$venv = Join-Path $PSScriptRoot ".venv"
if (-not (Test-Path -LiteralPath $venv)) { python -m venv $venv }
$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install --upgrade pip
# Upstream pins pywin32 306, which has no Python 3.14 wheel. Install the
# package without its stale pins, then install equivalent compatible deps.
& $python -m pip install ChatGPTAutomation==0.7.3 --no-deps
& $python -m pip install python-dotenv "pywin32>=311" pyzmq requests selenium==4.9.0 webdriver-manager pyperclip PyAutoIt
& $python -c "from chatgpt_automation.chatgpt_automation import ChatGPTAutomation; print('ChatGPTAutomation import OK')"
