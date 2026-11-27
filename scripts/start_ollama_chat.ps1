param([string]$Model = 'qwen3.5:4b-q4_K_M', [switch]$SkipPull)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
$taskState = Join-Path $taskRoot 'var/ollama-chat'
New-Item -ItemType Directory -Path $taskState -Force | Out-Null
$taskCommand = Get-Command ollama -ErrorAction SilentlyContinue
$taskBinary = if ($taskCommand) { $taskCommand.Source } else { Join-Path $env:LOCALAPPDATA 'Programs/Ollama/ollama.exe' }
if (-not (Test-Path -LiteralPath $taskBinary)) { throw 'Install Ollama for Windows first: https://ollama.com/download/windows' }
if ($Model -notmatch '^[A-Za-z0-9._/-]+:[A-Za-z0-9._-]+$' -or $Model -match 'cloud') { throw 'Select an explicit local model tag.' }
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MODELS = Join-Path $taskRoot 'var/ollama-models'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_CONTEXT_LENGTH = '32768'
$env:OLLAMA_FLASH_ATTENTION = '1'
$env:OLLAMA_KV_CACHE_TYPE = 'q8_0'
try { $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 2 }
catch {
    $taskProcess = Start-Process -FilePath $taskBinary -ArgumentList 'serve' -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $taskState 'server.stdout.log') -RedirectStandardError (Join-Path $taskState 'server.stderr.log')
    $taskProcess.Id | Set-Content -LiteralPath (Join-Path $taskState 'server.pid')
    $taskReady = $false
    for ($taskAttempt=0; $taskAttempt -lt 60; $taskAttempt++) {
        try { $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 2; $taskReady=$true; break }
        catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $taskReady) { throw 'Ollama did not become ready; inspect var/ollama-chat/server.stderr.log.' }
}
$taskModels = (Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 10).models
$taskFound = $taskModels | Where-Object { $_.name -eq $Model } | Select-Object -First 1
if (-not $taskFound) {
    if ($SkipPull) { throw 'The model is not downloaded. Run without -SkipPull to prepare it.' }
    & $taskBinary pull $Model
    if ($LASTEXITCODE -ne 0) { throw 'Ollama model download failed.' }
    $taskFound = (Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 10).models | Where-Object { $_.name -eq $Model } | Select-Object -First 1
}
if (-not $taskFound -or $taskFound.remote_host -or $taskFound.remote_model) { throw 'Expected a downloaded local model.' }
$taskDigest = 'sha256:' + ($taskFound.digest -replace '^sha256:', '')
if ($taskDigest -notmatch '^sha256:[0-9a-f]{64}$') { throw 'Invalid model digest.' }
$taskInfo = @{model=$taskFound.name;digest=$taskDigest;size=$taskFound.size;base_url='http://127.0.0.1:11434';docker_url='http://host.docker.internal:11434';context=32768;cloud_fallback=$false}
$taskInfo | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskState 'model.json') -Encoding UTF8
Write-Output "Ready: $($taskFound.name), $taskDigest"
Write-Output 'Configuration: var/ollama-chat/model.json. Model cache: var/ollama-models.'
