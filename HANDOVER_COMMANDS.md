# SocietySphere — Verified Developer Handover Commands

**Document Version:** 1.0.0  
**Date:** November 5, 2026  
**Audience:** Incoming Developer, DevOps Engineer, QA Engineer  
**Project Path:** `C:\SocApp`  

This document contains **verified, empirical commands** matching the exact configurations, scripts, and package definitions in the SocietySphere repository.

---

## Command Safety Classification Legend

| Badge | Classification | Description |
|---|---|---|
| `[SAFE-LOCAL]` | Safe Local Command | Operates locally without side effects on cloud or persistent stores. |
| `[LOCAL-MUTATING]` | Local Mutating Command | Alters local files, dependencies, or local Docker containers. |
| `[REQUIRES-LOCAL-STACK]` | Requires Local Stack | Requires running local Docker Compose dependencies (Postgres/Redis/RabbitMQ). |
| `[REQUIRES-AWS-CREDS]` | Requires AWS Credentials | Calls AWS APIs via AWS CLI, OpenTofu, or Terraform. |
| `[LIVE-INFRASTRUCTURE]` | Live Infrastructure Operation | Generates plans or reads state from live AWS environments. |
| `[DESTRUCTIVE-APPROVAL-REQUIRED]` | Critical / Destructive | Can alter or delete database records, apply cloud infrastructure, or roll back state. **Requires explicit Principal Architect approval.** |

---

## 1. Local Development Environment Setup

### 1.1 Backend Environment Setup (Python 3.12) `[LOCAL-MUTATING]`
```powershell
# 1. Initialize environment configuration from sanitized template
Copy-Item .env.example .env

# 2. Create Python 3.12 virtual environment
python -m venv .venv

# 3. Activate virtual environment (Windows PowerShell)
.\.venv\Scripts\Activate.ps1
# Alternative for Linux / macOS / WSL:
# source .venv/bin/activate

# 4. Install backend dependencies (including dev/test tooling)
pip install -r apps/api/requirements-dev.txt
```

### 1.2 Frontend Environment Setup (Next.js 14 / TypeScript) `[LOCAL-MUTATING]`
```powershell
# Navigate to web application directory
cd apps/web

# Install frontend dependencies via npm
npm install

# Return to repository root
cd ../..
```

---

## 2. Docker Compose Local Sandbox Development

### 2.1 Start Local Infrastructure Stack `[LOCAL-MUTATING]`
Starts PostgreSQL 16, Redis 7, RabbitMQ 3 Management, and MinIO S3 storage with local persistent Docker volumes:
```powershell
# Start backing services in background
docker-compose up -d postgres redis rabbitmq minio

# Or start the complete stack including local API container:
docker-compose up -d
```

### 2.2 Inspect Service Health & Logs `[SAFE-LOCAL]`
```powershell
# Check container status and health probe results
docker-compose ps

# Follow logs from specific services
docker-compose logs -f postgres
docker-compose logs -f redis
docker-compose logs -f rabbitmq
docker-compose logs -f minio
docker-compose logs -f api
```

### 2.3 Stop or Tear Down Local Containers
```powershell
# Stop running containers without removing data: [SAFE-LOCAL]
docker-compose stop

# Remove containers while preserving volumes: [LOCAL-MUTATING]
docker-compose down

# CRITICAL: Wipe containers and ALL local database/volume data: [DESTRUCTIVE-APPROVAL-REQUIRED]
docker-compose down -v
```

---

## 3. Database Migration & Seeding Commands (Alembic)

SocietySphere utilizes Alembic with asynchronous PostgreSQL connections.

### 3.1 Inspect Migration Status `[SAFE-LOCAL]`
```powershell
# Check the current database revision
.\.venv\Scripts\alembic -c apps/api/alembic.ini current

# Inspect migration history up to head
.\.venv\Scripts\alembic -c apps/api/alembic.ini history --verbose

# Confirm the head revision (Must show 20261102_0025_saas_billing_automation)
.\.venv\Scripts\alembic -c apps/api/alembic.ini heads
```

### 3.2 Apply Database Migrations
```powershell
# Apply pending migrations to local development database: [REQUIRES-LOCAL-STACK]
.\.venv\Scripts\alembic -c apps/api/alembic.ini upgrade head

# Roll back a single migration revision (local development only): [DESTRUCTIVE-APPROVAL-REQUIRED]
.\.venv\Scripts\alembic -c apps/api/alembic.ini downgrade -1

# DANGER: Applying migrations against Staging or Production databases:
# [DESTRUCTIVE-APPROVAL-REQUIRED] - Strictly forbidden without Principal Database Architect authorization!
```

### 3.3 Seed Local Development Data `[LOCAL-MUTATING]` `[REQUIRES-LOCAL-STACK]`
Populates standard permissions, roles, test societies (Palm Meadows & Greenwood Enclave), and test users:
```powershell
.\.venv\Scripts\python infrastructure/scripts/seed_dev_data.py
```

---

## 4. Running the Application Locally

### 4.1 Run FastAPI Backend Server `[SAFE-LOCAL]` `[REQUIRES-LOCAL-STACK]`
```powershell
# Launches API on port 8000 with auto-reload
.\.venv\Scripts\uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000 --reload
```
- API Base URL: `http://localhost:8000`
- Interactive Swagger Documentation: `http://localhost:8000/docs`
- Health Probe: `http://localhost:8000/health`
- Readiness Probe: `http://localhost:8000/health/ready`

### 4.2 Run Async Background Worker Runner `[SAFE-LOCAL]` `[REQUIRES-LOCAL-STACK]`
```powershell
# In a separate terminal with .venv activated:
.\.venv\Scripts\python -m apps.api.src.workers.runner
```

### 4.3 Run Next.js Frontend Development Server `[SAFE-LOCAL]`
```powershell
cd apps/web
npm run dev
```
- Web Application URL: `http://localhost:3000`

---

## 5. Automated Testing & Code Quality Commands

### 5.1 Backend Tests & Linters `[SAFE-LOCAL]`
```powershell
# 1. Run full backend unit and integration test suite
.\.venv\Scripts\pytest -v

# 2. Run specific test files (e.g., billing rules or invoice lifecycle)
.\.venv\Scripts\pytest tests/test_billing_rules.py -v
.\.venv\Scripts\pytest tests/test_billing_invoice_lifecycle.py -v
.\.venv\Scripts\pytest tests/test_billing_payments_and_allocation.py -v

# 3. Code formatting & linting with Ruff
.\.venv\Scripts\ruff check apps/api tests
.\.venv\Scripts\ruff format --check apps/api tests

# 4. Optional: Auto-fix lint and formatting violations [LOCAL-MUTATING]
.\.venv\Scripts\ruff check --fix apps/api tests
.\.venv\Scripts\ruff format apps/api tests

# 5. Static type checking with Mypy
.\.venv\Scripts\mypy apps/api tests
```

### 5.2 Frontend Tests & Type Checking `[SAFE-LOCAL]`
```powershell
cd apps/web

# 1. Strict TypeScript type check (no compilation output)
npm run typecheck

# 2. Next.js ESLint verification
npm run lint

# 3. Test production build compilation [LOCAL-MUTATING]
# (Note: Requires ~500 MB temporary disk space in apps/web/.next)
npm run build
```

---

## 6. Infrastructure as Code Validation & Security Scanning

### 6.1 Automated Dual IaC Validation Suite `[SAFE-LOCAL]`
Executes formatting check, syntax validation, TFLint, and tfsec across all 13 components:
```powershell
# Primary engine validation: OpenTofu v1.9.0
powershell -ExecutionPolicy Bypass -File infrastructure/terraform/scripts/validate_all.ps1 -IacTool tofu

# Secondary compatibility validation: HashiCorp Terraform >= 1.10.x
powershell -ExecutionPolicy Bypass -File infrastructure/terraform/scripts/validate_all.ps1 -IacTool terraform

# Bash equivalents (Linux / macOS):
# bash infrastructure/terraform/scripts/validate_all.sh tofu
# bash infrastructure/terraform/scripts/validate_all.sh terraform
```

### 6.2 Checkov Security & Compliance Scanning `[SAFE-LOCAL]`
Runs Checkov static analysis using the project baseline `.checkov.yaml`:
```powershell
# Scan all data tier modules
checkov -d infrastructure/terraform/modules/rds -d infrastructure/terraform/modules/redis -d infrastructure/terraform/modules/rabbitmq -d infrastructure/terraform/modules/storage --config-file infrastructure/terraform/.checkov.yaml

# Scan entire infrastructure tree
checkov -d infrastructure/terraform --config-file infrastructure/terraform/.checkov.yaml
```

### 6.3 Automated Compliance Test Suite `[SAFE-LOCAL]`
Runs the 76 custom Python compliance assertions verifying RLS isolation, KMS encryption, network sealing, and subnet usable IP math:
```powershell
.\.venv\Scripts\python -m pytest infrastructure/terraform/tests/test_compliance.py -v
```

---

## 7. Cloud Infrastructure Deployment Commands (AWS ap-south-1)

> [!CAUTION]
> The commands in this section interact with live AWS cloud resources. They must **NEVER** be run without explicit, written authorization from the Principal Cloud Architect.

### 7.1 Remote State Bootstrap `[REQUIRES-AWS-CREDS]` `[LIVE-INFRASTRUCTURE]`
Deploys the foundational S3 remote state bucket and DynamoDB locking table:
```powershell
cd infrastructure/terraform/bootstrap
tofu init
tofu plan -out=bootstrap.tfplan

# DESTRUCTIVE/CREATION: [DESTRUCTIVE-APPROVAL-REQUIRED]
# tofu apply bootstrap.tfplan
```

### 7.2 Environment Planning (e.g., Staging / Production) `[REQUIRES-AWS-CREDS]` `[LIVE-INFRASTRUCTURE]`
```powershell
cd infrastructure/terraform/environments/staging
# Or: cd infrastructure/terraform/environments/production

# Initialize environment with remote state
tofu init

# Generate speculative execution plan (Read-Only) [SAFE-LOCAL with AWS Creds]
tofu plan -var-file="terraform.tfvars" -out="staging.tfplan"

# Review the plan using Tofu show:
tofu show staging.tfplan

# DANGER: Applying infrastructure changes to AWS:
# [DESTRUCTIVE-APPROVAL-REQUIRED]
# Strictly forbidden in Phase 22F. Requires formal sign-off!
# tofu apply "staging.tfplan"
```
