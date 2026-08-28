$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
if (-not $env:SPIRIT_DATA_DIR) { $env:SPIRIT_DATA_DIR = "C:\SpiritJeronion\.spirit-data" }
python -m spirit_worker
