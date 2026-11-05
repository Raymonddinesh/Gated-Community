#!/usr/bin/env bash
# ==============================================================================
# SocietySphere Infrastructure as Code Validation Suite (POSIX Bash / CI)
# Verifies OpenTofu/Terraform formatting, validation, linting, and tfsec scans
# across all bootstrap, reusable modules, and environment tiers.
# ==============================================================================

set -euo pipefail

IAC_TOOL="${IAC_TOOL:-tofu}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "===================================================================="
echo "SocietySphere Phase 22B: Full Infrastructure as Code Validation Suite"
echo "Base Directory: ${BASE_DIR}"
echo "Selected Tool:  ${IAC_TOOL}"
echo "===================================================================="

# Check prerequisites
for tool in "${IAC_TOOL}" tflint tfsec; do
    if ! command -v "${tool}" &> /dev/null; then
        echo "ERROR: Required tool '${tool}' is not installed or not in PATH."
        exit 1
    fi
done

TARGET_DIRS=(
    "bootstrap"
    "modules/networking"
    "modules/security"
    "modules/storage"
    "modules/monitoring"
    "modules/ecs"
    "modules/rds"
    "modules/redis"
    "modules/rabbitmq"
    "environments/dev"
    "environments/qa"
    "environments/staging"
    "environments/production"
)

OVERALL_STATUS=0

for rel_dir in "${TARGET_DIRS[@]}"; do
    target="${BASE_DIR}/${rel_dir}"
    echo ""
    echo ">>> Validating: ${rel_dir}"

    echo -n "  [1/4] Checking formatting... "
    if "${IAC_TOOL}" -chdir="${target}" fmt -check > /dev/null 2>&1; then
        echo "PASSED"
    else
        echo "FAILED"
        OVERALL_STATUS=1
    fi

    echo -n "  [2/4] Validating configuration syntax... "
    "${IAC_TOOL}" -chdir="${target}" init -backend=false > /dev/null 2>&1
    if "${IAC_TOOL}" -chdir="${target}" validate > /dev/null 2>&1; then
        echo "PASSED"
    else
        echo "FAILED"
        OVERALL_STATUS=1
    fi

    echo -n "  [3/4] Running TFLint... "
    if (cd "${target}" && tflint > /dev/null 2>&1); then
        echo "PASSED"
    else
        echo "FAILED"
        OVERALL_STATUS=1
    fi

    echo -n "  [4/4] Running tfsec scan... "
    if (cd "${target}" && tfsec . --concise-output > /dev/null 2>&1); then
        echo "PASSED"
    else
        echo "FAILED"
        OVERALL_STATUS=1
    fi
done

echo ""
echo "===================================================================="
if [ "${OVERALL_STATUS}" -eq 0 ]; then
    echo "OVERALL VALIDATION STATUS: ALL CHECKS PASSED EMPIRICALLY."
    echo "===================================================================="
    exit 0
else
    echo "OVERALL VALIDATION STATUS: FAILED. Please review flagged issues."
    echo "===================================================================="
    exit 1
fi
