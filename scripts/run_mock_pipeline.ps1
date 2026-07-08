$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -Path $RepoRoot

$env:PYTHONPATH = Join-Path $RepoRoot "src"
python -m sensoragent.services.cli.main mock-pick-place --config configs\mock.yaml @args
