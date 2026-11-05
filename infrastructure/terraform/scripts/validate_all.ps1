# ==============================================================================
# SocietySphere Infrastructure as Code Validation Suite (PowerShell)
# Verifies OpenTofu/Terraform formatting, validation, linting, and tfsec scans
# across all bootstrap, reusable modules, and environment tiers.
# ==============================================================================

[CmdletBinding()]
param (
    [string]$IacTool = "tofu"
)

$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path } else { (Get-Location).Path }
$BaseDir = (Resolve-Path (Join-Path $ScriptDir "..")).Path

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "SocietySphere Phase 22B: Full Infrastructure as Code Validation Suite" -ForegroundColor Cyan
Write-Host "Base Directory: $BaseDir" -ForegroundColor Cyan
Write-Host "Selected Tool:  $IacTool" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan

# Verify Prerequisites
$tools = @($IacTool, "tflint", "tfsec")
foreach ($tool in $tools) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Error "Required tool '$tool' not found on PATH. Please ensure OpenTofu/Terraform, TFLint, and tfsec are installed."
        exit 1
    }
}

$DirectoriesToValidate = @(
    "bootstrap",
    "modules/networking",
    "modules/security",
    "modules/storage",
    "modules/monitoring",
    "modules/ecs",
    "modules/rds",
    "modules/redis",
    "modules/rabbitmq",
    "environments/dev",
    "environments/qa",
    "environments/staging",
    "environments/production"
)

$OverallFailed = $false
$SummaryResults = @()

foreach ($relDir in $DirectoriesToValidate) {
    $targetDir = Join-Path $BaseDir $relDir
    Write-Host "`n>>> Validating: $relDir" -ForegroundColor Yellow

    Push-Location $targetDir
    try {
        # 1. Format Check
        Write-Host "  [1/4] Checking formatting..." -NoNewline
        $fmtOutput = & $IacTool fmt -check 2>&1
        $fmtPass = ($LASTEXITCODE -eq 0)
        if ($fmtPass) {
            Write-Host " PASSED" -ForegroundColor Green
        } else {
            Write-Host " FAILED (Formatting diff detected)" -ForegroundColor Red
            Write-Host "$fmtOutput" -ForegroundColor Red
            $OverallFailed = $true
        }

        # 2. Initialization & Syntax Validation
        Write-Host "  [2/4] Validating configuration syntax..." -NoNewline
        $initOutput = & $IacTool init -backend=false 2>&1
        $valOutput = & $IacTool validate 2>&1
        $valPass = ($LASTEXITCODE -eq 0)
        if ($valPass) {
            Write-Host " PASSED" -ForegroundColor Green
        } else {
            Write-Host " FAILED" -ForegroundColor Red
            Write-Host "$valOutput" -ForegroundColor Red
            $OverallFailed = $true
        }

        # 3. TFLint
        Write-Host "  [3/4] Running TFLint..." -NoNewline
        $lintOutput = & tflint 2>&1
        $lintPass = ($LASTEXITCODE -eq 0)
        if ($lintPass) {
            Write-Host " PASSED" -ForegroundColor Green
        } else {
            Write-Host " FAILED" -ForegroundColor Red
            Write-Host "$lintOutput" -ForegroundColor Red
            $OverallFailed = $true
        }

        # 4. tfsec Security Scan
        Write-Host "  [4/4] Running tfsec scan..." -NoNewline
        $secOutput = & tfsec . --concise-output 2>&1
        $secPass = ($LASTEXITCODE -eq 0)
        if ($secPass) {
            Write-Host " PASSED" -ForegroundColor Green
        } else {
            Write-Host " FAILED (Security findings detected)" -ForegroundColor Red
            Write-Host "$secOutput" -ForegroundColor Red
            $OverallFailed = $true
        }

        $SummaryResults += [PSCustomObject]@{
            Component  = $relDir
            Formatting = if ($fmtPass) { "PASS" } else { "FAIL" }
            Validation = if ($valPass) { "PASS" } else { "FAIL" }
            Linting    = if ($lintPass) { "PASS" } else { "FAIL" }
            Security   = if ($secPass) { "PASS" } else { "FAIL" }
        }
    } finally {
        Pop-Location
    }
}

Write-Host "`n====================================================================" -ForegroundColor Cyan
Write-Host "SUMMARY RESULTS MATRIX:" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan
$SummaryResults | Format-Table -AutoSize

if ($OverallFailed) {
    Write-Host "OVERALL VALIDATION STATUS: FAILED. Please review flagged issues." -ForegroundColor Red
    exit 1
} else {
    Write-Host "OVERALL VALIDATION STATUS: ALL CHECKS PASSED EMPIRICALLY." -ForegroundColor Green
    Write-Host "All 9 modules and 4 environments conform to SocietySphere standards." -ForegroundColor Green
    Write-Host "====================================================================" -ForegroundColor Cyan
    exit 0
}
