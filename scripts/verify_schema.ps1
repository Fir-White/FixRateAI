# Disposable PostgreSQL: base 001-004, populated upgrade to 008, independent clean 001-008.
param(
    [string]$PgBin = 'C:\Program Files\PostgreSQL\18\bin',
    [int]$Port = 0,
    [string]$Database = 'fixrate_test_schema',
    [string]$LogPath = (Join-Path $PSScriptRoot "../logs/sql/$(Get-Date -Format 'yyyyMMdd-HHmmss')-$PID/run_schema_test.log")
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$LogPath = [IO.Path]::GetFullPath($LogPath)
if (Test-Path -LiteralPath $LogPath) { throw 'Log already exists; choose a new LogPath to preserve evidence' }
$schemaLogDirectory = Split-Path -Parent $LogPath
New-Item -ItemType Directory -Path $schemaLogDirectory -Force | Out-Null
$clusterName = "pgfixrate_schema_${PID}_$([guid]::NewGuid().ToString('N'))"
$dataDir = Join-Path $env:TEMP $clusterName
$serverOut = Join-Path $schemaLogDirectory "$clusterName.stdout.log"
$serverErr = Join-Path $schemaLogDirectory "$clusterName.stderr.log"
$migrations = @(Get-ChildItem -LiteralPath (Join-Path $repoRoot 'database/migrations') -Filter '*.sql' | Where-Object { $_.Name -match '^[0-9]+' } | Sort-Object Name)
$baseMigrations = @($migrations | Where-Object { $_.Name -match '^00[1-4]_' })
$upgradeMigrations = @($migrations | Where-Object { $_.Name -notmatch '^00[1-4]_' })
$ownsDataDir = $false
$server = $null
$fail = $false
$previousPgTimeout = $env:PGCONNECT_TIMEOUT
$previousPgEncoding = $env:PGCLIENTENCODING
$env:PGCONNECT_TIMEOUT = '5'
$env:PGCLIENTENCODING = 'UTF8'

function Write-Log([string]$line) {
    $line | Out-File -LiteralPath $LogPath -Append -Encoding utf8
}

function Invoke-LoggedCommand([string]$Name, [string]$Executable, [string[]]$Arguments) {
    Write-Log "=== $Name ==="
    # Windows PowerShell converts native stderr into ErrorRecord; retain diagnostics
    # and judge success by the real exit code, not the presence of stderr notices.
    $priorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $lines = @(& $Executable @Arguments 2>&1 | ForEach-Object { $_.ToString() })
        $code = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $priorPreference }
    foreach ($line in $lines) { Write-Log $line }
    if ($code -ne 0) { throw "$Name failed (exit $code); see $LogPath" }
}

function Invoke-SqlFile([string]$Path, [string]$TargetDatabase = $Database, [hashtable]$Variables = @{}) {
    $sqlArguments = @('-X', '-h', '127.0.0.1', '-p', "$Port", '-U', 'postgres', '-w', '-d', $TargetDatabase,
        '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose')
    foreach ($key in $Variables.Keys) { $sqlArguments += @('-v', "$key=$($Variables[$key])") }
    $sqlArguments += @('-f', (Join-Path $repoRoot $Path))
    Invoke-LoggedCommand "SQL $TargetDatabase $Path" (Join-Path $PgBin 'psql.exe') $sqlArguments
}

try {
    if ($baseMigrations.Count -ne 4 -or $migrations.Count -lt 8) { throw 'Missing expected migration chain' }
    # Reject an occupied explicit port before initializing; zero selects a free port.
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    try { $probe.Start(); $Port = $probe.LocalEndpoint.Port } finally { $probe.Stop() }
    if (Test-Path -LiteralPath $dataDir) { throw 'Refusing to overwrite a pre-existing cluster' }
    New-Item -ItemType Directory -Path $dataDir -ErrorAction Stop | Out-Null
    $ownsDataDir = $true
    Write-Log '# FixRate AI base/runtime schema and nonempty-history upgrade verification'
    Write-Log "# Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'); port: $Port; cluster: $dataDir"
    Invoke-LoggedCommand 'initdb' (Join-Path $PgBin 'initdb.exe') @('-D', $dataDir, '-U', 'postgres', '-A', 'trust', '--encoding=UTF8', '--locale=C')
    $server = Start-Process -FilePath (Join-Path $PgBin 'postgres.exe') -ArgumentList @('-D', ('"' + $dataDir + '"'), '-p', "$Port", '-h', '127.0.0.1') -RedirectStandardOutput $serverOut -RedirectStandardError $serverErr -WindowStyle Hidden -PassThru
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        if ($server.HasExited) { throw 'Isolated PostgreSQL exited during startup' }
        & (Join-Path $PgBin 'pg_isready.exe') -q -h 127.0.0.1 -p $Port -U postgres -d postgres
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $ready) { throw 'Isolated PostgreSQL readiness timeout' }
    $actualData = & (Join-Path $PgBin 'psql.exe') -X -h 127.0.0.1 -p $Port -U postgres -w -d postgres -tAc 'SHOW data_directory'
    if ($LASTEXITCODE -ne 0 -or [IO.Path]::GetFullPath($actualData.Trim()) -ne [IO.Path]::GetFullPath($dataDir)) {
        throw 'Connected server is not our temporary cluster; refusing database operations'
    }
    $version = & (Join-Path $PgBin 'psql.exe') -X -h 127.0.0.1 -p $Port -U postgres -w -d postgres -tAc 'SELECT version()'
    Write-Log "# Server: $version"
    foreach ($db in @($Database, "${Database}_fresh")) {
        Invoke-LoggedCommand "create $db" (Join-Path $PgBin 'createdb.exe') @('-h', '127.0.0.1', '-p', "$Port", '-U', 'postgres', '-w', $db)
    }
    foreach ($file in $baseMigrations) { Invoke-SqlFile "database/migrations/$($file.Name)" }
    foreach ($file in @('001_integrity.sql','002_planning.sql','003_history.sql','004_tl03_constraints.sql')) {
        Invoke-SqlFile "tests/sql/$file"
    }
    Invoke-SqlFile 'tests/sql/test_maintenance_schema.sql' $Database @{qa03_keep_fixtures='true'}
    Invoke-SqlFile 'tests/sql/005_demo_seed.sql'
    Invoke-SqlFile 'tests/sql/test_maintenance_history_upgrade.sql' $Database @{qa03_capture='true'}
    foreach ($file in $upgradeMigrations) { Invoke-SqlFile "database/migrations/$($file.Name)" }
    Invoke-SqlFile 'tests/sql/test_maintenance_history_upgrade.sql'
    Invoke-SqlFile 'tests/sql/test_runtime_schema.sql'
    foreach ($file in $migrations) { Invoke-SqlFile "database/migrations/$($file.Name)" "${Database}_fresh" }
    Invoke-SqlFile 'tests/sql/test_maintenance_schema.sql' "${Database}_fresh"
    Invoke-SqlFile 'tests/sql/test_runtime_schema.sql' "${Database}_fresh"
    Invoke-SqlFile 'tests/sql/005_demo_seed.sql' "${Database}_fresh"
    Write-Log '=== SQL CHECKS PASSED ==='
}
catch {
    $fail = $true
    Write-Log "=== RESULT: FAILED: $($_.Exception.Message) ==="
    Write-Host "FAILED: $($_.Exception.Message)"
}
finally {
    try {
        if ($server -and -not $server.HasExited) {
            Invoke-LoggedCommand 'stop temporary PostgreSQL' (Join-Path $PgBin 'pg_ctl.exe') @('-D', $dataDir, 'stop', '-m', 'fast', '-w', '-t', '15')
            $server.WaitForExit()
        }
        if ($ownsDataDir) {
            $checkedDataDir = [IO.Path]::GetFullPath($dataDir)
            if ([IO.Path]::GetDirectoryName($checkedDataDir) -ne [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') -or [IO.Path]::GetFileName($checkedDataDir) -ne $clusterName) {
                throw 'Refusing cleanup outside our exact temporary cluster'
            }
            Remove-Item -LiteralPath $checkedDataDir -Recurse -Force -ErrorAction Stop
            Write-Log '# Temporary cluster stopped and removed; working database was not used.'
        }
    }
    catch { $fail = $true; Write-Log "=== CLEANUP FAILED: $($_.Exception.Message) ==="; Write-Host $_.Exception.Message }
    $env:PGCONNECT_TIMEOUT = $previousPgTimeout
    $env:PGCLIENTENCODING = $previousPgEncoding
}
if ($fail) { exit 1 }
Write-Log '=== RESULT: ALL CHECKS PASSED ==='
Write-Host "ALL CHECKS PASSED: $LogPath"
exit 0
