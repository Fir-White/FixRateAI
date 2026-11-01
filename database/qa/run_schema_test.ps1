# Runs the schema contract test against a throwaway PostgreSQL cluster.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File database/qa/run_schema_test.ps1
#   powershell -ExecutionPolicy Bypass -File database/qa/run_schema_test.ps1 -PgBin 'C:\Program Files\PostgreSQL\18\bin'
#
# The script never touches the project database: it initializes a temporary
# cluster under $env:TEMP, applies database/migrations/001..004, runs the SQL
# tests and removes the cluster afterwards. Exit code 0 means every check passed.

param(
    [string]$PgBin = 'C:\Program Files\PostgreSQL\18\bin',
    [int]$Port = 55433,
    [string]$Database = 'fixrate_test_schema',
    [string]$LogPath = (Join-Path $PSScriptRoot 'run_schema_test.log')
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$dataDir = Join-Path $env:TEMP "opencode\pgfixrate_schema_$PID"
$serverOut = Join-Path $env:TEMP "opencode\pgfixrate_schema_$PID.out.log"
$serverErr = Join-Path $env:TEMP "opencode\pgfixrate_schema_$PID.err.log"
$migrations = @(
    'database/migrations/001_tl02.sql',
    'database/migrations/002_planning_contract.sql',
    'database/migrations/003_occurrence_uniqueness.sql',
    'database/migrations/004_tl03_safe_constraints.sql'
)
$tests = @(
    'database/tests/001_integrity.sql',
    'database/tests/002_planning.sql',
    'database/tests/003_history.sql',
    'database/tests/004_tl03_constraints.sql',
    'database/qa/test_maintenance_schema.sql'
)

$env:PGCONNECT_TIMEOUT = '10'
$env:PGCLIENTENCODING = 'UTF8'
$fail = $false
$server = $null

function Write-Log([string]$line) {
    $line | Out-File -FilePath $LogPath -Append -Encoding utf8
}

function Invoke-SqlFile([string]$relativePath) {
    & (Join-Path $PgBin 'psql.exe') -X -h 127.0.0.1 -p $Port -U postgres `
        -d $Database -w -v ON_ERROR_STOP=1 -f (Join-Path $repoRoot $relativePath) 2>&1 |
        Out-File -FilePath $LogPath -Append -Encoding utf8
    return $LASTEXITCODE
}

try {
    if (Test-Path -LiteralPath $dataDir) { throw 'Temporary cluster path already exists; refusing to overwrite' }
    & (Join-Path $PgBin 'initdb.exe') -D $dataDir -U postgres -A trust `
        --encoding=UTF8 --locale=C 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'initdb failed' }

    # Start-Process with a hidden window keeps the console detached; pg_ctl
    # inherits the parent console and can hang in non-interactive sessions.
    $server = Start-Process -FilePath (Join-Path $PgBin 'postgres.exe') `
        -ArgumentList @('-D', $dataDir, '-p', $Port,
            '-c', 'listen_addresses=127.0.0.1', '-c', 'autovacuum=off') `
        -RedirectStandardOutput $serverOut -RedirectStandardError $serverErr `
        -WindowStyle Hidden -PassThru

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        & (Join-Path $PgBin 'psql.exe') -X -h 127.0.0.1 -p $Port -U postgres `
            -d postgres -w -tAc 'select 1' 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    }
    if (-not $ready) { throw 'isolated PostgreSQL did not start' }

    & (Join-Path $PgBin 'createdb.exe') -h 127.0.0.1 -p $Port -U postgres -w $Database 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "createdb $Database failed" }

    @(
        '# FixRate AI schema run log',
        "# Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
        "# Server: PostgreSQL ($((& (Join-Path $PgBin 'psql.exe') -X -h 127.0.0.1 -p $Port -U postgres -d postgres -w -tAc 'select version()'))), isolated cluster",
        "# Database: $Database",
        '# Migrations: database/migrations/001..004',
        '# Tests: database/tests/001..004, database/qa/test_maintenance_schema.sql',
        ''
    ) | Out-File -FilePath $LogPath -Encoding utf8

    foreach ($file in $migrations) {
        Write-Log "=== APPLY $file ==="
        if ((Invoke-SqlFile $file) -ne 0) { throw "migration failed: $file" }
    }

    foreach ($file in $tests) {
        Write-Log "=== RUN $file ==="
        if ((Invoke-SqlFile $file) -ne 0) { throw "test failed: $file" }
    }

    Write-Log '=== RESULT: ALL CHECKS PASSED ==='
    Write-Host 'ALL CHECKS PASSED'
}
catch {
    $fail = $true
    Write-Log "=== RESULT: FAILED: $($_.Exception.Message) ==="
    Write-Host "FAILED: $($_.Exception.Message)"
}
finally {
    if ($server -and -not $server.HasExited) {
        & (Join-Path $PgBin 'pg_ctl.exe') -D $dataDir stop -m immediate 2>&1 | Out-Null
        if (-not $server.HasExited) { $server.Kill() }
    }
    Start-Sleep -Milliseconds 500
    $checkedDataDir = [IO.Path]::GetFullPath($dataDir)
    $expectedTempRoot = [IO.Path]::GetFullPath((Join-Path $env:TEMP 'opencode')) + [IO.Path]::DirectorySeparatorChar
    if (-not $checkedDataDir.StartsWith($expectedTempRoot, [StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($checkedDataDir) -ne "pgfixrate_schema_$PID") {
        throw 'Refusing cleanup outside the exact temporary cluster directory'
    }
    Remove-Item -LiteralPath $checkedDataDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $serverOut, $serverErr -Force -ErrorAction SilentlyContinue
}

if ($fail) { exit 1 } else { exit 0 }
