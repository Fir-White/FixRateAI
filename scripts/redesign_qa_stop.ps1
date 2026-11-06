$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskStatePath = Join-Path $taskRoot 'var/redesign-v2/qa-state.json'
$taskState = Get-Content -Raw -Encoding UTF8 -LiteralPath $taskStatePath | ConvertFrom-Json
if ($taskState.baseUrl -ne 'http://127.0.0.1:18074' -or $taskState.api -ne 'fixrate-redesign-qa-api' -or $taskState.database -ne 'fixrate-redesign-qa-db' -or $taskState.network -ne 'fixrate-redesign-qa') {
  throw 'Refusing to stop an unrecognized QA environment'
}
docker rm -f fixrate-redesign-qa-api fixrate-redesign-qa-db | Out-Null
if ($LASTEXITCODE) { throw 'QA containers were not removed; state retained' }
docker network rm fixrate-redesign-qa-browser fixrate-redesign-qa | Out-Null
if ($LASTEXITCODE) { throw 'QA networks were not removed; state retained' }
Remove-Item -LiteralPath $taskStatePath
Write-Output 'Disposable redesign QA containers, networks and credential state removed.'
