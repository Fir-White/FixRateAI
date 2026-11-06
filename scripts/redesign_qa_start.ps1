$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskState = Join-Path $taskRoot 'var/redesign-v2/qa-state.json'
if (Test-Path -LiteralPath $taskState) { throw 'QA state already exists. Reuse the isolated environment; do not overwrite it.' }
$taskNetwork = 'fixrate-redesign-qa'
$taskBrowserNetwork = 'fixrate-redesign-qa-browser'
$taskDb = 'fixrate-redesign-qa-db'
$taskApi = 'fixrate-redesign-qa-api'
$taskPassword = 'Redesign-' + [guid]::NewGuid().ToString('N')
$env:FIXRATE_TEST_PASSWORD = $taskPassword
docker network create --internal $taskNetwork | Out-Null
if ($LASTEXITCODE) { throw 'Cannot create QA network' }
docker run -d --name $taskDb --network $taskNetwork --tmpfs /var/lib/postgresql -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=fixrate_redesign_qa postgres:18 | Out-Null
if ($LASTEXITCODE) { throw 'Cannot start QA database' }
for ($taskAttempt=0; $taskAttempt -lt 30; $taskAttempt++) {
  docker exec $taskDb pg_isready -U postgres -d fixrate_redesign_qa 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { break }
  Start-Sleep -Seconds 1
}
docker run -d --name $taskApi --network $taskNetwork -p 127.0.0.1:18074:8000 --mount "type=bind,source=$taskRoot,target=/src,readonly" -w /src -e PYTHONPATH=/src/backend:/src -e DATABASE_URL=postgresql+psycopg://postgres@fixrate-redesign-qa-db:5432/fixrate_redesign_qa -e FIXRATE_TEST_PASSWORD -e PHOTO_STORAGE_ROOT=/tmp/redesign-photos -e COOKIE_SECURE=false -e MAINTENANCE_SCHEDULER=false -e PHOTO_REVIEW_PROVIDER=clip -e FORECAST_PROVIDER=rf -e AITUNNEL_API_KEY= -e AI_TUNNEL_API_KEY= --entrypoint python fixrate-ai:notice-copy scripts/redesign_qa_api.py | Out-Null
if ($LASTEXITCODE) { throw 'Cannot start QA API' }
# Docker does not publish ports on an internal-only network. Only the API joins
# this second bridge; the database remains exclusively on the internal network.
docker network create $taskBrowserNetwork | Out-Null
if ($LASTEXITCODE) { throw 'Cannot create QA browser network' }
docker network connect $taskBrowserNetwork $taskApi
if ($LASTEXITCODE) { throw 'Cannot expose QA API to the browser' }
New-Item -ItemType Directory -Force (Split-Path -Parent $taskState) | Out-Null
@{ baseUrl='http://127.0.0.1:18074'; password=$taskPassword; network=$taskNetwork; browserNetwork=$taskBrowserNetwork; database=$taskDb; api=$taskApi } | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath $taskState
Remove-Item Env:FIXRATE_TEST_PASSWORD
Write-Output 'Isolated QA API starting at http://127.0.0.1:18074; credentials stored only in ignored var/redesign-v2/qa-state.json'
