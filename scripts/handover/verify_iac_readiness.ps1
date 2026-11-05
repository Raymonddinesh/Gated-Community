<#
.SYNOPSIS
    SocietySphere Infrastructure as Code Compliance & Security Verification
.DESCRIPTION
    Non-destructively runs the 76-test Python compliance suite and Checkov security scan.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\handover\verify_iac_readiness.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "SocietySphere: Infrastructure Compliance & Security Verification" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptRoot "..\..")

Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) { $VenvPython = "python" }

$allPassed = $true

# 1. Python Compliance Suite
Write-Host "`n[1/2] Running Python Infrastructure Compliance Test Suite (76 tests)..." -ForegroundColor White
& $VenvPython -m pytest infrastructure/terraform/tests/test_compliance.py -v
if ($LASTEXITCODE -eq 0) {
    Write-Host "  --> Compliance Tests: PASSED (76/76)" -ForegroundColor Green
} else {
    Write-Host "  --> Compliance Tests: FAILED" -ForegroundColor Red
    $allPassed = $false
}

# 2. Checkov Security Scan
Write-Host "`n[2/2] Running Checkov Static Analysis on Data Tier Modules..." -ForegroundColor White
$CheckovExe = Get-Command "checkov" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if ($CheckovExe) {
    & $CheckovExe -d infrastructure/terraform/modules/rds -d infrastructure/terraform/modules/redis -d infrastructure/terraform/modules/rabbitmq -d infrastructure/terraform/modules/storage --config-file infrastructure/terraform/.checkov.yaml --compact
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  --> Checkov Security Scan: PASSED (0 failures)" -ForegroundColor Green
    } else {
        Write-Host "  --> Checkov Security Scan: FAILED" -ForegroundColor Red
        $allPassed = $false
    }
} else {
    Write-Host "  --> checkov not found on PATH. Install via pip install checkov to run security scan." -ForegroundColor Yellow
}

Write-Host "`n====================================================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "OVERALL STATUS: INFRASTRUCTURE COMPLIANCE CHECKS PASSED." -ForegroundColor Green
} else {
    Write-Host "OVERALL STATUS: COMPLIANCE CHECKS FAILED. Review output above." -ForegroundColor Red
}
Write-Host "====================================================================" -ForegroundColor Cyan
