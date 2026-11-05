<#
.SYNOPSIS
    SocietySphere Non-Destructive Database Migration Inspection
.DESCRIPTION
    Checks the Alembic migration history, verifies the active migration head,
    and inspects the database current revision without applying changes.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\handover\check_migration_status.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "SocietySphere: Database Migration Status Inspection" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptRoot "..\..")

# Find alembic executable
$AlembicExe = Join-Path $ProjectRoot ".venv\Scripts\alembic.exe"
if (-not (Test-Path $AlembicExe)) {
    $AlembicExe = Get-Command "alembic" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
}

if (-not $AlembicExe) {
    Write-Host "[ERROR] alembic executable not found in .venv or PATH." -ForegroundColor Red
    Write-Host "Please activate virtual environment or install dependencies:" -ForegroundColor Yellow
    Write-Host "  pip install -r apps/api/requirements-dev.txt" -ForegroundColor Yellow
    exit 1
}

$AlembicIni = Join-Path $ProjectRoot "apps\api\alembic.ini"
if (-not (Test-Path $AlembicIni)) {
    Write-Host "[ERROR] alembic.ini not found at $AlembicIni" -ForegroundColor Red
    exit 1
}

Write-Host "`n1. Inspecting Configured Migration Head..." -ForegroundColor White
$heads = & $AlembicExe -c $AlembicIni heads 2>&1
Write-Host $heads -ForegroundColor Gray

$expectedHead = "20261102_0025_saas_billing_automation"
if ($heads -match "0025") {
    Write-Host "  [OK] Migration head matches expected baseline: $expectedHead" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Unexpected migration head! Expected: $expectedHead" -ForegroundColor Yellow
}

Write-Host "`n2. Inspecting Local Database Current Applied Revision..." -ForegroundColor White
Write-Host "(Requires local PostgreSQL running on localhost:5432)" -ForegroundColor Gray
$current = & $AlembicExe -c $AlembicIni current 2>&1
if ($LASTEXITCODE -eq 0) {
    if ($current) {
        Write-Host "  [OK] Current database revision: $current" -ForegroundColor Green
    } else {
        Write-Host "  [INFO] Database is connected but no migrations applied yet (empty database)." -ForegroundColor Cyan
        Write-Host "  To apply migrations on local dev: alembic -c apps/api/alembic.ini upgrade head" -ForegroundColor Gray
    }
} else {
    Write-Host "  [NOTICE] Could not connect to local database." -ForegroundColor Yellow
    Write-Host "  Start local database via Docker Compose: docker-compose up -d postgres" -ForegroundColor Gray
}

Write-Host "`n====================================================================" -ForegroundColor Cyan
Write-Host "Migration Inspection Complete (Read-Only; no database changes made)." -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan
