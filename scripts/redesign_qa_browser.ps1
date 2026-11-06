param([string[]] $Tests = @(), [switch] $Mobile)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskState = Get-Content -Raw -Encoding UTF8 (Join-Path $taskRoot 'var/redesign-v2/qa-state.json') | ConvertFrom-Json
if ($taskState.baseUrl -ne 'http://127.0.0.1:18074' -or $taskState.database -ne 'fixrate-redesign-qa-db') { throw 'Refusing non-QA destination' }
$taskReady = $false
for ($taskAttempt=0; $taskAttempt -lt 120; $taskAttempt++) {
  try {
    $taskHealth = Invoke-RestMethod ($taskState.baseUrl + '/api/health') -TimeoutSec 1
    if ($taskHealth.status -eq 'ok' -and $taskHealth.database -eq 'ready') { $taskReady = $true; break }
  } catch { }
  Start-Sleep -Milliseconds 250
}
if (-not $taskReady) { throw 'Disposable QA API did not become ready' }
$env:FIXRATE_BASE_URL = $taskState.baseUrl
$env:FIXRATE_TEST_PASSWORD = $taskState.password
$env:FIXRATE_TEST_SOURCE = (git -C $taskRoot rev-parse HEAD).Trim()
$taskReportName = if ($Mobile) { 'e2e-mobile-final' } else { 'e2e-final' }
$taskReportPath = Join-Path $taskRoot "reports/redesign-v2/$taskReportName"
New-Item -ItemType Directory -Force -Path $taskReportPath | Out-Null
$env:FIXRATE_E2E_OUTPUT = $taskReportPath
Push-Location (Join-Path $taskRoot 'frontend')
try {
  if ($Mobile) {
    npm.cmd run test:e2e -- --config playwright.mobile.config.ts @Tests --output (Join-Path $taskReportPath 'playwright')
  } else {
    npm.cmd run test:e2e -- @Tests --output (Join-Path $taskReportPath 'playwright')
  }
  $taskExitCode = $LASTEXITCODE
} finally {
  Pop-Location
  Remove-Item Env:FIXRATE_TEST_PASSWORD
  Remove-Item Env:FIXRATE_BASE_URL
  Remove-Item Env:FIXRATE_E2E_OUTPUT
  Remove-Item Env:FIXRATE_TEST_SOURCE
}
exit $taskExitCode
