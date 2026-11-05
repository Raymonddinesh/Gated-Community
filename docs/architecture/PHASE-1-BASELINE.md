# Phase 1 Baseline & Architecture Alignment

## 1. Current Repository State
- **Workspace**: `c:\SocApp`
- **Initial State**: Pristine directory initialized in Phase 0 with architecture specifications (`ARCHITECTURE.md`) and 10 Architectural Decision Records (`docs/adr/ADR-001` through `ADR-010`).
- **Git**: Initialized at Phase 1 start.
- **Pre-existing Code**: Zero business logic, zero prototype code, zero database schemas created yet.

## 2. Existing Technology Stack & Specifications
- **Operating Environment**: Windows OS, Node.js v24.13.0, npm 11.6.2, Python 3.11.0, Docker 29.1.5, Git 2.43.0.
- **Frontend Target**: Next.js 14+ (React, TypeScript strict mode, Tailwind CSS).
- **Backend Target (Phase 1 Approved Directive)**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x async, Alembic.
- **Database**: PostgreSQL 16+ with Row-Level Security (RLS) support.
- **Caching & Sessions**: Redis 7+.
- **Background Jobs**: RabbitMQ (with Celery/aio-pika abstraction) & Redis.
- **Object Storage**: S3-compatible API (AWS S3 / MinIO).
- **Architecture Pattern**: Modular Monolith, Clean Architecture (Domain, Application, Infrastructure layers).

## 3. Technology Stack Alignment & Conflict Resolution (ADR-011)
- **Observed Variance**: During initial Phase 0 exploratory drafting, ADR-002 mentioned NestJS. The Phase 1 formal architecture directive mandates Python + FastAPI with Pydantic v2 and SQLAlchemy 2.x async.
- **Resolution**: Formally codified via [ADR-011: Backend Framework Alignment to FastAPI & Python](file:///c:/SocApp/docs/adr/ADR-011-backend-framework-fastapi.md). Python and FastAPI provide world-class async I/O performance, native Pydantic v2 type safety, direct synergy with financial/accounting calculation modules and future AI/voice intelligence layers, and pristine clean architecture modularity.
- **Zero Impact on Core Principles**: Multi-tenancy, Row-Level Security, append-only financial ledgers, auditability, API parity with future Flutter mobile clients, and 13-role RBAC/ABAC remain 100% intact.

## 4. Missing Foundation Components (To Be Built in Phase 1)
1. **Monorepo Directory Layout**: Clean separation into `/apps/api`, `/apps/web`, `/packages`, `/infrastructure`, `/docs`, `/tests`.
2. **Backend Engineering Scaffold**:
   - FastAPI application startup/shutdown lifespan.
   - Pydantic v2 Settings configuration management with `.env.example`.
   - Async database engine & session dependency via SQLAlchemy 2.x.
   - Alembic migration environment with non-destructive versioning.
   - Async Redis client connection management.
   - RabbitMQ connection & publisher/consumer abstraction.
   - S3-compatible object storage provider abstraction.
   - Centralized RFC 7807 problem details exception handling.
   - Structured JSON logging with request correlation IDs (`X-Correlation-ID` / `X-Request-ID`).
   - Baseline security middleware (CORS, trusted host, secure headers, rate limiter foundation).
   - Health endpoints (`/health`, `/health/live`, `/health/ready`).
   - Versioned API router prefix (`/api/v1`).
3. **Frontend Engineering Scaffold**:
   - Next.js project with TypeScript strict mode, Tailwind CSS.
   - Accessible UI design system primitives (Button, Input, Select, Modal, Card, Table, Badge, Alert, Form, Page container, Loading indicator).
   - Mode switching foundations (Easy Mode, Standard Mode, Admin Mode).
   - API client abstraction, global layout, error boundary, loading and empty states.
4. **Local DevOps & Docker**:
   - `docker-compose.yml` orchestrating API, Web, PostgreSQL, Redis, RabbitMQ, and MinIO.
   - Multi-stage Dockerfiles for backend and frontend.
5. **Testing & CI**:
   - Pytest suite for backend health, config, correlation ID, and error handling.
   - Frontend validation and testing framework.
   - GitHub Actions CI workflow.

## 5. Risks Discovered & Mitigations
- **Risk 1: Multi-Tenant Leakage**: If developer queries bypass tenant boundaries, cross-tenant data leaks can occur.
  - *Mitigation*: Architecture mandates PostgreSQL RLS and strict Async Context / dependency injection of tenant ID from Phase 2 onward.
- **Risk 2: Premature Business Logic Creep**: Risk of accidental early implementation of resident, billing, or gate entities.
  - *Mitigation*: Strict gatekeeping. Phase 1 implements only foundational infrastructure (connectivity, health checks, configs, abstract providers). Zero business tables or routes.
- **Risk 3: Configuration Secret Leakage**: Accidental exposure of credentials.
  - *Mitigation*: `.gitignore` excludes `.env*` files except `.env.example`. Structured logger scrubs sensitive headers and secrets.
