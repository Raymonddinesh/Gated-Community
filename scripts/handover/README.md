# SocietySphere — Handover Helper Scripts

This directory contains lightweight, non-destructive helper scripts to assist developers in onboarding, validating their local environment, inspecting database migration state, and running quality checks.

---

## Safety Guarantees

All scripts in this directory strictly adhere to the following safety rules:
- **Zero Destructive Operations:** No files, database tables, or containers are deleted.
- **Zero Cloud Provisioning:** No `tofu apply` or `terraform apply` commands are executed.
- **Zero Production Migrations:** No database migrations are applied automatically.
- **Zero Hardcoded Credentials:** Scripts rely exclusively on environment variables and standard local defaults.
- **Low Resource Consumption:** Scripts perform static analysis and status inspection without heavy Docker builds or application compilation.

---

## Script Inventory

| Script | Platform | Description |
|---|---|---|
| `check_environment.ps1` | Windows PowerShell | Audits developer machine for required tools (Python, Node, Docker, OpenTofu, Terraform, Git, disk space) and checks for `.env`. |
| `check_environment.sh` | Linux / macOS / WSL | Bash equivalent of the environment prerequisite audit script. |
| `check_migration_status.ps1`| Windows PowerShell | Non-destructively inspects Alembic migration heads and confirms the active migration head (`0025`). |
| `check_migration_status.sh` | Linux / macOS / WSL | Bash equivalent of the migration inspection script. |
| `verify_code_quality.ps1` | Windows PowerShell | Runs read-only static linters and type checkers (Ruff, Mypy, TypeScript `typecheck`). |
| `verify_code_quality.sh` | Linux / macOS / WSL | Bash equivalent of the code quality verification script. |
| `verify_iac_readiness.ps1` | Windows PowerShell | Runs the automated 76-test compliance suite (`test_compliance.py`) and Checkov data tier scan. |
| `verify_iac_readiness.sh` | Linux / macOS / WSL | Bash equivalent of the IaC compliance verification script. |

---

## Usage Examples

### Windows (PowerShell):
```powershell
# 1. Audit developer workstation prerequisites
.\scripts\handover\check_environment.ps1

# 2. Check database migration status
.\scripts\handover\check_migration_status.ps1

# 3. Verify backend and frontend static code quality
.\scripts\handover\verify_code_quality.ps1

# 4. Verify IaC compliance and security posture
.\scripts\handover\verify_iac_readiness.ps1
```

### Linux / macOS / WSL (Bash):
```bash
# Ensure execution permissions
chmod +x scripts/handover/*.sh

# 1. Audit developer workstation prerequisites
./scripts/handover/check_environment.sh

# 2. Check database migration status
./scripts/handover/check_migration_status.sh

# 3. Verify backend and frontend static code quality
./scripts/handover/verify_code_quality.sh

# 4. Verify IaC compliance and security posture
./scripts/handover/verify_iac_readiness.sh
```
