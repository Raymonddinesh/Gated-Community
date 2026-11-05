# SocietySphere — Technical Project Handover Guide

**Document Version:** 1.0.0  
**Date:** November 5, 2026  
**Author:** Senior DevOps Engineer & Technical Project Handover Architect  
**Audience:** Incoming Lead Developer, Solutions Architect, and DevSecOps Engineers  
**Target AWS Region:** `ap-south-1` (Mumbai)  
**Current Engineering Status:** Phase 22F Implementation Complete (Pending Final Principal Architect Approval)  
**Active Alembic Migration Head:** `20261102_0025_saas_billing_automation.py`  

---

## 1. Project Overview

SocietySphere is an enterprise-grade, multi-tenant Software-as-a-Service (SaaS) platform engineered for residential apartment societies, gated communities, and housing cooperatives. The platform streamlines:
- Administrative governance (committee meetings, resolutions, formal notices, resident polls).
- Gate and visitor physical security (visitor passes, entry/exit logging, staff attendance).
- Financial ledger management (automated maintenance fee generation, rule-based invoicing, GST calculation, payments, receipts, credit notes).
- Document and asset management (immutable tax invoices, society compliance certificates).
- Multi-channel resident communication (push notifications, SMS, email, WhatsApp, and voice accessibility).

The platform is designed for **long-term maintainability**, **defense-in-depth security**, and **strict tenant isolation** backed by PostgreSQL Row-Level Security (RLS).

---

## 2. Technology Stack

| Layer | Technologies | Version & Details |
|---|---|---|
| **Backend API** | Python, FastAPI, Pydantic v2, SQLAlchemy 2.x (async), Alembic | Python 3.12, strict asyncpg database driver |
| **Frontend Web** | Next.js (App Router), React, TypeScript, Tailwind CSS | Next.js 14+, React 18, strict TypeScript |
| **Relational Database** | PostgreSQL, Amazon RDS PostgreSQL | PostgreSQL 16.4 with Row-Level Security |
| **Connection Pooling** | Amazon RDS Proxy (PgBouncer-compatible) | Transaction pooling mode |
| **In-Memory Cache** | Redis, Amazon ElastiCache Redis | Redis 7.1 with in-transit TLS & KMS CMK |
| **Message Broker** | RabbitMQ, Amazon MQ for RabbitMQ | RabbitMQ 3.13, Multi-AZ cluster |
| **Object Storage** | Amazon S3 / MinIO (local sandbox) | SSE-KMS CMK, Object Lock, Glacier lifecycle |
| **Container Platform** | Docker, Amazon ECS on AWS Fargate, AWS ECR | Non-root containers, read-only root filesystems |
| **Load Balancing** | AWS Application Load Balancer (ALB) | Dual-stack, TLS 1.3, path-based routing |
| **Infrastructure as Code** | OpenTofu v1.9.0 & HashiCorp Terraform >= 1.10.x | Modular architecture, remote S3/DynamoDB state |
| **CI/CD Automation** | GitHub Actions | Linters, typecheckers, TFLint, tfsec, Checkov |

---

## 3. Application Architecture

```
                                 [ Web Browser / Mobile App ]
                                              │
                                              ▼ (HTTPS / TLS 1.3)
                               [ Application Load Balancer (ALB) ]
                                              │
                 ┌────────────────────────────┴────────────────────────────┐
                 │                                                         │
                 ▼ Path: /* (Default)                                      ▼ Path: /api/*
     [ Next.js Frontend Tasks ]                                [ FastAPI Backend API Tasks ]
     - App Router (SSR & Client)                               - Async HTTP Request Handlers
     - Persona-based navigation                                - JWT Authentication Guard
     - "Easy Mode" Accessibility                               - Dynamic Tenant Resolver
                                                               - Domain Service Layer
                                                                           │
                                                                           ▼ Async Job Events
                                                               [ Amazon MQ RabbitMQ 3.13 ]
                                                                           │
                                                                           ▼ Consumer Queue
                                                               [ Background Worker Tasks ]
                                                               - Runner: apps.api.src.workers.runner
                                                               - Invoice Generation & Penalties
                                                               - S3 PDF Rendering
                                                               - Notification Outbox
```

### Key Application Principles:
1. **Universal API Parity:** Next.js and future Flutter mobile apps communicate with the exact same `/api/v1` REST API.
2. **Deterministic Financial Calculation:** AI or automated models are strictly forbidden from performing financial ledger calculations; all totals and GST are computed deterministically by verified domain services.
3. **Graceful Worker Shutdown:** Background workers handle `SIGTERM`, drain active task loops, commit/rollback in-flight RabbitMQ messages, and release Redis leases before task termination.

---

## 4. Database Architecture & Multi-Tenant RLS

### 4.1 Multi-Tenancy Segregation
Every tenant table incorporates a `society_id` UUID foreign key referencing the `societies` table. Database-level data segregation is enforced through PostgreSQL Row-Level Security:
```sql
ALTER TABLE <tenant_table> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <tenant_table> FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON <tenant_table>
    AS RESTRICTIVE
    USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);
```

### 4.2 Transaction-Scoped Tenant Context
In `apps/api/src/database/session.py`, tenant context is set on the active SQLAlchemy session:
```python
await session.execute(
    text("SELECT set_config('app.current_society_id', :val, true)"),
    {"val": str(society_id)},
)
```
- The third argument (`is_local = true`) guarantees transaction-level scoping.
- When the transaction terminates (`COMMIT` or `ROLLBACK`), PostgreSQL automatically purges the variable.
- In conjunction with Amazon RDS Proxy configured with `session_pinning_filters = ["EXCLUDE_VARIABLE_SETS"]`, physical connections are safely reused across distinct tenants with zero leakage.

---

## 5. Authentication & Granular RBAC

- **Stateless Tokens:** Access tokens are signed JWTs with 15-minute expirations. Refresh tokens (7-day validity) are stored securely in HTTP-only cookies and validated against a Redis active-token denylist.
- **13 Distinct Personas:** Super Admin, Society Admin, Committee Member, Secretary, Treasurer, Auditor, Facility Manager, Gatekeeper, Resident Owner, Resident Tenant, Family Member, Daily Staff, and Background System Worker.
- **Server-Side Enforcement:** Privileges are validated inside domain service entry points; client-supplied claims are never trusted without server verification.

---

## 6. Billing Architecture (Phase 21 Baseline)

The billing subsystem (`apps/api/src/billing/`) manages:
- **Billing Config & Rules:** Flexible calculation formulas (flat rate, area-based sq.ft., slab-based utility consumption).
- **Tax Invoicing:** GST compliance (CGST + SGST or IGST) with sequential invoice numbering (`INV-YYYYMM-XXXX`).
- **Payment Allocation:** Strict FIFO allocation of incoming resident payments against overdue balances, interest penalties, and current dues.
- **Credit Notes:** Formal credit note adjustments with ledger balance preservation.
- **PDF Document Generation:** Immutable PDF invoices and receipts stored in S3.

---

## 7. Redis & RabbitMQ Architecture

### 7.1 Redis Distributed Locking & Leasing
- Used for distributed rate limiting, session token invalidation, and leader election across background workers.
- Implements atomic `SET NX PX` leasing with atomic Lua evaluation scripts (`COMPARE_AND_RENEW_LUA`, `COMPARE_AND_RELEASE_LUA`).
- In `apps/api/src/cache/leader_election.py`, Redis leasing is federated with PostgreSQL advisory locks (`pg_try_advisory_lock`) to guarantee single-master execution for recurring monthly billing runs.

### 7.2 RabbitMQ Message Topology
- **Topic Exchange:** `societysphere.jobs` (durable).
- **Direct Exchange:** `societysphere.dlx` (durable dead-letter exchange).
- **Queues:**
  - `billing-operations-queue`: Bound to `societysphere.jobs` with `billing.#` routing key. Configured with `x-max-priority: 10` for priority calculations.
  - `notification-outbox-queue`: Bound to `societysphere.jobs` with `notification.#` routing key.
  - `dead-letter-queue`: Bound to `societysphere.dlx` with `#` catch-all routing key.

---

## 8. S3 Document Storage & Regulatory Compliance

- Invoices, credit notes, and payment receipts are stored in a private S3 bucket (`societysphere-<env>-documents-<account_id>`).
- **Security:** Complete public access block, SSE-KMS encryption with Customer Managed Key, and S3 Bucket Keys enabled.
- **Presigned URLs:** Time-limited upload URLs (`PUT`, 300s expiry) and download URLs (`GET`, 60s expiry). S3 CORS configured for `https://*.societysphere.com`.
- **Statutory Audit Retention:** S3 Object Lock and lifecycle rules transition objects to `GLACIER` after 30 days and enforce a 7-year (2,555-day) retention window in accordance with Indian GST and corporate audit statutes.

---

## 9. Terraform/OpenTofu Infrastructure Architecture

Infrastructure is organized modularly under `infrastructure/terraform/`:
```
infrastructure/terraform/
├── bootstrap/                    # S3 remote state bucket & DynamoDB lock table
├── modules/
│   ├── networking/               # VPC, 3 Public, 3 App, 3 Data subnets, NAT, VPC Endpoints, Flow Logs
│   ├── security/                 # KMS CMKs, Security Groups, IAM Roles & Policies
│   ├── storage/                  # S3 Private Documents Bucket, Object Lock, CORS, Lifecycle
│   ├── monitoring/               # CloudWatch Log Groups & Retention
│   ├── rds/                      # RDS PostgreSQL 16 Multi-AZ, Parameter Group, RDS Proxy
│   ├── redis/                    # ElastiCache Redis 7.1 Replication Group
│   ├── rabbitmq/                 # Amazon MQ RabbitMQ 3.13 Multi-AZ Cluster
│   └── ecs/                      # ECR, ALB, ECS Fargate Cluster, Task Definitions, Autoscaling
└── environments/
    ├── dev/                      # Cost-optimized single-AZ development environment
    ├── qa/                       # Multi-AZ QA regression environment
    ├── staging/                  # Production mirror pre-release environment
    └── production/               # Production environment with strict deletion protection & 35-day backup
```

---

## 10. CI/CD Workflows (GitHub Actions)

Located under `.github/workflows/`:
1. `infrastructure-validate.yml`: Runs on PRs touching `infrastructure/**`. Validates OpenTofu formatting, syntax, TFLint, and tfsec.
2. `infrastructure-terraform-compat.yml`: Validates HashiCorp Terraform >= 1.10.x compatibility.
3. `security-scan.yml`: Executes Checkov static security analysis across all infrastructure modules.

---

## 11. Environment Configuration & Local Setup

1. Copy `.env.example` to `.env`.
2. Review local connection strings.
3. Start full stack via `docker-compose up -d`.
4. Apply migrations: `alembic -c apps/api/alembic.ini upgrade head`.
5. Access web UI at [http://localhost:3000](http://localhost:3000) and Swagger docs at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## 12. Testing Instructions

```powershell
# Backend unit & integration tests
pytest -v

# Linter & type checks
ruff check apps/api tests
mypy apps/api tests

# Frontend quality checks
cd apps/web
npm run typecheck
npm run lint

# Infrastructure compliance & validation tests
cd ../..
python -m pytest infrastructure/terraform/tests/test_compliance.py -v
powershell -ExecutionPolicy Bypass -File infrastructure/terraform/scripts/validate_all.ps1 -IacTool tofu
```

---

## 13. Critical Phase 22F Handover Status & Outstanding Review Items

> [!IMPORTANT]
> **Phase 22F implementation is reported complete and empirically verified (144 Checkov checks passed, 76 compliance tests passed, 13/13 dual IaC passed), but FINAL PRINCIPAL ARCHITECT APPROVAL IS PENDING.**
>
> The incoming developer or team **MUST NOT** consider Phase 22F locked or proceed with Phase 22G until the following outstanding architecture review items are formally audited and approved:

### Outstanding Architecture Review Items:
1. **RDS Proxy PostgreSQL Session-Pinning Compatibility:**
   - Verify whether asyncpg connection pool parameters (e.g. `statement_cache_size = 0`) fully prevent session pinning during high query concurrency.
   - Audit the behavior of custom extensions or setting overrides under transaction pooling.
2. **RDS Proxy versus PgBouncer Architecture Decision:**
   - Formally document the trade-off decision between managed AWS RDS Proxy vs self-hosted PgBouncer on ECS Fargate (pricing, IAM auth, latency, scaling characteristics).
3. **Live Proxy-Path Tenant RLS Isolation Verification:**
   - Execute an empirical, end-to-end integration test across a real RDS Proxy endpoint ensuring that `SELECT set_config('app.current_society_id', :val, true)` with `is_local = true` completely clears tenant state upon connection reuse, preventing cross-tenant data leakage.
4. **Seven-Year S3 Object Lock Compliance Mode Retention Review:**
   - Evaluate whether Compliance Mode or Governance Mode should be utilized in non-production environments (dev/qa/staging).
   - Warning: Compliance Mode prevents deletion even by the AWS account root user during the 7-year retention period.
5. **RabbitMQ Classic Mirrored versus Quorum Queue Decision:**
   - Re-verify Amazon MQ RabbitMQ 3.13 classic queue support given the requirement for message priority (`x-max-priority: 10`) in billing operations.
6. **Mandatory Production Redis Authentication Verification:**
   - Verify token-based Redis authentication configuration and Secrets Manager secret rotation procedures for production clusters.

---

## 14. Remaining Project Roadmap

| Phase | Title | Scope & Objectives |
|---|---|---|
| **Phase 22G** | Observability, Backup & Disaster Recovery | CloudWatch Dashboards, Metric Alarms, SNS alerts, AWS Backup policies, chaos failover runbooks. |
| **Phase 22H** | Security Assessment & Hardening | WAFv2 rules, penetration testing, GuardDuty, AWS Config rules, automated KMS key rotation. |
| **Phase 22I** | Performance & Scalability | High-concurrency load testing (k6/Locust), DB index tuning, autoscaling calibration under burst traffic. |
| **Phase 22J** | UAT & Commercial Launch | Production staging cutover, Route 53 health routing, pilot society onboarding, commercial go-live. |

*All future phases must follow the Four-Stage Lifecycle: Implementation → Automated Validation → Principal Architect Review → Sign-Off & Lock.*

---

## 15. Key Handover References & Verified Commands

- **[PENDING_TASKS.md](file:///c:/SocApp/PENDING_TASKS.md)**: Detailed tracking table for Phase 22F pending approvals and implementation plans for Phases 22G–22J.
- **[HANDOVER_COMMANDS.md](file:///c:/SocApp/HANDOVER_COMMANDS.md)**: Exhaustive catalog of verified local development, database migration, testing, and cloud infrastructure commands categorized by safety level.
- **[scripts/handover/README.md](file:///c:/SocApp/scripts/handover/README.md)**: Lightweight, non-destructive helper scripts for developer environment auditing and status verification.
- **[PROJECT_ROADMAP.md](file:///c:/SocApp/PROJECT_ROADMAP.md)**: Master milestone roadmap and phase completion criteria.
- **[DEPLOYMENT_GUIDE.md](file:///c:/SocApp/DEPLOYMENT_GUIDE.md)**: Local, Docker Compose, and AWS infrastructure deployment runbooks.
- **[SECURITY.md](file:///c:/SocApp/SECURITY.md)**: Multi-tenant security architecture, RLS isolation policies, and compliance controls.
- **[CONTRIBUTING.md](file:///c:/SocApp/CONTRIBUTING.md)**: Branching strategy, Conventional Commits standard, and PR quality gates.
