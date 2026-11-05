#!/usr/bin/env bash
# ==============================================================================
# SocietySphere Static Code Quality Verification (Bash)
# Runs Ruff, Mypy, and TypeScript checks without heavy tests or Docker builds.
# ==============================================================================

set -uo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}====================================================================${NC}"
echo -e "${CYAN}SocietySphere: Static Code Quality & Type Check Verification${NC}"
echo -e "${CYAN}====================================================================${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${PROJECT_ROOT}"

RUFF_BIN="${PROJECT_ROOT}/.venv/bin/ruff"
if [ ! -f "$RUFF_BIN" ]; then RUFF_BIN="ruff"; fi

MYPY_BIN="${PROJECT_ROOT}/.venv/bin/mypy"
if [ ! -f "$MYPY_BIN" ]; then MYPY_BIN="mypy"; fi

all_passed=true

echo ""
echo "[1/4] Running Ruff Linter on apps/api and tests..."
if "$RUFF_BIN" check apps/api tests; then
    echo -e "  ${GREEN}--> Ruff Lint: PASSED${NC}"
else
    echo -e "  ${RED}--> Ruff Lint: FAILED${NC}"
    all_passed=false
fi

echo ""
echo "[2/4] Checking code formatting with Ruff..."
if "$RUFF_BIN" format --check apps/api tests; then
    echo -e "  ${GREEN}--> Ruff Format Check: PASSED${NC}"
else
    echo -e "  ${RED}--> Ruff Format Check: FAILED${NC}"
    all_passed=false
fi

echo ""
echo "[3/4] Running Mypy Static Type Checker..."
if "$MYPY_BIN" apps/api tests; then
    echo -e "  ${GREEN}--> Mypy Typecheck: PASSED${NC}"
else
    echo -e "  ${RED}--> Mypy Typecheck: FAILED${NC}"
    all_passed=false
fi

echo ""
echo "[4/4] Running Frontend TypeScript Typecheck..."
if [ -d "apps/web" ]; then
    cd apps/web
    if npm run typecheck; then
        echo -e "  ${GREEN}--> Frontend Typecheck: PASSED${NC}"
    else
        echo -e "  ${RED}--> Frontend Typecheck: FAILED${NC}"
        all_passed=false
    fi
    cd "${PROJECT_ROOT}"
fi

echo ""
echo -e "${CYAN}====================================================================${NC}"
if [ "$all_passed" = true ]; then
    echo -e "${GREEN}OVERALL STATUS: ALL CODE QUALITY CHECKS PASSED EMPIRICALLY.${NC}"
else
    echo -e "${RED}OVERALL STATUS: SOME CHECKS FAILED. Review output above.${NC}"
fi
echo -e "${CYAN}====================================================================${NC}"
