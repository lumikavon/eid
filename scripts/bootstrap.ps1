$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location (Split-Path $PSScriptRoot -Parent)
# 启动尝试一旦开始，旧运行清单不再代表本次启动成功；仅在最终公共就绪后重建。
Remove-Item -LiteralPath '.local/runtime-images.json' -Force -ErrorAction SilentlyContinue
$eidNode = Join-Path (Get-Location) '.local/tools/node-v24.20.0-win-x64'
if (Test-Path -LiteralPath $eidNode) { $env:PATH = "$eidNode;$env:PATH" }
function Invoke-Checked {
    param([string]$File, [string[]]$Arguments)
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$File failed with exit $LASTEXITCODE; bootstrap stopped" }
}
function Invoke-CapturedChecked {
    param([string]$File, [string[]]$Arguments)
    $output = & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$File failed with exit $LASTEXITCODE; bootstrap stopped" }
    return $output
}
if ($env:EID_MIGRATION_DATABASE_URL -and $env:EID_MIGRATION_DATABASE_URL -ne 'postgresql+psycopg://eid_migrator:local-migrate-only@localhost:55432/eid_local_dev') { throw '拒绝覆盖已配置的数据库目标' }
$env:EID_MIGRATION_DATABASE_URL = 'postgresql+psycopg://eid_migrator:local-migrate-only@localhost:55432/eid_local_dev'
Invoke-Checked uv @('run','--frozen','python','scripts/verify_local_environment.py','--prepare')
$eidOwner = Get-Content -LiteralPath '.local/ownership.json' -Raw | ConvertFrom-Json
$env:EID_OWNER_NONCE = $eidOwner.nonce
$eidSourceEvidence = Invoke-CapturedChecked uv @('run','--frozen','python','scripts/verify_local_environment.py','--source-fingerprints') | ConvertFrom-Json
$env:EID_API_SOURCE_FINGERPRINT = $eidSourceEvidence.source_fingerprints.api
$env:EID_WORKER_SOURCE_FINGERPRINT = $eidSourceEvidence.source_fingerprints.worker
$env:EID_WEB_SOURCE_FINGERPRINT = $eidSourceEvidence.source_fingerprints.web
Invoke-Checked docker @('compose','-f','deployment/compose.yaml','config','--quiet')
Invoke-Checked docker @('compose','-f','deployment/compose.yaml','up','-d','--wait','--wait-timeout','180','postgres','keycloak','rabbitmq','redis','seaweedfs')
Invoke-Checked uv @('run','--frozen','python','-m','scripts.initialize_local_storage')
Invoke-Checked uv @('run','--frozen','python','scripts/verify_local_environment.py')
Invoke-Checked uv @('run','--frozen','alembic','upgrade','head')
Invoke-Checked docker @('compose','-f','deployment/compose.yaml','up','-d','--build','--wait','--wait-timeout','180','api','worker','web','nginx')
Invoke-Checked docker @('compose','-f','deployment/compose.yaml','exec','-T','nginx','nginx','-t')
Invoke-Checked docker @('compose','-f','deployment/compose.yaml','exec','-T','nginx','nginx','-s','reload')
Invoke-Checked uv @('run','--frozen','python','-m','scripts.verify_rabbitmq_api_access')
Invoke-Checked uv @('run','--frozen','python','-m','scripts.verify_readiness')
Invoke-Checked uv @('run','--frozen','python','scripts/verify_local_environment.py','--record-runtime-images')
