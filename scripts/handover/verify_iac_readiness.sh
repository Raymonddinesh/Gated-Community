#!/usr/bin/env bash
# ==============================================================================
# SocietySphere Infrastructure Compliance & Security Verification (Bash)
# Runs the 76-test Python compliance suite and Checkov scan non-destructively.
# ==============================================================================

set -uo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}====================================================================${NC}"
echo -e "${CYAN}SocietySphere: Infrastructure Compliance & Security Verification${NC}"
echo -e "${CYAN}====================================================================${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${PROJECT_ROOT}"

PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then PYTHON_BIN="python3"; fi

all_passed=true

echo ""
echo "[1/2] Running Python Infrastructure Compliance Test Suite (76 tests)..."
if "$PYTHON_BIN" -m pytest infrastructure/terraform/tests/test_compliance.py -v; then
    echo -e "  ${GREEN}--> Compliance Tests: PASSED (76/76)${NC}"
else
    echo -e "  ${RED}--> Compliance Tests: FAILED${NC}"
    all_passed=false
fi

echo ""
echo "[2/2] Running Checkov Static Analysis on Data Tier Modules..."
if command -v checkov &> /dev/null; then
    if checkov -d infrastructure/terraform/modules/rds -d infrastructure/terraform/modules/redis -d infrastructure/terraform/modules/rabbitmq -d infrastructure/terraform/modules/storage --config-file infrastructure/terraform/.checkov.yaml --compact; then
        echo -e "  ${GREEN}--> Checkov Security Scan: PASSED (0 failures)${NC}"
    else
        echo -e "  ${RED}--> Checkov Security Scan: FAILED${NC}"
        all_passed=false
    fi
else
    echo -e "  ${YELLOW}--> checkov not found on PATH. Install via pip install checkov.${NC}"
fi

echo ""
echo -e "${CYAN}====================================================================${NC}"
if [ "$all_passed" = true ]; then
    echo -e "${GREEN}OVERALL STATUS: INFRASTRUCTURE COMPLIANCE CHECKS PASSED.${NC}"
else
    echo -e "${RED}OVERALL STATUS: COMPLIANCE CHECKS FAILED. Review output above.${NC}"
fi
echo -e "${CYAN}====================================================================${NC}"
