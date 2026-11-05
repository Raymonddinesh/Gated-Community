<#
.SYNOPSIS
    SocietySphere Developer Environment Prerequisite Audit Script
.DESCRIPTION
    Non-destructively inspects the host system for required development tools,
    virtual environments, environment configuration, and free disk space.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\handover\check_environment.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "SocietySphere: Developer Environment Prerequisite Audit" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan

function Test-Tool {
    param (
        [string]$ToolName,
        [string]$Command,
        [string]$VersionPattern
    )
    try {
        $output = Invoke-Expression $Command 2>&1
        if ($LASTEXITCODE -eq 0 -or $output) {
            $versionMatch = [regex]::Match($output, $VersionPattern)
            $version = if ($versionMatch.Success) { $versionMatch.Value } else { $output.ToString().Trim().Split("`n")[0] }
            Write-Host "  [OK] $ToolName is installed: $version" -ForegroundColor Green
            return
        } else {
            Write-Host "  [MISSING] $ToolName is NOT installed or returned an error." -ForegroundColor Yellow
            return
        }
    } catch {
        Write-Host "  [MISSING] $ToolName is NOT found on PATH." -ForegroundColor Red
        return
    }
}

Write-Host "`n1. Inspecting Required Runtimes & Tooling..." -ForegroundColor White
Test-Tool -ToolName "Python" -Command "python --version" -VersionPattern "Python \d+\.\d+\.\d+"
Test-Tool -ToolName "Node.js" -Command "node --version" -VersionPattern "v\d+\.\d+\.\d+"
Test-Tool -ToolName "npm" -Command "npm --version" -VersionPattern "\d+\.\d+\.\d+"
Test-Tool -ToolName "Docker CLI" -Command "docker --version" -VersionPattern "Docker version [\d\.]+"
Test-Tool -ToolName "Git" -Command "git --version" -VersionPattern "git version [\d\.]+"
Test-Tool -ToolName "OpenTofu" -Command "tofu --version" -VersionPattern "OpenTofu v[\d\.]+"
Test-Tool -ToolName "Terraform" -Command "terraform --version" -VersionPattern "Terraform v[\d\.]+"

Write-Host "`n2. Inspecting Project Configuration & Virtual Environments..." -ForegroundColor White
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptRoot "..\..")

# Check .venv
$VenvPath = Join-Path $ProjectRoot ".venv"
if (Test-Path $VenvPath) {
    Write-Host "  [OK] Python virtual environment exists at: .venv" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Python virtual environment (.venv) not found. Create via: python -m venv .venv" -ForegroundColor Yellow
}

# Check .env
$EnvPath = Join-Path $ProjectRoot ".env"
$EnvExamplePath = Join-Path $ProjectRoot ".env.example"
if (Test-Path $EnvPath) {
    Write-Host "  [OK] Local environment file exists at: .env" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Local .env not found! Copy from template: cp .env.example .env" -ForegroundColor Yellow
}

# Check disk space
Write-Host "`n3. Inspecting Host Disk Space..." -ForegroundColor White
$drive = (Get-Item $ProjectRoot).PSDrive
if ($drive) {
    $freeGb = [math]::Round($drive.Free / 1GB, 2)
    $usedGb = [math]::Round($drive.Used / 1GB, 2)
    if ($freeGb -lt 2.0) {
        Write-Host "  [CRITICAL] Free disk space on drive $($drive.Name): ${freeGb} GB (< 2 GB!). Avoid heavy builds." -ForegroundColor Red
    } elseif ($freeGb -lt 5.0) {
        Write-Host "  [WARN] Free disk space on drive $($drive.Name): ${freeGb} GB. Keep builds lightweight." -ForegroundColor Yellow
    } else {
        Write-Host "  [OK] Free disk space on drive $($drive.Name): ${freeGb} GB." -ForegroundColor Green
    }
}

# Check Git branch
Write-Host "`n4. Inspecting Git Repository Status..." -ForegroundColor White
try {
    $branch = git rev-parse --abbrev-ref HEAD 2>$null
    if ($branch) {
        Write-Host "  [OK] Current Git branch: $branch" -ForegroundColor Green
    } else {
        Write-Host "  [INFO] Git repository initialized, currently on initial uncommitted branch." -ForegroundColor Cyan
    }
} catch {
    Write-Host "  [WARN] Git not initialized." -ForegroundColor Yellow
}

Write-Host "`n====================================================================" -ForegroundColor Cyan
Write-Host "Audit Complete. Review warnings above before launching services." -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan
