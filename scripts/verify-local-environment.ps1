$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$eidNode = Join-Path (Get-Location) '.local/tools/node-v24.20.0-win-x64'
if (Test-Path -LiteralPath $eidNode) { $env:PATH = "$eidNode;$env:PATH" }
& uv run --frozen python scripts/verify_local_environment.py @args
$eidGuardExitCode = $LASTEXITCODE
if ($eidGuardExitCode -ne 0) { exit $eidGuardExitCode }
exit 0
