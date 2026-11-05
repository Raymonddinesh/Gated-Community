#!/usr/bin/env bash
# ==============================================================================
# SocietySphere Developer Environment Prerequisite Audit Script (Bash)
# Non-destructively audits developer tools, python env, configs, and disk space.
# ==============================================================================

set -uo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}====================================================================${NC}"
echo -e "${CYAN}SocietySphere: Developer Environment Prerequisite Audit${NC}"
echo -e "${CYAN}====================================================================${NC}"

test_tool() {
    local tool_name="$1"
    local cmd="$2"
    if command -v $cmd &> /dev/null; then
        local ver
        ver=$($cmd --version 2>&1 | head -n 1)
        echo -e "  ${GREEN}[OK]${NC} ${tool_name} is installed: ${ver}"
        return 0
    else
        echo -e "  ${YELLOW}[MISSING]${NC} ${tool_name} is NOT found on PATH."
        return 1
    fi
}

echo ""
echo "1. Inspecting Required Runtimes & Tooling..."
test_tool "Python" "python3" || test_tool "Python" "python" || true
test_tool "Node.js" "node" || true
test_tool "npm" "npm" || true
test_tool "Docker CLI" "docker" || true
test_tool "Git" "git" || true
test_tool "OpenTofu" "tofu" || true
test_tool "Terraform" "terraform" || true

echo ""
echo "2. Inspecting Project Configuration & Virtual Environments..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [ -d "${PROJECT_ROOT}/.venv" ]; then
    echo -e "  ${GREEN}[OK]${NC} Python virtual environment exists at: .venv"
else
    echo -e "  ${YELLOW}[WARN]${NC} Python virtual environment (.venv) not found. Run: python -m venv .venv"
fi

if [ -f "${PROJECT_ROOT}/.env" ]; then
    echo -e "  ${GREEN}[OK]${NC} Local environment file exists at: .env"
else
    echo -e "  ${YELLOW}[WARN]${NC} Local .env not found! Copy from template: cp .env.example .env"
fi

echo ""
echo "3. Inspecting Host Disk Space..."
if command -v df &> /dev/null; then
    free_kb=$(df -k "${PROJECT_ROOT}" | awk 'NR==2 {print $4}')
    free_gb=$(echo "scale=2; ${free_kb}/1048576" | bc 2>/dev/null || awk -v k="$free_kb" 'BEGIN {printf "%.2f", k/1048576}')
    echo -e "  ${GREEN}[OK]${NC} Available disk space: ${free_gb} GB"
fi

echo ""
echo "4. Inspecting Git Repository Status..."
if command -v git &> /dev/null; then
    branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "uncommitted-initial")
    echo -e "  ${GREEN}[OK]${NC} Current Git branch: ${branch}"
fi

echo ""
echo -e "${CYAN}====================================================================${NC}"
echo -e "${CYAN}Audit Complete. Review warnings above before launching services.${NC}"
echo -e "${CYAN}====================================================================${NC}"
