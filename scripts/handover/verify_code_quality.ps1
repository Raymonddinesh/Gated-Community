<#
.SYNOPSIS
    SocietySphere Static Code Quality & Type Check Suite
.DESCRIPTION
    Non-destructively runs Ruff linter, Ruff formatting check, Mypy static type checker,
    and Next.js TypeScript type checking without heavy test execution or Docker builds.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\handover\verify_code_quality.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "SocietySphere: Static Code Quality & Type Check Verification" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptRoot "..\..")

Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvRuff = Join-Path $ProjectRoot ".venv\Scripts\ruff.exe"
$VenvMypy = Join-Path $ProjectRoot ".venv\Scripts\mypy.exe"

if (-not (Test-Path $VenvRuff)) { $VenvRuff = "ruff" }
if (-not (Test-Path $VenvMypy)) { $VenvMypy = "mypy" }

$allPassed = $true

# 1. Ruff linting
Write-Host "`n[1/4] Running Ruff Linter on apps/api and tests..." -ForegroundColor White
& $VenvRuff check apps/api tests
if ($LASTEXITCODE -eq 0) {
    Write-Host "  --> Ruff Lint: PASSED" -ForegroundColor Green
} else {
    Write-Host "  --> Ruff Lint: FAILED" -ForegroundColor Red
    $allPassed = $false
}

# 2. Ruff formatting
Write-Host "`n[2/4] Checking code formatting with Ruff..." -ForegroundColor White
& $VenvRuff format --check apps/api tests
if ($LASTEXITCODE -eq 0) {
    Write-Host "  --> Ruff Format Check: PASSED" -ForegroundColor Green
} else {
    Write-Host "  --> Ruff Format Check: FAILED" -ForegroundColor Red
    $allPassed = $false
}

# 3. Mypy typecheck
Write-Host "`n[3/4] Running Mypy Static Type Checker..." -ForegroundColor White
& $VenvMypy apps/api tests
if ($LASTEXITCODE -eq 0) {
    Write-Host "  --> Mypy Typecheck: PASSED" -ForegroundColor Green
} else {
    Write-Host "  --> Mypy Typecheck: FAILED" -ForegroundColor Red
    $allPassed = $false
}

# 4. Frontend TypeScript check
Write-Host "`n[4/4] Running Frontend TypeScript Typecheck (tsc --noEmit)..." -ForegroundColor White
$WebDir = Join-Path $ProjectRoot "apps\web"
if (Test-Path $WebDir) {
    Push-Location $WebDir
    npm run typecheck
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  --> Frontend Typecheck: PASSED" -ForegroundColor Green
    } else {
        Write-Host "  --> Frontend Typecheck: FAILED" -ForegroundColor Red
        $allPassed = $false
    }
    Pop-Location
} else {
    Write-Host "  --> apps/web not found, skipping frontend check." -ForegroundColor Yellow
}

Write-Host "`n====================================================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "OVERALL STATUS: ALL CODE QUALITY CHECKS PASSED EMPIRICALLY." -ForegroundColor Green
} else {
    Write-Host "OVERALL STATUS: SOME CHECKS FAILED. Review output above." -ForegroundColor Red
}
Write-Host "====================================================================" -ForegroundColor Cyan
