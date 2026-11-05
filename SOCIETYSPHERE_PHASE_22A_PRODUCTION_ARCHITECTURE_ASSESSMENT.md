# SOCIETYSPHERE — PHASE 22A
# PRODUCTION INFRASTRUCTURE & ARCHITECTURE ASSESSMENT

**Document Version:** 1.0.0  
**Status:** READY FOR ARCHITECT REVIEW  
**Date:** November 2026  
**Author:** Principal Cloud Architect, AWS Solutions Architect, DevSecOps Lead, Production Reliability Engineer  
**Target Environment:** AWS `ap-south-1` (Mumbai, India)  
**Alembic Migration Head:** `0025_saas_billing_automation`  
**Application Scope:** SocietySphere Multi-Tenant SaaS (Web, API, Background Workers, PostgreSQL, Redis, RabbitMQ, S3)

---

## EXECUTIVE SUMMARY

SocietySphere has completed Phases 1 through 21 (including 21A through 21E.6 Stage 4), establishing a hardened, multi-tenant residential management SaaS platform with row-level security (RLS), an automated billing engine, 7-day dunning lifecycle, grace-period suspension, transactional outboxes, and distributed worker supervision.

The objective of **Phase 22A** is to deliver a definitive, production-grade, secure, scalable, and cost-conscious AWS deployment architecture. SocietySphere processes sensitive financial transactions (maintenance dues, GST invoicing, Razorpay settlements) and personal identifiable information (PII) of residential owners and tenants. Consequently, the architecture strictly adheres to Indian regulatory compliance (Digital Personal Data Protection Act - DPDP 2023, RBI Payment Data Localization Guidelines, GST Statutory Invoicing Rules) and aligns with the **ISO/IEC 27001:2022** Information Security Standard.

This assessment evaluates the existing codebase, identifies production readiness gaps, models operational capacity, compares three real-world AWS cost profiles, formalizes four key Architectural Decision Records (ADRs), and defines the implementation roadmap for Phases 22B through 22F.

---

## TABLE OF CONTENTS

1. [Existing Application Architecture Findings](#1-existing-application-architecture-findings)
2. [Current Deployment Readiness Analysis](#2-current-deployment-readiness-analysis)
3. [Recommended AWS Architecture](#3-recommended-aws-architecture)
4. [Architecture Diagrams](#4-architecture-diagrams)
5. [Network Architecture (VPC, Subnets, Routing, Security Groups)](#5-network-architecture)
6. [Frontend & Backend Deployment Strategy](#6-frontend--backend-deployment-strategy)
7. [Database & Messaging Architecture](#7-database--messaging-architecture)
8. [Security Architecture & DevSecOps](#8-security-architecture--devsecops)
9. [Environment Strategy (Dev, QA, Staging, Prod)](#9-environment-strategy)
10. [CI/CD Strategy & Release Engineering](#10-cicd-strategy--release-engineering)
11. [High Availability & Disaster Recovery (HA/DR)](#11-high-availability--disaster-recovery)
12. [Initial Capacity & Scaling Model](#12-initial-capacity--scaling-model)
13. [AWS Cost Estimation Scenarios](#13-aws-cost-estimation-scenarios)
14. [ISO 27001:2022 Security Alignment Matrix](#14-iso-270012022-security-alignment-matrix)
15. [Architectural Decision Records (ADRs)](#15-architectural-decision-records-adrs)
16. [Infrastructure Implementation Roadmap (Phases 22B–22F)](#16-infrastructure-implementation-roadmap)
17. [Production-Readiness Gaps & Remediation Plan](#17-production-readiness-gaps--remediation-plan)
18. [Final Status & Recommendations](#18-final-status--recommendations)

---

## 1. EXISTING APPLICATION ARCHITECTURE FINDINGS

A comprehensive audit of `c:\SocApp` was conducted to establish empirical requirements for AWS cloud architecture.

### 1.1 Frontend Architecture (`apps/web`)
* **Framework:** Next.js `14.1.4` (React `18.2.0`, React DOM `18.2.0`, TypeScript `5.4.3`).
* **Router Paradigm:** Next.js App Router (`apps/web/src/app`).
* **Build Configuration:** Configured with `output: 'standalone'` in `apps/web/next.config.js`. This creates a self-contained Node.js server inside `.next/standalone` which bundles required `node_modules` without requiring the full workspace footprint.
* **Styling & Assets:** Tailwind CSS `3.4.1`, PostCSS `8.4.38`, Lucide React icons. Static assets served from `apps/web/public`.
* **API Client & Networking:** `apps/web/src/lib/api-client.ts` implements an Axios/Fetch abstraction that automatically attaches:
  * `X-Correlation-ID`: Client-generated UUIDv4 for distributed request tracing.
  * `X-Society-ID`: Active tenant identifier for multi-tenant context resolution.
  * `Authorization: Bearer <token>`: JWT authentication header.
* **Session Management:** `apps/web/src/lib/auth-client.ts` manages dual-token authentication:
  * Access Token: Short-lived (15 minutes), stored in client memory / `localStorage`.
  * Refresh Token: Long-lived (7 days), exchanged via `/api/v1/auth/refresh`.

### 1.2 Backend API Architecture (`apps/api`)
* **Framework:** FastAPI `^0.110.0`, Pydantic v2 `^2.6.0`, Pydantic Settings `^2.2.0`.
* **Python Runtime:** Python 3.12 (standardized in Dockerfile.api and CI).
* **ASGI Server:** Uvicorn `^0.28.0` with standard ASGI interface.
* **Database Driver & ORM:** SQLAlchemy `^2.0.28` (asyncio) with `asyncpg ^0.29.0`.
* **Connection Pooling:** In-app connection pool configured in `apps/api/src/database/session.py`:
  * `DATABASE_POOL_SIZE = 10`
  * `DATABASE_MAX_OVERFLOW = 20`
  * `DATABASE_POOL_TIMEOUT = 30`
* **Multi-Tenancy & Data Isolation:** Native PostgreSQL Row-Level Security (RLS). Every tenant query executes with:
  ```sql
  SELECT set_config('app.current_society_id', :society_id, true);
  ```
  with `is_local = true` to restrict scope to the current transaction. All 19 tenant tables enforce `FORCE ROW LEVEL SECURITY`.
* **Health Probes:** Implemented in `apps/api/src/api/v1/endpoints/health.py`:
  * `GET /health`: Basic metadata (app name, version, environment).
  * `GET /health/live`: Liveness probe (returns 200 OK immediately).
  * `GET /health/ready`: Deep readiness probe checking PostgreSQL connection, Redis ping, and RabbitMQ channel availability. In staging and production, any dependency outage returns `503 Service Unavailable`.

### 1.3 Background Workers & Distributed Topology
* **Entry Point:** `python -m apps.api.src.workers.runner`.
* **Concurrency Engine:** Python `asyncio.TaskGroup` running 4 independently supervised tasks:
  1. `DistributedSchedulerLeader`: Runs leader election using atomic Redis leases (`SET NX EX`) backed by persistent PostgreSQL 64-bit transaction-independent session advisory locks (`pg_try_advisory_lock`). Schedules billing period rolls (hourly) and dunning evaluations (every 4 hours).
  2. `BillingOperationsConsumer`: Consumes asynchronous billing tasks from RabbitMQ (`billing.operations` queue).
  3. `NotificationOutboxDispatcher`: Sweeps `notification_outbox` table and publishes to RabbitMQ or external providers (polling interval 5 seconds).
  4. `StaleJobSweeper`: Identifies and recovers stuck processing jobs (runs hourly).
* **Broker & Queue Topology:** `aio-pika ^9.4.1` connecting over AMQP 0-9-1. Declares persistent exchanges (`societysphere.events`, `billing.direct`), durable queues, and quorum queue characteristics with dead-letter exchange (DLX) routing.

### 1.4 Object Storage & External Services
* **Storage Protocol:** `aioboto3 ^12.3.0` implementing S3-compatible API. Bucket configured via `OBJECT_STORAGE_BUCKET` (default: `societysphere-documents`). Used for maintenance invoices (PDFs generated via `reportlab ^4.0.0`), payment receipts, and resident KYC uploads.
* **Email & SMS:** Configurable provider via `EMAIL_PROVIDER`:
  * `'SES'`: Amazon Simple Email Service (production standard).
  * `'SMTP'`: Standard SMTP gateway.
  * `'MOCK'`: Local testing sink.
* **Payment Gateway:** Multi-provider factory abstraction (`PaymentGatewayFactory`) with Razorpay integration (`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`) and mock providers for automated testing.

### 1.5 Containerization & Packaging
* **Backend Image (`infrastructure/docker/Dockerfile.api`):**
  * Multi-stage build on `python:3.12-slim`.
  * Security: Drops root, creates unprivileged system user `appuser:appgroup` (`UID 1001`, `GID 1001`).
  * Dependencies: Installs build tools (`gcc`, `libpq-dev`), copies virtual environment, strips build tooling from final image.
  * Exposed Port: 8000.
* **Frontend Image (`infrastructure/docker/Dockerfile.web`):**
  * Multi-stage build on `node:20-alpine`.
  * Security: Runs as non-root `nextjs:nodejs` (`UID 1001`, `GID 1001`).
  * Optimization: Utilizes `.next/standalone` output; copies static files to `public` and `.next/static`.
  * Exposed Port: 3000.
* **Reverse Proxy (`infrastructure/nginx/nginx.conf`):**
  * Implements rate limiting (`limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s`).
  * Injects security headers (`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`).
  * Forwards `/api/` and `/health` to backend (port 8000) and `/` to frontend (port 3000).

---

## 2. CURRENT DEPLOYMENT READINESS ANALYSIS

| Dimension | Current State | Production Assessment | Gap / Action Required |
| :--- | :--- | :--- | :--- |
| **Twelve-Factor Compliance** | High | All configuration parameterized via environment variables; stateless HTTP processes; backing services treated as attached resources. | Fully compliant. |
| **Container Security** | High | Non-root users (`UID 1001`), multi-stage builds, minimal base images (Alpine/Debian slim). | Add automated container image vulnerability scanning in CI (Trivy / ECR basic scanning). |
| **Health & Observability** | High | Native `/health/ready` verifying DB, Redis, and RabbitMQ. JSON structured logs with correlation IDs. | Connect metrics to CloudWatch / OpenTelemetry; define synthetic canary monitors. |
| **Data Isolation & RLS** | Excellent | Multi-tenant RLS enforced at DB level on 19 tables with `FORCE ROW LEVEL SECURITY`. Tested under multi-process concurrency. | Standardize connection pooler reset (`DISCARD ALL`) to avoid session state leaks. |
| **Connection Pooling** | Medium | In-app pooling (asyncpg: 10 connections + 20 overflow). Multiple containers could exhaust PostgreSQL connection limit. | **Critical Gap:** Introduce PgBouncer between ECS tasks and RDS PostgreSQL. |
| **Secrets Management** | Low (Dev) | Plaintext `.env` / environment variables in local Docker Compose. | **Critical Gap:** Migrate to AWS Secrets Manager with dynamic retrieval at container startup. |
| **Static Edge Caching** | Low | Nginx proxies all requests directly to Node.js container; no edge caching. | **High Gap:** Place AWS CloudFront in front of ALB to cache Next.js static assets (`/_next/static/*`). |
| **Statutory Data Retention** | Medium | Local MinIO object storage without object lock or lifecycle policies. | **Regulatory Gap:** Configure AWS S3 Object Lock (Compliance mode) for GST invoices (6-year retention). |
| **Infrastructure-as-Code** | None | Local Docker Compose only. No Terraform / OpenTofu or CloudFormation. | **Critical Gap:** Author modular Terraform/OpenTofu configurations (Phase 22B). |

---

## 3. RECOMMENDED AWS ARCHITECTURE

### 3.1 AWS Region Selection: `ap-south-1` (Mumbai, India)
**Justification:**
1. **Regulatory Compliance:** Under the **Digital Personal Data Protection Act (DPDP) 2023** and **Reserve Bank of India (RBI)** payment directive (Circular DPSS.CO.OD No. 2785/06.11.001/2017-18), financial data and sensitive resident personal records must be stored within Indian borders.
2. **Latency:** SocietySphere users (residents, security guards, society managers, treasurers) are located in Tier 1 and Tier 2 Indian metropolitan areas (Mumbai, Pune, Bengaluru, NCR, Hyderabad, Chennai). `ap-south-1` delivers round-trip latencies of 12–35 ms across India.
3. **Availability Zones:** Mumbai provides 3 physically separated Availability Zones (`ap-south-1a`, `ap-south-1b`, `ap-south-1c`) with redundant power, networking, and flood/seismic mitigation, enabling true Multi-AZ fault tolerance.

### 3.2 Target AWS Services Topology
* **Ingress & Edge Security:**
  * **AWS CloudFront:** Global Content Delivery Network caching static assets (`/_next/static/*`, images) with Edge TLS 1.3 termination.
  * **AWS WAF v2:** Web Application Firewall attached to CloudFront and ALB, enforcing OWASP Top 10 mitigation, SQL injection protection, and IP-based rate limiting on auth endpoints.
  * **AWS Certificate Manager (ACM):** Public TLS certificates with automated DNS-01 validation and annual zero-touch renewal.
  * **AWS Application Load Balancer (ALB):** Multi-AZ Layer 7 reverse proxy routing `/api/*` and `/health*` to API target groups, and default traffic to Web target groups.
* **Compute Services (Serverless Containers):**
  * **Amazon Elastic Container Service (ECS) with AWS Fargate:**
    * Eliminates EC2 OS maintenance, AMI patching, and container breakout host privilege escalation.
    * Three logically separated ECS Services:
      1. `societysphere-web`: Next.js 14 Standalone frontend.
      2. `societysphere-api`: FastAPI backend API.
      3. `societysphere-workers`: Background worker tasks (scheduler, outbox, consumer).
  * **Amazon Elastic Container Registry (ECR):** Private container registry with immutable tag immutability and continuous vulnerability scanning.
* **Database & Caching Layer:**
  * **Amazon RDS for PostgreSQL 16 (Multi-AZ):** Synchronous replication across two AZs with automatic DNS failover (< 60s), gp3 storage with provisioned IOPS, automated backups (35 days), and Point-In-Time Recovery (PITR).
  * **PgBouncer (Containerized on ECS Fargate):** Sits in front of RDS PostgreSQL in `transaction` pooling mode, handling high-concurrency connection multiplexing while preserving RLS transaction hygiene.
  * **Amazon ElastiCache for Redis 7.x (Multi-AZ with Auto-failover):** In-memory cache for session state, API rate limiting, and atomic scheduler distributed lease management (`SET NX EX`).
* **Message Broker:**
  * **Amazon MQ for RabbitMQ (Multi-AZ 3-Node Quorum Cluster):** Managed RabbitMQ broker. Preserves 100% compatibility with existing `aio-pika` AMQP 0-9-1 client code, quorum queue persistence, and DLX routing without code refactoring.
* **Storage & Static Documents:**
  * **Amazon S3:** Private bucket with SSE-KMS Customer Managed Key encryption, bucket versioning, public access block, S3 Lifecycle policies, and S3 Object Lock for statutory invoice preservation.
* **Security, Secrets & Management:**
  * **AWS Secrets Manager:** Centralized vault for database credentials, JWT keys, and Razorpay secrets. Injected directly into ECS tasks at launch via IAM Task Execution roles.
  * **AWS Key Management Service (KMS):** Dedicated Customer Managed Keys (CMKs) with automatic annual key rotation for S3, RDS, Secrets Manager, and CloudWatch logs.
  * **AWS IAM:** Strict least-privilege roles, separating Task Execution Roles (infrastructure pull) from Task Roles (application runtime permissions).
  * **AWS CloudTrail & Amazon GuardDuty:** Continuous audit logging and ML-based threat detection across all API calls and network interfaces.
  * **Amazon CloudWatch:** Centralized logs, Container Insights, alarms, and metric filters.

---

## 4. ARCHITECTURE DIAGRAMS

### 4.1 High-Level End-to-End System Topology
```mermaid
flowchart TD
    subgraph Users ["Client Layer"]
        ResidentMobile["Mobile App / Resident Browser"]
        SocietyAdmin["Society Admin / Treasurer"]
        SuperAdmin["SaaS Platform Admin"]
    end

    subgraph Edge ["AWS Edge & Perimeter Security (ap-south-1)"]
        Route53["Amazon Route 53 (DNS / Anycast)"]
        CloudFront["Amazon CloudFront CDN (Edge Cache)"]
        WAF["AWS WAF v2 (OWASP Rules / Rate Limiting)"]
    end

    subgraph VPC ["AWS Virtual Private Cloud (10.0.0.0/16)"]
        subgraph PublicSubnets ["Public Subnets (AZ-a, AZ-b, AZ-c)"]
            ALB["Application Load Balancer (ACM TLS 1.3)"]
            NAT_GW["Managed NAT Gateways (Multi-AZ)"]
        end

        subgraph PrivateAppSubnets ["Private Application Subnets (AZ-a, AZ-b, AZ-c)"]
            ECS_Web["ECS Fargate: Web Frontend (Next.js 14)"]
            ECS_API["ECS Fargate: Backend API (FastAPI)"]
            ECS_Workers["ECS Fargate: Background Workers (TaskGroup)"]
            PgBouncer["ECS Fargate: PgBouncer (Transaction Pooler)"]
        end

        subgraph IsolatedDataSubnets ["Isolated Data Subnets (AZ-a, AZ-b, AZ-c)"]
            RDS_PG["Amazon RDS PostgreSQL 16 (Multi-AZ Primary & Standby)"]
            ElastiCache["Amazon ElastiCache Redis 7.x (Multi-AZ Cluster)"]
            AmazonMQ["Amazon MQ RabbitMQ (3-Node Quorum Cluster)"]
        end
    end

    subgraph ExternalAWS ["Managed AWS Cloud Services"]
        S3["Amazon S3 Bucket (SSE-KMS / Object Lock / Versioning)"]
        SecretsMgr["AWS Secrets Manager (Auto-Rotation)"]
        KMS["AWS KMS (Customer Managed Keys)"]
        SES["Amazon SES (Transactional Email Dispatch)"]
        CW["Amazon CloudWatch (Logs / Container Insights / Alarms)"]
    end

    subgraph ThirdParty ["External Gateways"]
        Razorpay["Razorpay Payment Gateway API"]
        SMS["SMS / WhatsApp Notification Gateway"]
    end

    %% Edge Traffic
    Users --> Route53
    Route53 --> WAF
    WAF --> CloudFront
    CloudFront -- "Static Assets (/_next/static/*)" --> CloudFront
    CloudFront -- "Dynamic Page Requests" --> ALB
    WAF -. "Inspects & Shields" .-> ALB

    %% ALB Routing
    ALB -- "Path: /* (Web App)" --> ECS_Web
    ALB -- "Path: /api/* & /health*" --> ECS_API

    %% App Layer Communication
    ECS_Web -- "Internal API Calls (Headers: X-Society-ID)" --> ECS_API
    ECS_API --> PgBouncer
    ECS_Workers --> PgBouncer
    PgBouncer --> RDS_PG
    
    ECS_API -- "Cache / Rate Limit / Tokens" --> ElastiCache
    ECS_Workers -- "Leader Lease (SET NX EX)" --> ElastiCache
    
    ECS_API -- "Publish Tasks (AMQP)" --> AmazonMQ
    AmazonMQ -- "Consume Tasks (aio-pika)" --> ECS_Workers
    
    ECS_API -- "Read/Write KYC & Invoices" --> S3
    ECS_Workers -- "Generate Invoices & Receipts (PDF)" --> S3
    
    %% Egress & Outbound
    ECS_Workers -- "Dispatch Webhooks / Emails" --> NAT_GW
    NAT_GW --> Razorpay
    NAT_GW --> SMS
    ECS_Workers --> SES

    %% Security & Management
    SecretsMgr -. "Secret Injection" .-> ECS_API
    SecretsMgr -. "Secret Injection" .-> ECS_Workers
    KMS -. "Decryption Keys" .-> RDS_PG
    KMS -. "Decryption Keys" .-> S3
    ECS_API -. "Structured Logs" .-> CW
    ECS_Workers -. "Structured Logs" .-> CW
```

### 4.2 Multi-AZ Network Subnet Topology
```mermaid
flowchart LR
    subgraph Region ["AWS Region: ap-south-1 (Mumbai)"]
        subgraph AZ_A ["Availability Zone: ap-south-1a"]
            Pub_A["Public Subnet A (10.0.1.0/24)<br>• ALB Node A<br>• NAT Gateway A"]
            App_A["Private App Subnet A (10.0.10.0/22)<br>• ECS Web Task A<br>• ECS API Task A<br>• ECS Worker Task A<br>• PgBouncer A"]
            Data_A["Isolated Data Subnet A (10.0.30.0/24)<br>• RDS PostgreSQL (Primary)<br>• ElastiCache (Primary Node)<br>• Amazon MQ (Broker 1)"]
        end

        subgraph AZ_B ["Availability Zone: ap-south-1b"]
            Pub_B["Public Subnet B (10.0.2.0/24)<br>• ALB Node B<br>• NAT Gateway B"]
            App_B["Private App Subnet B (10.0.14.0/22)<br>• ECS Web Task B<br>• ECS API Task B<br>• ECS Worker Task B<br>• PgBouncer B"]
            Data_B["Isolated Data Subnet B (10.0.31.0/24)<br>• RDS PostgreSQL (Standby)<br>• ElastiCache (Replica Node)<br>• Amazon MQ (Broker 2)"]
        end

        subgraph AZ_C ["Availability Zone: ap-south-1c"]
            Pub_C["Public Subnet C (10.0.3.0/24)<br>• ALB Node C<br>• NAT Gateway C"]
            App_C["Private App Subnet C (10.0.18.0/22)<br>• ECS Web Task C<br>• ECS API Task C<br>• ECS Worker Task C"]
            Data_C["Isolated Data Subnet C (10.0.32.0/24)<br>• Amazon MQ (Quorum Witness / Broker 3)"]
        end
    end

    Pub_A -.-> App_A
    Pub_B -.-> App_B
    Pub_C -.-> App_C
    App_A -.-> Data_A
    App_B -.-> Data_B
    App_C -.-> Data_C
```

### 4.3 Multi-Tenant Isolation & Security Boundary
```mermaid
flowchart TD
    subgraph ClientScope ["Client Request Scope"]
        Req["Inbound HTTP Request<br>Header: Authorization: Bearer &lt;JWT&gt;<br>Header: X-Society-ID: &lt;society_uuid&gt;"]
    end

    subgraph API_Scope ["FastAPI Container Boundary (Non-root appuser)"]
        AuthMiddleware["Auth Middleware<br>1. Validates JWT Signature (RS256)<br>2. Verifies Society Membership"]
        ContextSetter["Tenant Context Injector<br>Set request.state.society_id"]
    end

    subgraph DB_Scope ["Database Isolation Boundary (PostgreSQL 16)"]
        TxBegin["Begin DB Transaction"]
        RLS_Config["Execute: SELECT set_config('app.current_society_id', :id, true)"]
        TableAccess["Query Target Table (e.g., invoices, payments, residents)"]
        RLS_Filter{"PostgreSQL Engine Evaluates RLS Policy:<br>society_id = current_setting('app.current_society_id')::uuid"}
        TxCommit["Commit Transaction<br>(Config Automatically Discarded)"]
    end

    Req --> AuthMiddleware
    AuthMiddleware --> ContextSetter
    ContextSetter --> TxBegin
    TxBegin --> RLS_Config
    RLS_Config --> TableAccess
    TableAccess --> RLS_Filter
    RLS_Filter -- "Matches Current Society" --> TxCommit
    RLS_Filter -- "Does Not Match / Bypass Attempt" --> ZeroRows["Returns Empty Rows / Denied"]
```

---

## 5. NETWORK ARCHITECTURE

### 5.1 VPC Subnet Allocation
A dedicated Amazon Virtual Private Cloud (VPC) with CIDR block `10.0.0.0/16` is allocated across three Availability Zones in `ap-south-1`:

| Subnet Identifier | CIDR Block | Available IPs | Route Table Gateway | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `subnet-public-1a` | `10.0.1.0/24` | 251 | Internet Gateway (`igw-xxxx`) | ALB Ingress, NAT Gateway A |
| `subnet-public-1b` | `10.0.2.0/24` | 251 | Internet Gateway (`igw-xxxx`) | ALB Ingress, NAT Gateway B |
| `subnet-public-1c` | `10.0.3.0/24` | 251 | Internet Gateway (`igw-xxxx`) | ALB Ingress, NAT Gateway C |
| `subnet-app-1a` | `10.0.10.0/22` | 1,019 | NAT Gateway A (`nat-xxxx-a`) | ECS Web, API, Workers, PgBouncer |
| `subnet-app-1b` | `10.0.14.0/22` | 1,019 | NAT Gateway B (`nat-xxxx-b`) | ECS Web, API, Workers, PgBouncer |
| `subnet-app-1c` | `10.0.18.0/22` | 1,019 | NAT Gateway C (`nat-xxxx-c`) | ECS Web, API, Workers |
| `subnet-data-1a` | `10.0.30.0/24` | 251 | Isolated (No IGW / No NAT) | RDS Primary, ElastiCache, Amazon MQ |
| `subnet-data-1b` | `10.0.31.0/24` | 251 | Isolated (No IGW / No NAT) | RDS Standby, ElastiCache, Amazon MQ |
| `subnet-data-1c` | `10.0.32.0/24` | 251 | Isolated (No IGW / No NAT) | Amazon MQ Quorum Node |

### 5.2 VPC Endpoints (AWS PrivateLink & Gateway Endpoints)
To minimize NAT Gateway data processing charges and eliminate public internet traversal for internal AWS API calls, the following VPC Endpoints are provisioned:
1. **Amazon S3 Gateway Endpoint (`com.amazonaws.ap-south-1.s3`):** Free of charge. Attached to App route tables. Routes invoice PDF and document transfers directly to S3 via private AWS backplanes.
2. **AWS ECR Endpoints (Interface):** `com.amazonaws.ap-south-1.ecr.api` and `com.amazonaws.ap-south-1.ecr.dkr` allow ECS Fargate agents to pull container images without consuming NAT Gateway bandwidth.
3. **AWS Secrets Manager Endpoint (Interface):** `com.amazonaws.ap-south-1.secretsmanager` for secure, private runtime credential injection.
4. **Amazon CloudWatch Logs Endpoint (Interface):** `com.amazonaws.ap-south-1.logs` for high-volume container log streaming.
5. **AWS KMS Endpoint (Interface):** `com.amazonaws.ap-south-1.kms` for cryptographic envelope operations.

### 5.3 Security Group Ingress / Egress Matrix
All traffic adheres strictly to the Principle of Least Privilege:

| Security Group | Ingress Rules | Egress Rules |
| :--- | :--- | :--- |
| **`sg-alb`** (ALB) | • `0.0.0.0/0` on TCP 80 (redirects to 443)<br>• `0.0.0.0/0` on TCP 443 (TLS 1.3) | • `sg-ecs-web` on TCP 3000<br>• `sg-ecs-api` on TCP 8000 |
| **`sg-ecs-web`** (Next.js) | • `sg-alb` on TCP 3000 | • `sg-ecs-api` on TCP 8000<br>• VPC Endpoints on TCP 443 |
| **`sg-ecs-api`** (FastAPI) | • `sg-alb` on TCP 8000<br>• `sg-ecs-web` on TCP 8000 | • `sg-pgbouncer` on TCP 6432<br>• `sg-redis` on TCP 6379<br>• `sg-rabbitmq` on TCP 5671<br>• VPC Endpoints on TCP 443 |
| **`sg-ecs-workers`** (Workers) | • None (no incoming traffic; consumers poll broker) | • `sg-pgbouncer` on TCP 6432<br>• `sg-redis` on TCP 6379<br>• `sg-rabbitmq` on TCP 5671<br>• `0.0.0.0/0` on TCP 443 (via NAT for Razorpay/SES) |
| **`sg-pgbouncer`** (Pooler) | • `sg-ecs-api` on TCP 6432<br>• `sg-ecs-workers` on TCP 6432 | • `sg-rds-postgres` on TCP 5432 |
| **`sg-rds-postgres`** (DB) | • `sg-pgbouncer` on TCP 5432<br>• `sg-migration-task` on TCP 5432 | • None (strictly isolated) |
| **`sg-redis`** (Cache) | • `sg-ecs-api` on TCP 6379<br>• `sg-ecs-workers` on TCP 6379 | • None |
| **`sg-rabbitmq`** (Broker) | • `sg-ecs-api` on TCP 5671 (AMQPS)<br>• `sg-ecs-workers` on TCP 5671 (AMQPS) | • None |

---

## 6. FRONTEND & BACKEND DEPLOYMENT STRATEGY

### 6.1 Frontend Hosting Evaluation: Next.js 14 on ECS Fargate vs AWS Amplify
A critical architectural evaluation was conducted to determine the optimal production hosting platform for `apps/web`:

* **Evaluation Dimensions:**
  1. *Container Compatibility:* Next.js 14 App Router relies on `output: 'standalone'`, Node.js 20 runtime, and custom SSR server handlers. ECS Fargate runs the exact, unadulterated Docker container produced by `Dockerfile.web`. Amplify uses proprietary Lambda/S3 edge wrappers that frequently experience compatibility regressions with dynamic server components and streaming responses.
  2. *Cold Starts & Latency:* Amplify SSR functions run serverlessly with cold start delays (800ms–2,500ms) after idle periods. ECS Fargate keeps warm container instances running continuously, providing sub-20ms first-byte response times.
  3. *Internal Network Security:* Next.js SSR components must communicate with the backend FastAPI service. On ECS Fargate, both services reside in the same VPC private application subnets, allowing internal DNS resolution via AWS Cloud Map (`api.internal:8000`) with zero public internet egress. On Amplify, requests must traverse the public internet or complex cross-VPC peering.
  4. *Cost Predictability:* Amplify charges per build-minute and request-hour with opaque edge data transfer multipliers. ECS Fargate provides deterministic hourly pricing based on vCPU/RAM allocation.
* **Architectural Decision:** **AWS ECS Fargate behind ALB and CloudFront** is selected as the production standard for the frontend (see [ADR-22A-01](#15-architectural-decision-records-adrs)).

### 6.2 Backend & Worker Topology on AWS ECS Fargate
Although `apps/api` and `apps/workers` share the same codebase and container image (`Dockerfile.api`), they possess fundamentally distinct runtime characteristics and scaling profiles:

```
+-------------------------------------------------------------------------+
|                  SHARED ECR CONTAINER: societysphere-api                |
|             (Python 3.12-slim, Non-root appuser:appgroup, UID 1001)     |
+------------------------------------+------------------------------------+
                                     |
              +----------------------+----------------------+
              |                                             |
              v                                             v
+-------------------------------+             +-------------------------------+
|   ECS SERVICE: api            |             |   ECS SERVICE: workers        |
|-------------------------------|             |-------------------------------|
| Entry: uvicorn apps.api.src...|             | Entry: python -m apps.api...  |
| Ports: 8000 (Ingress via ALB) |             | Ports: None (Ingress Denied)  |
| Health: GET /health/ready     |             | Health: Internal Task Watchdog|
| Scale Metric: ALB Req/Target  |             | Scale Metric: RabbitMQ Depth  |
| Workload: Sync Web Requests   |             | Workload: Async Background    |
+-------------------------------+             +-------------------------------+
```

* **Service 1: `societysphere-api`**
  * **Command:** `uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000 --workers 2`
  * **Task Sizing:** 1 vCPU, 2 GB RAM.
  * **Target Group Ingress:** Attached to ALB HTTP/HTTPS listener. Health check configured to `/health/ready` (interval: 15s, timeout: 5s, healthy threshold: 2, unhealthy threshold: 3).
  * **Auto-Scaling:** Target Tracking Scaling based on `ALBRequestCountPerTarget` (threshold: 1,200 requests/minute/task) and CPU utilization (> 70%).
* **Service 2: `societysphere-workers`**
  * **Command:** `python -m apps.api.src.workers.runner`
  * **Task Sizing:** 1 vCPU, 2 GB RAM.
  * **Network:** Private subnets only; no ALB listener or public ports.
  * **Internal Supervision:** Runs Python `asyncio.TaskGroup` supervising the distributed scheduler, billing consumer, notification dispatcher, and stale job sweeper.
  * **Auto-Scaling:** Step scaling triggered by CloudWatch Custom Metric publishing RabbitMQ queue depth (`billing.operations` + `notifications.outbox` depth > 500 messages).

---

## 7. DATABASE & MESSAGING ARCHITECTURE

### 7.1 Amazon RDS for PostgreSQL 16 (Multi-AZ)
* **Instance Class:** `db.m6g.large` (2 vCPUs, 8 GB RAM, AWS Graviton2 processor providing 35% superior price/performance over x86).
* **Storage:** 100 GB General Purpose SSD (`gp3`), 3,000 baseline IOPS, 125 MB/s throughput, autoscaling storage up to 500 GB.
* **High-Availability (Multi-AZ):** Synchronous physical block-level replication between AZ-a (Primary) and AZ-b (Standby). Failover is automated via DNS endpoint re-pointing, completing within 35 to 60 seconds with zero data loss (RPO = 0).
* **Automated Backups & Recovery:** 35-day backup retention window; continuous Write-Ahead Log (WAL) archiving to S3 enables Point-In-Time Recovery (PITR) to any second within the retention window.
* **Database Parameter Group Tuning:**
  ```ini
  max_connections = 300
  shared_buffers = 2097152          # 2GB (25% of RAM)
  effective_cache_size = 6291456    # 6GB (75% of RAM)
  work_mem = 16384                  # 16MB per sort/hash operation
  maintenance_work_mem = 262144     # 256MB for indexing and vacuum
  checkpoint_completion_target = 0.9
  wal_buffers = 16384               # 16MB
  default_statistics_target = 100
  random_page_cost = 1.1            # Optimized for SSD storage
  log_min_duration_statement = 250  # Log slow queries exceeding 250ms
  ```

### 7.2 Connection Pooling with PgBouncer
* **The Architectural Dilemma:** FastAPI with `asyncpg` opens a pool of 10 to 30 persistent connections per API task. As ECS autoscales to 10 API tasks and 4 worker tasks, total concurrent connections surge toward 400. Direct connection surges exhaust PostgreSQL memory, degrade CPU cache lines, and trigger connection timeouts.
* **The RLS Compatibility Challenge:** SocietySphere multi-tenancy relies on `SET LOCAL app.current_society_id = :val` within database transactions. In traditional session-level pooling, connection reuse could inadvertently leak the previous tenant's `society_id` if a connection is recycled without resetting session state.
* **The PgBouncer Solution:**
  * Sits as a lightweight proxy service between ECS tasks and RDS.
  * **Pool Mode:** `transaction`. A physical server connection is allocated to an application client only for the duration of a single database transaction (`BEGIN` to `COMMIT`/`ROLLBACK`).
  * **Session Sanitation:** Configured with `server_reset_query = DISCARD ALL`. This guarantees that whenever a transaction finishes, all temporary state, session configurations, prepared statements, and session variables are expunged before the connection is returned to the pool.
  * Because SocietySphere's tenant setter uses `is_local = true` (`set_config('app.current_society_id', :val, true)`), the setting is automatically dropped upon transaction termination by PostgreSQL itself, creating defense-in-depth against tenant leakage.

### 7.3 Amazon ElastiCache for Redis 7.x
* **Deployment Model:** Redis Cluster with Multi-AZ and Auto-Failover enabled.
* **Node Type:** `cache.m6g.large` (6.38 GB memory). Primary in AZ-a, Read Replica in AZ-b.
* **Security:** In-Transit TLS encryption, At-Rest AES-256 encryption, Redis AUTH token injected via AWS Secrets Manager.
* **Workloads:**
  1. *Distributed Scheduler Lease:* 10-second atomic leases via `SET key token NX EX 10` ensuring exactly one scheduler leader runs billing automation across the cluster.
  2. *API Rate Limiting:* Sliding window request tracking to prevent brute-force attacks on auth routes.
  3. *Application Caching:* User permissions and society quota definitions.

### 7.4 Amazon MQ for RabbitMQ
* **Deployment Model:** 3-Node Quorum Queue Cluster across 3 Availability Zones (`ap-south-1a`, `ap-south-1b`, `ap-south-1c`).
* **Instance Type:** `mq.m5.large` (2 vCPUs, 8 GB RAM).
* **Protocol & Compatibility:** Native AMQP 0-9-1 over TLS (port 5671). The existing `aio-pika` client implementation connects without code modifications.
* **Queue Configuration:** Quorum queues (`x-queue-type: quorum`) with Raft consensus replication across all 3 nodes, eliminating message loss in the event of an abrupt single-node hardware failure. Dead-letter exchanges (`billing.dlx`) capture unparseable or rejected messages for operator triage.

---

## 8. SECURITY ARCHITECTURE & DEVSECOPS

### 8.1 AWS WAF v2 Rule Hierarchy
AWS WAF v2 is deployed on both CloudFront and the ALB with the following managed and custom rule sets:
1. **AWSManagedRulesCommonRuleSet:** Mitigates common web exploits (OWASP Top 10, cross-site scripting, directory traversal).
2. **AWSManagedRulesKnownBadInputsRuleSet:** Shields against malicious request payloads, log4j patterns, and invalid request encodings.
3. **AWSManagedRulesSQLiRuleSet:** Detects and blocks SQL injection vectors targeting application inputs.
4. **AWSManagedRulesAmazonIpReputationList:** Blocks bots, TOR exit nodes, and known attacker IP addresses.
5. **Custom Auth Rate-Limiting Rule:** Tracks requests targeting `/api/v1/auth/*` and blocks IP addresses exceeding 100 requests per 5-minute rolling window.

### 8.2 Cryptographic Architecture & Data Protection
* **Data at Rest:**
  * **KMS Customer Managed Key (CMK):** A dedicated multi-region CMK (`alias/societysphere-prod-cmk`) with automatic annual key rotation.
  * **Database:** RDS storage encrypted using AWS KMS CMK with AES-256.
  * **S3 Buckets:** Server-Side Encryption with KMS (SSE-KMS). Bucket policies enforce `aws:SecureTransport: true` (rejecting plain HTTP).
  * **EBS & Container Disks:** ECS Fargate ephemeral storage encrypted at rest by default.
* **Data in Transit:**
  * **Edge:** TLS 1.3 mandated at CloudFront and ALB listeners. Support for legacy protocols (TLS 1.0, 1.1) and insecure ciphers is disabled.
  * **Internal VPC:** ALB to ECS Fargate communication executes over internal private subnets. Egress from ECS to RDS, ElastiCache, and Amazon MQ strictly utilizes TLS 1.2+ encryption (`sslmode=require` / `amqps://`).
* **Statutory Document Immutability:**
  * S3 Object Lock is activated in **Compliance Mode** on the production documents bucket (`societysphere-prod-documents-ap-south-1`) with a default retention period of **2,190 days (6 years)**.
  * This guarantees compliance with the Indian Goods and Services Tax Act (Section 36), preventing anyone—including AWS account root users—from deleting or tampering with finalized tax invoices and receipts during the statutory audit window.

### 8.3 IAM Least Privilege Model
Two distinct IAM roles are defined for ECS tasks to prevent privilege escalation:
1. **ECS Task Execution Role (`SocietySphereEcsTaskExecutionRole`):**
   * Permissions: `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:GetDownloadUrlForLayer`, `logs:CreateLogStream`, `logs:PutLogEvents`.
   * Scoped Secrets Access: `secretsmanager:GetSecretValue` restricted strictly to ARNs matching `arn:aws:secretsmanager:ap-south-1:ACCOUNT_ID:secret:societysphere/prod/*`.
2. **ECS Task Runtime Role (`SocietySphereEcsTaskRole`):**
   * Permissions:
     * S3: `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` restricted to `arn:aws:s3:::societysphere-prod-documents-ap-south-1/*`.
     * SES: `ses:SendEmail`, `ses:SendRawEmail` restricted to verified identity `noreply@societysphere.com`.
     * KMS: `kms:GenerateDataKey`, `kms:Decrypt` restricted to `alias/societysphere-prod-cmk`.
     * Explicit Deny: Direct access to IAM, VPC configuration, or database administrative APIs is strictly barred.

---

## 9. ENVIRONMENT STRATEGY

To preserve environment isolation and prevent configuration drift, SocietySphere employs a multi-account organization strategy using **AWS Organizations** and **AWS Control Tower**:

```
+-------------------------------------------------------------------------+
|                  AWS ORGANIZATIONS (ROOT MANAGEMENT)                    |
+------------------------------------+------------------------------------+
                                     |
              +----------------------+----------------------+
              |                                             |
              v                                             v
+-------------------------------+             +-------------------------------+
|  CORE / SECURITY ACCOUNT      |             |  DEVELOPMENT & TEST ACCOUNT   |
|-------------------------------|             |-------------------------------|
| • AWS IAM Identity Center     |             | • Ephemeral QA Environments   |
| • Central S3 CloudTrail Bucket|             | • Integration Test Pipelines  |
| • GuardDuty Master Admin      |             | • Isolated VPC (10.10.0.0/16) |
+-------------------------------+             +-------------------------------+
              |                                             |
              +----------------------+----------------------+
                                     |
                                     v
                      +-------------------------------+
                      |  PRODUCTION ACCOUNT           |
                      |-------------------------------|
                      | • Production VPC (10.0.0.0/16)|
                      | • Multi-AZ RDS / MQ / Cache   |
                      | • Strict IAM Lockdown         |
                      | • Zero Human Console Write    |
                      +-------------------------------+
```

### 9.1 Environment Tier Breakdown

| Attribute | Local / Dev | QA / Testing | Staging | Production |
| :--- | :--- | :--- | :--- | :--- |
| **AWS Account** | Local Workstation | Dev Account | Prod Account (Staging VPC) | Prod Account (Prod VPC) |
| **Compute** | Docker Compose | Ephemeral ECS / CI | ECS Fargate (2 Tasks) | ECS Fargate (Auto-scaled) |
| **Database** | Postgres Docker | RDS Single-AZ `db.t4g` | RDS Multi-AZ `db.m6g` | RDS Multi-AZ `db.m6g.large` |
| **Messaging** | RabbitMQ Docker | Amazon MQ Single-instance | Amazon MQ Multi-AZ | Amazon MQ 3-Node Quorum |
| **Storage** | MinIO Container | S3 Private Bucket | S3 Bucket (Versioning) | S3 (Object Lock / KMS CMK) |
| **Data Hygiene** | Seed Script Data | Synthetic Test Sets | Anonymized Replica | Production Data (Encrypted) |

### 9.2 Data Sanitization & Developer Isolation
* **Zero Production Access:** Developers and engineers have zero direct database access to production. Production troubleshooting is conducted exclusively through sanitized CloudWatch logs and distributed X-Ray tracing.
* **Test Data Generation:** Non-production environments utilize deterministic synthetic generation scripts (`infrastructure/scripts/seed_dev_data.py`) with zero real-world tenant records, phone numbers, or PAN/GST details.

---

## 10. CI/CD STRATEGY & RELEASE ENGINEERING

### 10.1 Pipeline Stages (GitHub Actions + AWS ECR + ECS)
The existing `.github/workflows/ci.yml` is extended to form a complete automated promotion pipeline:

```mermaid
flowchart LR
    Commit["Git Push / PR"] --> Lint["Step 1: Quality Gate<br>• Ruff Lint & Format<br>• Mypy Type Check<br>• Pytest (Unit/RLS)<br>• Next.js Build"]
    Lint --> Scan["Step 2: Security Gate<br>• Trivy Vulnerability Scan<br>• GitGuardian Secret Scan"]
    Scan --> Build["Step 3: Docker Buildx<br>• Multi-stage build<br>• Push to Amazon ECR<br>• Tag: Git SHA + semver"]
    Build --> Migrate["Step 4: Pre-Release Task<br>• Run Alembic Migration<br>• Ephemeral ECS Task"]
    Migrate --> Deploy["Step 5: ECS Deployment<br>• Rolling Blue/Green<br>• Target Group Health Check<br>• Drain Old Tasks"]
    Deploy --> Verify["Step 6: Post-Deploy Verification<br>• Smoke Tests (/health/ready)<br>• Metric Alarm Monitoring"]
```

### 10.2 Database Migration Orchestration
A critical hazard in automated SaaS pipelines is deploying application code before database migrations complete, or running migrations while old containers are serving requests.
* **Orchestration Pattern:**
  1. GitHub Actions triggers a dedicated, one-off ECS Fargate Task (`societysphere-db-migrator`) before initiating the service rolling update.
  2. The migrator task runs `alembic upgrade head` under a 3-minute execution timeout.
  3. If migrations fail, the deployment is aborted immediately, preserving previous container versions without traffic disruption.
  4. Only upon zero exit code from the migrator task does AWS ECS initiate the rolling service update.
* **Backward-Compatible DDL Rules:** All migrations must strictly adhere to expand-and-contract patterns (e.g., adding nullable columns, creating new tables). Destructive operations (dropping columns, changing constraints) must span multiple phase releases.

### 10.3 Zero-Downtime Rolling Deployments
* **ECS Rolling Update Configuration:**
  * `minimumHealthyPercent = 100`: Guarantees that at least the desired task count remains active and serving traffic during rollout.
  * `maximumPercent = 200`: Allows ECS to provision new tasks in parallel before terminating legacy tasks.
  * **Deregistration Delay:** ALB Target Group deregistration delay set to `30 seconds` to allow in-flight HTTP requests to complete cleanly before container shutdown.

---

## 11. HIGH AVAILABILITY & DISASTER RECOVERY (HA/DR)

### 11.1 Service Level Objectives
* **Recovery Point Objective (RPO):** < 5 minutes (Maximum tolerable data loss in disaster).
* **Recovery Time Objective (RTO):** < 15 minutes (Maximum tolerable downtime to restore service).

### 11.2 Failure Mode & Mitigation Analysis

| Failure Domain | Severity | Detection Mechanism | Automated Mitigation Procedure | Expected Downtime |
| :--- | :--- | :--- | :--- | :--- |
| **Single ECS Container Crash** | Low | ECS Task Exit Code / Health Probe Failure | ECS Service Manager immediately spins up a replacement container. ALB stops routing traffic to failed container within 15s. | 0 seconds (transparent to users) |
| **Availability Zone Outage (AZ-a)** | High | CloudWatch AZ Health Alarm / ALB Target Health | ALB immediately shifts all ingress traffic to healthy AZ-b and AZ-c. RDS initiates automatic failover to AZ-b standby. Amazon MQ maintains quorum. | < 60 seconds (brief DB reconnection) |
| **PostgreSQL Primary Corruption / Failure** | Critical | RDS Health Monitor / CloudWatch Alarm | Multi-AZ automated failover switches primary DNS endpoint to standby replica. PgBouncer reconnects automatically. | 35–60 seconds |
| **Redis Cache Node Failure** | Medium | ElastiCache Health Monitor | Multi-AZ auto-failover promotes replica node to primary. Leader election temporarily acquires lease on new primary. | < 15 seconds |
| **RabbitMQ Broker Failure** | High | Amazon MQ Node Health Check | Quorum queues maintain data availability across 2 surviving nodes with zero message loss. | 0 seconds (Raft quorum maintained) |
| **Catastrophic Regional Disaster (`ap-south-1`)** | Catastrophic | AWS Regional Service Health Dashboard | Execute Disaster Recovery Runbook: Restore latest RDS snapshot and S3 cross-region replica in `ap-south-2` (Hyderabad). | < 4 hours (Cold Standby DR) |

---

## 12. INITIAL CAPACITY & SCALING MODEL

### 12.1 Sizing Baseline (Initial 12-Month Horizon)
* **Target Adoption:** 100 Housing Societies onboarded.
* **Total Managed Units:** 20,000 residential apartments (average 200 units per society).
* **Registered Residents:** ~35,000 active mobile app / web users.
* **Transaction Characteristics:**
  * Monthly Maintenance Billing Cycle: Once per month (1st of each month). Generates 20,000 PDF invoices within a 2-hour window.
  * Payment Due Window: 1st to 10th of each month. Peak payment submissions via Razorpay webhooks.
  * Daily Operational Traffic: Gatekeeper visitor approvals, maintenance ticket submissions, notice board broadcasts (~120,000 daily API calls).

### 12.2 Request & Throughput Calculations
* **Normal Business Hours:**
  $$\text{Throughput} = \frac{120,000 \text{ requests}}{12 \times 3600 \text{ seconds}} \approx 2.8 \text{ requests/sec}$$
* **Peak Surge (1st of Month Billing + Morning Resident Gate Activity):**
  $$\text{Peak Factor} = 25\times \implies \text{Peak Throughput} \approx 70 \text{ requests/sec}$$
* **Container Capacity Sizing:**
  * Single FastAPI Container (1 vCPU, 2 GB RAM, 2 Uvicorn workers): Empirically benchmarks at **150–220 requests/sec** for database-backed I/O endpoints.
  * Provisioning 2 API tasks provides **300–440 req/sec** baseline capacity (more than 4x peak surge requirement).

### 12.3 Database & Connection Sizing
* **Storage Growth:**
  * Database records: 20,000 invoices/month $\times$ 1.5 KB = 30 MB/month. 100 societies audit data = ~5 GB/year.
  * S3 Object Storage: 20,000 PDF invoices/month $\times$ 250 KB = 5 GB/month $\implies$ 60 GB/year.
* **Connection Multiplexing:**
  * Direct connections required without pooler: 8 API tasks $\times$ 20 pool = 160 connections.
  * With PgBouncer in `transaction` mode: Multiplexes 160 incoming application connections down to **25 active physical PostgreSQL server connections**, running comfortably within the `db.m6g.large` 300-connection ceiling.

---

## 13. AWS COST ESTIMATION SCENARIOS

All pricing is modeled specifically for **AWS Region `ap-south-1` (Mumbai)** based on standard On-Demand public rates (converted at USD 1 = INR 84.00).

### 13.1 Option A: Minimum Viable Production (Cost-Optimized / Single-AZ)
*Designed for initial pilot launches, early-stage bootstrap operations, or pre-revenue beta deployments.*

| Component | AWS Resource Specification | Monthly Cost (USD) | Monthly Cost (INR) |
| :--- | :--- | :--- | :--- |
| **Compute (Web & API)** | 2 $\times$ ECS Fargate Tasks (0.5 vCPU, 1 GB RAM) | $26.00 | ₹2,184 |
| **Compute (Workers)** | 1 $\times$ ECS Fargate Task (0.5 vCPU, 1 GB RAM) | $13.00 | ₹1,092 |
| **Load Balancing** | 1 $\times$ AWS Application Load Balancer (ALB) + LCU | $23.00 | ₹1,932 |
| **Database** | RDS PostgreSQL 16 (Single-AZ, `db.t4g.medium`, 50 GB gp3) | $62.00 | ₹5,208 |
| **Caching** | Amazon ElastiCache Redis (Single-Node, `cache.t4g.small`) | $24.00 | ₹2,016 |
| **Messaging** | Amazon MQ for RabbitMQ (Single-Instance, `mq.t3.micro`) | $28.00 | ₹2,352 |
| **Object Storage** | Amazon S3 Standard (50 GB storage, 20k PUT/GET) | $2.50 | ₹210 |
| **Networking** | 1 $\times$ Managed NAT Gateway (Single AZ, 50 GB data) | $36.00 | ₹3,024 |
| **Security & Secrets** | AWS Secrets Manager (10 secrets) + KMS | $5.00 | ₹420 |
| **Observability** | Amazon CloudWatch (Logs, Metrics, 1 Dashboard) | $15.00 | ₹1,260 |
| **Edge CDN & WAF** | CloudFront (Free Tier) + AWS WAF Basic (Common Rules) | $15.00 | ₹1,260 |
| **TOTAL (Option A)** | **Cost-Optimized / Single-AZ** | **~$250.00 / mo** | **~₹21,000 / mo** |

> *Limitations:* Single points of failure on RDS, Redis, and NAT Gateway. Downtime expected during AWS hardware maintenance windows. Not suitable for commercial SLA guarantees.

---

### 13.2 Option B: Standard Production (Recommended Multi-AZ High Availability)
*The recommended production baseline for SocietySphere commercial launch. Meets enterprise SLAs (99.9% uptime), Indian data residency, and ISO 27001 requirements.*

| Component | AWS Resource Specification | Monthly Cost (USD) | Monthly Cost (INR) |
| :--- | :--- | :--- | :--- |
| **Compute (Web Frontend)** | 2 $\times$ ECS Fargate Tasks (1 vCPU, 2 GB RAM) across 2 AZs | $72.00 | ₹6,048 |
| **Compute (Backend API)** | 2 $\times$ ECS Fargate Tasks (1 vCPU, 2 GB RAM) across 2 AZs | $72.00 | ₹6,048 |
| **Compute (Workers)** | 2 $\times$ ECS Fargate Tasks (1 vCPU, 2 GB RAM) across 2 AZs | $72.00 | ₹6,048 |
| **Load Balancing & Edge** | 1 $\times$ ALB + AWS CloudFront + ACM TLS | $32.00 | ₹2,688 |
| **WAF Protection** | AWS WAF v2 (Common Rules, SQLi, Rate Limiting) | $28.00 | ₹2,352 |
| **Database** | RDS PostgreSQL 16 (Multi-AZ, `db.m6g.large`, 100 GB gp3) | $265.00 | ₹22,260 |
| **Connection Pooler** | 2 $\times$ ECS Fargate PgBouncer (0.25 vCPU, 0.5 GB RAM) | $12.00 | ₹1,008 |
| **Caching Layer** | Amazon ElastiCache Redis 7.x (Multi-AZ, `cache.m6g.large`) | $145.00 | ₹12,180 |
| **Message Broker** | Amazon MQ RabbitMQ (3-Node Quorum Cluster, `mq.m5.large`) | $195.00 | ₹16,380 |
| **Object Storage** | S3 Standard (250 GB + Object Lock + Versioning) | $8.00 | ₹672 |
| **Networking** | 2 $\times$ Managed NAT Gateways (Multi-AZ, 150 GB data) | $78.00 | ₹6,552 |
| **VPC Endpoints** | 4 $\times$ Interface PrivateLink Endpoints (ECR, Secrets, Logs) | $32.00 | ₹2,688 |
| **Security & Secrets** | Secrets Manager (15 secrets) + KMS Customer Managed Key | $8.00 | ₹672 |
| **Observability** | CloudWatch Container Insights, Alarms, Metric Filters | $35.00 | ₹2,940 |
| **TOTAL (Option B)** | **Standard Multi-AZ High Availability** | **~$1,054.00 / mo** | **~₹88,500 / mo** |

> *Advantages:* Zero single points of failure across all tiers. Automated failover for Database (<60s), Redis (<15s), and RabbitMQ (0s). Full compliance with statutory invoice retention rules.

---

### 13.3 Option C: Enterprise Production (Large Scale / Regulatory Grade)
*Engineered for tier-1 property management enterprises, 500+ societies (100,000+ units), strict compliance auditing, provisioned IOPS, and cross-region disaster recovery.*

| Component | AWS Resource Specification | Monthly Cost (USD) | Monthly Cost (INR) |
| :--- | :--- | :--- | :--- |
| **Compute (Web Frontend)** | 4 $\times$ ECS Fargate Tasks (2 vCPU, 4 GB RAM) | $288.00 | ₹24,192 |
| **Compute (Backend API)** | 6 $\times$ ECS Fargate Tasks (2 vCPU, 4 GB RAM) | $432.00 | ₹36,288 |
| **Compute (Workers)** | 4 $\times$ ECS Fargate Tasks (2 vCPU, 4 GB RAM) | $288.00 | ₹24,192 |
| **Ingress & Edge** | Multi-AZ ALB + CloudFront Global CDN + Route 53 Routing | $65.00 | ₹5,460 |
| **Enterprise Security** | AWS WAF v2 + AWS Shield Standard + GuardDuty + SecurityHub | $145.00 | ₹12,180 |
| **Primary Database** | RDS PostgreSQL 16 Multi-AZ (`db.r6g.xlarge`, 500 GB, 6k IOPS) | $780.00 | ₹65,520 |
| **Read Replica** | RDS Read Replica (`db.m6g.large` in AZ-c for BI/Reports) | $135.00 | ₹11,340 |
| **Connection Pooling** | 4 $\times$ ECS Fargate PgBouncer (0.5 vCPU, 1 GB RAM) | $48.00 | ₹4,032 |
| **Cache Cluster** | ElastiCache Redis (2 Shards $\times$ 2 Replicas, `cache.r6g.large`) | $410.00 | ₹34,440 |
| **Broker Cluster** | Amazon MQ RabbitMQ Quorum Cluster (`mq.m5.xlarge`) | $390.00 | ₹32,760 |
| **Storage & DR** | S3 Standard (1 TB) + Cross-Region Replication to `ap-south-2` | $45.00 | ₹3,780 |
| **Networking** | 3 $\times$ NAT Gateways (1 per AZ) + 8 $\times$ VPC Endpoints | $185.00 | ₹15,540 |
| **Governance & Audit** | CloudTrail Multi-Region Organization Trail + KMS CMKs | $25.00 | ₹2,100 |
| **Observability** | CloudWatch Insights + AWS X-Ray Distributed Tracing | $85.00 | ₹7,140 |
| **TOTAL (Option C)** | **Enterprise Production & Regulatory Scale** | **~$3,321.00 / mo** | **~₹2,78,900 / mo** |

---

## 14. ISO 27001:2022 SECURITY ALIGNMENT MATRIX

The SocietySphere production architecture maps directly to the **ISO/IEC 27001:2022** Information Security Management System (ISMS) Annex A controls:

| ISO 27001:2022 Control | Control Title | SocietySphere Implementation & AWS Control Mapping |
| :--- | :--- | :--- |
| **A.5.15** | Access Control | IAM Least Privilege Task Roles; API JWT authentication (RS256); RBAC & RLS database authorization. |
| **A.5.23** | Information Security for Cloud Services | AWS Shared Responsibility model; encrypted VPC private subnets; AWS CIS Foundations Benchmark compliance. |
| **A.8.2** | Privileged Access Rights | Zero direct SSH or console write access for developers; break-glass MFA root controls; temporary STS credentials. |
| **A.8.9** | Configuration Management | Infrastructure-as-Code (Terraform/OpenTofu) versioned in Git; immutable container images tagged by Git SHA. |
| **A.8.11** | Data Masking | Synthetic data generation in test environments; API logging filters out PAN, passwords, and banking tokens. |
| **A.8.12** | Data Leakage Prevention | Strict VPC egress routing; S3 Public Access Block enforced at AWS Account level; DLP checks on S3 buckets. |
| **A.8.20** | Network Security | Three-tier subnet topology (Public, Private App, Isolated Data); strict SG firewall rules; AWS WAF v2 inspection. |
| **A.8.24** | Use of Cryptography | AWS KMS Customer Managed Keys; TLS 1.3 edge termination; TLS 1.2 internal DB/broker links; S3 Object Lock. |
| **A.8.28** | Secure Coding | CI automated pipeline executing Ruff, Mypy, and Pytest suites; Trivy container image vulnerability scanning. |
| **A.8.31** | Separation of Environments | Isolated AWS accounts for Dev/QA and Production; zero cross-environment database peering or shared credentials. |

---

## 15. ARCHITECTURAL DECISION RECORDS (ADRs)

### ADR-22A-01: ECS Fargate over AWS Amplify for Next.js 14 Standalone Hosting
* **Status:** APPROVED
* **Context:** `apps/web` is developed with Next.js 14 App Router and configured with `output: 'standalone'` in `next.config.js`. We evaluated whether to host on AWS Amplify Hosting or deploy containerized onto AWS ECS Fargate.
* **Decision:** Deploy Next.js onto AWS ECS Fargate behind CloudFront and ALB.
* **Rationale:**
  1. *Runtime Fidelity:* ECS Fargate executes the identical Docker container verified locally, eliminating runtime incompatibilities with Amplify's serverless edge handlers.
  2. *Cold Start Elimination:* Eliminates serverless cold starts (800ms–2.5s) on server components, delivering consistent sub-20ms rendering.
  3. *VPC Private Routing:* Allows server-side Next.js fetch requests to route directly to the FastAPI container over internal private VPC subnets without traversing the public internet.
* **Consequences:** Requires provisioning an ALB target group and ECS service for the frontend, but provides complete operational control, deterministic scaling, and hardened VPC isolation.

### ADR-22A-02: Amazon MQ for RabbitMQ vs Self-Managed EC2 vs AWS SQS
* **Status:** APPROVED
* **Context:** SocietySphere's background architecture relies on RabbitMQ AMQP 0-9-1 with quorum queues, dead-letter exchanges, and transactional outbox consumers implemented via `aio-pika`. We evaluated Amazon SQS, self-managed RabbitMQ on EC2, and Amazon MQ.
* **Decision:** Adopt Amazon MQ for RabbitMQ (3-node Quorum Cluster in Production).
* **Rationale:**
  1. *Zero Code Changes:* Preserves 100% of the verified `aio-pika` consumer and publisher implementations in `apps/api/src/workers/`. Migrating to SQS would violate the phase restriction and require a major refactor of messaging semantics.
  2. *Managed Operations:* Offloads OS patching, RabbitMQ version upgrades, clustering management, and EBS volume administration to AWS.
  3. *High Availability:* 3-node managed cluster provides Raft-based quorum consensus across 3 AZs.
* **Consequences:** Slightly higher baseline cost than SQS, but saves dozens of engineering days and guarantees absolute behavioral continuity.

### ADR-22A-03: PgBouncer Connection Pooling with PostgreSQL Row-Level Security
* **Status:** APPROVED
* **Context:** As API and worker containers autoscale, connection counts to PostgreSQL surge. We must implement connection pooling while ensuring PostgreSQL RLS session variables (`app.current_society_id`) never leak between distinct tenant transactions.
* **Decision:** Deploy containerized PgBouncer in `transaction` pool mode with `server_reset_query = DISCARD ALL`.
* **Rationale:**
  1. *Multiplexing Efficiency:* Reduces 200+ container connections down to 25 physical PostgreSQL server connections, avoiding memory exhaustion on RDS.
  2. *RLS Isolation Safety:* In transaction mode, a server connection is assigned only for the duration of a transaction. Because `SELECT set_config('app.current_society_id', :id, true)` uses `is_local = true`, PostgreSQL drops the variable at `COMMIT`/`ROLLBACK`.
  3. *Defense-in-Depth:* Setting `server_reset_query = DISCARD ALL` in `pgbouncer.ini` ensures that even if an abnormal connection abort occurs, the connection is scrubbed clean before re-entering the pool.
* **Consequences:** Applications cannot use session-level prepared statements or session-level advisory locks across multiple transactions. SocietySphere's scheduler leader election already uses a dedicated persistent connection, adhering to this constraint.

### ADR-22A-04: Multi-AZ NAT Gateway Strategy vs Cost Trade-offs
* **Status:** APPROVED
* **Context:** AWS charges ~$32/month per NAT Gateway plus $0.045/GB data processing. We evaluated whether to deploy 1 NAT Gateway or 3 NAT Gateways (1 per AZ).
* **Decision:** Deploy **1 NAT Gateway in Dev/Staging/Pilot (Option A)** and **2 to 3 NAT Gateways in Standard/Enterprise Production (Option B & C)**.
* **Rationale:**
  1. *Zone Independence in Prod:* If a single AZ suffers a catastrophic network degradation, private subnets in surviving AZs must maintain outbound connectivity to Razorpay, SES, and SMS providers. A single NAT Gateway creates an inter-AZ dependency.
  2. *VPC Endpoints Optimization:* By provisioning free S3 Gateway Endpoints and Interface Endpoints for ECR, Secrets Manager, and CloudWatch Logs, over 80% of internal traffic bypasses the NAT Gateway entirely, preventing excessive data processing charges.
* **Consequences:** Standard Production incurs ~$78/month for dual NAT Gateways, justified by the avoidance of single-zone outbound network failure.

---

## 16. INFRASTRUCTURE IMPLEMENTATION ROADMAP

The production rollout is structured across the following consecutive phases:

```
[Phase 22A: Assessment & Design] (CURRENT)
        │
        ▼
[Phase 22B: Terraform/OpenTofu Core Foundations]
 ├── VPC, Subnets, Internet Gateways, NAT Gateways
 ├── Security Groups, Route Tables, VPC Endpoints
 └── IAM Roles, KMS CMK, S3 Buckets with Object Lock
        │
        ▼
[Phase 22C: Managed Data & Messaging Infrastructure]
 ├── Amazon RDS PostgreSQL 16 Multi-AZ & Parameter Groups
 ├── Containerized PgBouncer Service
 ├── Amazon ElastiCache Redis 7.x Multi-AZ Cluster
 └── Amazon MQ for RabbitMQ 3-Node Quorum Cluster
        │
        ▼
[Phase 22D: Container Compute & Ingress Routing]
 ├── Amazon ECR Repositories with Vulnerability Scanning
 ├── AWS Application Load Balancer & ACM TLS Certificates
 ├── AWS ECS Fargate Cluster & Task Definitions (Web, API, Workers)
 └── Amazon CloudFront CDN Distribution
        │
        ▼
[Phase 22E: Security Hardening, WAF & Observability]
 ├── AWS WAF v2 WebACL Rules & Rate Limiting
 ├── AWS Secrets Manager Secret Injection
 ├── Amazon CloudWatch Dashboards, Log Groups, Metric Alarms
 └── Amazon GuardDuty & AWS CloudTrail Configuration
        │
        ▼
[Phase 22F: CI/CD Pipeline & Automated Release Engineering]
 ├── GitHub Actions Deployment Workflows
 ├── Pre-release Automated Migration Execution
 ├── Zero-Downtime ECS Rolling Updates
 └── Smoke Test Verification & Automated Rollback
```

---

## 17. PRODUCTION-READINESS GAPS & REMEDIATION PLAN

| Item | Identified Gap | Severity | Risk / Impact | Concrete Remediation Plan (Phase Target) |
| :---: | :--- | :---: | :--- | :--- |
| **G-01** | **No Infrastructure as Code (IaC)** | CRITICAL | Manual AWS console provisioning causes configuration drift, lack of auditability, and catastrophic recovery delays. | Author modular Terraform/OpenTofu code defining all VPC, IAM, RDS, and ECS resources with state locking in S3/DynamoDB (Phase 22B). |
| **G-02** | **Direct Database Connection Exhaustion** | HIGH | Multiple scaling API and worker tasks directly opening asyncpg connection pools can overwhelm RDS connection limits. | Deploy containerized PgBouncer in `transaction` mode between ECS tasks and RDS (Phase 22C). |
| **G-03** | **Plaintext Secrets in Local Configs** | HIGH | Risk of credential leakage in Git or build logs. | Migrate all secrets (DB, JWT, Razorpay) to AWS Secrets Manager; inject dynamically via ECS Task Execution roles (Phase 22E). |
| **G-04** | **Unprotected Static Next.js Assets** | MEDIUM | Next.js Node container burdened with serving static files (`/_next/static/*`), consuming CPU/bandwidth. | Deploy AWS CloudFront CDN in front of ALB with caching policies for static paths (Phase 22D). |
| **G-05** | **Statutory Invoice Immutability** | HIGH | Indian GST regulations mandate 6-year retention. Standard S3 buckets allow accidental deletion. | Enable S3 Object Lock in Compliance Mode (2,190 days retention) on the production documents bucket (Phase 22B). |
| **G-06** | **Single Point of Failure on Background Workers** | MEDIUM | If the single worker instance crashes, billing rolls and outbox dispatches stall until container restart. | Configure ECS Service with `desired_count = 2` across 2 AZs. Distributed leader election safely coordinates execution (Phase 22D). |
| **G-07** | **Automated Deployment Pipeline Gaps** | HIGH | CI currently only runs tests; no automated ECR build/push, migration runner, or rolling ECS deployment. | Implement GitHub Actions deployment workflows with ephemeral migration task execution (Phase 22F). |

---

## 18. FINAL STATUS & RECOMMENDATIONS

### Final Assessment Classification:
# **READY FOR ARCHITECT REVIEW**

### Summary of Recommendations for Architecture Board:
1. **Approve Architecture Baseline:** Formally approve the **Option B (Standard Production - Multi-AZ High Availability)** deployment model (~$1,054/mo | ~₹88,500/mo) as the official launch target for SocietySphere in AWS `ap-south-1` (Mumbai).
2. **Authorize ADRs:** Adopt ADR-22A-01 (ECS Fargate for Next.js), ADR-22A-02 (Amazon MQ for RabbitMQ), ADR-22A-03 (PgBouncer with RLS), and ADR-22A-04 (Multi-AZ NAT Gateways).
3. **Lock Application Code & Migrations:** Verify and maintain zero modifications to application source code (`apps/`) and confirm Alembic migration head remains strictly locked at `0025_saas_billing_automation`.
4. **Authorize Phase 22B Commencement:** Authorize the engineering team to begin **Phase 22B: Terraform/OpenTofu Core Foundations**, focusing on networking, IAM, KMS, and baseline security configurations.

---
*End of Phase 22A Architecture Assessment Document.*
