#!/usr/bin/env bash
# ==============================================================================
# SocietySphere Database Migration Inspection (Bash)
# Non-destructively inspects Alembic heads and database current revision.
# ==============================================================================

set -uo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}====================================================================${NC}"
echo -e "${CYAN}SocietySphere: Database Migration Status Inspection${NC}"
echo -e "${CYAN}====================================================================${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

ALEMBIC_BIN="${PROJECT_ROOT}/.venv/bin/alembic"
if [ ! -f "$ALEMBIC_BIN" ]; then
    if command -v alembic &> /dev/null; then
        ALEMBIC_BIN="alembic"
    else
        echo -e "${RED}[ERROR] alembic executable not found in .venv or PATH.${NC}"
        echo -e "Please install backend dependencies: pip install -r apps/api/requirements-dev.txt"
        exit 1
    fi
fi

ALEMBIC_INI="${PROJECT_ROOT}/apps/api/alembic.ini"

echo ""
echo "1. Inspecting Configured Migration Head..."
heads=$("$ALEMBIC_BIN" -c "$ALEMBIC_INI" heads 2>&1 || true)
echo "$heads"

expected_head="20261102_0025_saas_billing_automation"
if echo "$heads" | grep -q "0025"; then
    echo -e "  ${GREEN}[OK]${NC} Migration head matches expected baseline: ${expected_head}"
else
    echo -e "  ${YELLOW}[WARN]${NC} Unexpected migration head! Expected: ${expected_head}"
fi

echo ""
echo "2. Inspecting Local Database Current Applied Revision..."
echo "(Requires local PostgreSQL running on localhost:5432)"
current=$("$ALEMBIC_BIN" -c "$ALEMBIC_INI" current 2>&1 || true)
if [ $? -eq 0 ] && [ -n "$current" ]; then
    echo -e "  ${GREEN}[OK]${NC} Current database revision: ${current}"
else
    echo -e "  ${YELLOW}[NOTICE]${NC} Could not connect to local database or database is empty."
    echo -e "  Start local database via Docker Compose: docker-compose up -d postgres"
fi

echo ""
echo -e "${CYAN}====================================================================${NC}"
echo -e "${CYAN}Migration Inspection Complete (Read-Only; no database changes made).${NC}"
echo -e "${CYAN}====================================================================${NC}"
