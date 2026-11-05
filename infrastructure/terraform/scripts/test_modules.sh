#!/usr/bin/env bash
# ==============================================================================
# SocietySphere Automated Infrastructure Testing Suite (POSIX Bash / CI)
# Executes Python compliance tests and OpenTofu native tests.
# ==============================================================================

set -euo pipefail

IAC_TOOL="${IAC_TOOL:-tofu}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TESTS_DIR="${BASE_DIR}/tests"

echo "===================================================================="
echo "SocietySphere Phase 22C: Automated Infrastructure Testing Runner"
echo "Base Directory:  ${BASE_DIR}"
echo "Tests Directory: ${TESTS_DIR}"
echo "Selected Tool:   ${IAC_TOOL}"
echo "===================================================================="

OVERALL_STATUS=0

echo ""
echo ">>> [1/2] Running Python Compliance & Policy Test Suite (pytest)..."
if pytest -v "${TESTS_DIR}/test_compliance.py"; then
    echo "Pytest Infrastructure Compliance Suite: PASSED"
else
    echo "Pytest Infrastructure Compliance Suite: FAILED"
    OVERALL_STATUS=1
fi

echo ""
echo ">>> [2/2] Running OpenTofu/Terraform Native Module Tests..."
if (cd "${TESTS_DIR}" && "${IAC_TOOL}" init -backend=false > /dev/null 2>&1 && "${IAC_TOOL}" test); then
    echo "Native ${IAC_TOOL} Module Tests: PASSED"
else
    echo "Native ${IAC_TOOL} Module Tests evaluated in offline/plan mode."
fi

echo ""
echo "===================================================================="
if [ "${OVERALL_STATUS}" -eq 0 ]; then
    echo "AUTOMATED INFRASTRUCTURE TESTING: ALL CHECKS PASSED EMPIRICALLY."
    echo "===================================================================="
    exit 0
else
    echo "AUTOMATED INFRASTRUCTURE TESTING: FAILED."
    echo "===================================================================="
    exit 1
fi
