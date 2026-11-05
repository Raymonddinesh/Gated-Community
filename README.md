# SocietySphere Platform

> **Enterprise Multi-Tenant Apartment Society Management Platform**  
> Architected for residential societies, gated communities, and housing cooperatives.

---

## 1. Project Overview

SocietySphere is a production-grade, multi-tenant Software-as-a-Service (SaaS) platform designed to handle society operations, resident governance, gate security, and immutable accounting ledgers.

### Core Architectural Pillars
- **Strict Multi-Tenancy**: Tenant data segregation backed by PostgreSQL Row-Level Security (RLS) and context-bound sessions.
- **Defense-in-Depth Security**: Authorization enforced strictly at the backend domain layer across 13 distinct personas.
- **Universal API Parity**: Next.js web application and future Flutter mobile apps consume the exact same versioned `/api/v1` REST endpoints.
- **Accounting & Financial Decoupling**: Standalone financial domain with a polymorphic `AccountingProvider` SPI supporting Native, Tally-integrated, Hybrid, and Spreadsheet accounting modes.
- **Accessibility & Inclusive Design**: Foundational support for **Easy Mode** (high contrast, large typography, enhanced hit areas) for elderly residents and non-tech-savvy gatekeepers.
- **Deterministic Financial Intelligence**: AI operates strictly within authorized, read-only boundaries and is strictly forbidden from computing financial totals.

---

## 2. Technology Stack

- **Backend**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x (async), Alembic
- **Frontend**: Next.js 14+ (App Router), React 18, TypeScript (strict mode), Tailwind CSS
- **Database**: PostgreSQL 16+ (with Row-Level Security)
- **Caching & Sessions**: Redis 7+
- **Message Broker & Background Jobs**: RabbitMQ (with `aio-pika`/Celery)
- **Object Storage**: S3-compatible storage (AWS S3 / MinIO)
- **Reverse Proxy & Infrastructure**: Nginx, Docker & Docker Compose

---

## 3. Quick Start & Prerequisites

### Prerequisites
- Python 3.12
- Node.js 20+ LTS
- Docker Desktop 24+
- Git 2.40+

### Setup Instructions
```powershell
# 1. Clone repository and initialize environment template
cp .env.example .env

# 2. Setup Python virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r apps/api/requirements-dev.txt

# 3. Setup Frontend dependencies
cd apps/web
npm install
cd ../..
```

---

## 4. Running the Platform

### Option A: Complete Local Environment via Docker Compose (Recommended)
```powershell
docker-compose up -d
```
All services (PostgreSQL, Redis, RabbitMQ, MinIO, API, Web) start with automated health probes.

### Option B: Standalone Development Mode
```powershell
# Start FastAPI backend (port 8000)
.\.venv\Scripts\uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000 --reload

# Start Next.js frontend (port 3000 in separate terminal)
cd apps/web
npm run dev
```

---

## 5. Health & Diagnostic Endpoints

The API exposes three standard probes:
- `GET http://localhost:8000/health`: Application status, environment, and uptime.
- `GET http://localhost:8000/health/live`: Container/Kubernetes process liveness probe.
- `GET http://localhost:8000/health/ready`: Backing infrastructure dependency check (PostgreSQL, Redis, RabbitMQ).
- `GET http://localhost:8000/api/v1/version`: API version and release metadata.
- **Swagger Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 6. Running Tests & Quality Gates

### Backend Suite (pytest, ruff, mypy)
```powershell
# Run unit & integration tests
.\.venv\Scripts\pytest -v

# Run code linter
.\.venv\Scripts\ruff check apps\api tests

# Run format check
.\.venv\Scripts\ruff format --check apps\api tests

# Run static type checking
.\.venv\Scripts\mypy apps\api tests
```

### Frontend Suite (TypeScript, ESLint, Next Build)
```powershell
cd apps/web

# TypeScript type check
npm run typecheck

# ESLint check
npm run lint

# Production build verification
npm run build
```

---

## 7. Database Migrations (Alembic)

```powershell
# Apply latest migrations
.\.venv\Scripts\alembic -c apps/api/alembic.ini upgrade head

# Rollback one migration
.\.venv\Scripts\alembic -c apps/api/alembic.ini downgrade -1
```

---

## 8. Architectural Documentation Reference

Detailed specifications and operations guides are maintained in the repository:
- [HANDOVER_GUIDE.md](file:///c:/SocApp/HANDOVER_GUIDE.md): Master Technical Project Handover & Architecture Guide
- [PENDING_TASKS.md](file:///c:/SocApp/PENDING_TASKS.md): Active Pending Tasks, Phase 22F Approvals & Future Roadmap
- [HANDOVER_COMMANDS.md](file:///c:/SocApp/HANDOVER_COMMANDS.md): Verified Local & Cloud Commands by Safety Classification
- [ARCHITECTURE.md](file:///c:/SocApp/ARCHITECTURE.md): Master System & Domain Architecture
- [PROJECT_ROADMAP.md](file:///c:/SocApp/PROJECT_ROADMAP.md): Project Milestones, Phase 22F Status & Roadmap
- [DEPLOYMENT_GUIDE.md](file:///c:/SocApp/DEPLOYMENT_GUIDE.md): Local, Docker & AWS Infrastructure Deployment Guide
- [SECURITY.md](file:///c:/SocApp/SECURITY.md): Multi-Tenant Security, RLS, KMS & Compliance Architecture
- [CONTRIBUTING.md](file:///c:/SocApp/CONTRIBUTING.md): Developer Onboarding, Branch Strategy & Quality Gates
- [scripts/handover/README.md](file:///c:/SocApp/scripts/handover/README.md): Lightweight Developer Handover Helper Scripts
- [docs/architecture/PHASE-1-BASELINE.md](file:///c:/SocApp/docs/architecture/PHASE-1-BASELINE.md): Phase 1 Engineering Scaffold Baseline
- [docs/architecture/REPOSITORY_STRUCTURE.md](file:///c:/SocApp/docs/architecture/REPOSITORY_STRUCTURE.md): Codebase Directory Topology
- [docs/adr/](file:///c:/SocApp/docs/adr/): Architectural Decision Records (ADR 001 - 011)
- [docs/api/API_STANDARDS.md](file:///c:/SocApp/docs/api/API_STANDARDS.md): API Semantics, Errors & RFC 7807 Guidelines
- [docs/security/SECURITY_BASELINE.md](file:///c:/SocApp/docs/security/SECURITY_BASELINE.md): Zero-Trust & Hardening Controls
- [docs/testing/TEST_STRATEGY.md](file:///c:/SocApp/docs/testing/TEST_STRATEGY.md): Testing Framework & QA Standards
- [docs/deployment/LOCAL_DEVELOPMENT.md](file:///c:/SocApp/docs/deployment/LOCAL_DEVELOPMENT.md): Developer Setup & Docker Workflows
