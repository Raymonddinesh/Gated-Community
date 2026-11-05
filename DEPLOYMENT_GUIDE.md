# SocietySphere — Deployment & Operations Guide

**Document Version:** 1.0.0  
**Target AWS Region:** `ap-south-1` (Mumbai)  
**Primary IaC Engine:** OpenTofu v1.9.0  
**Secondary Compatibility:** HashiCorp Terraform >= 1.10.x  

---

## 1. Overview & Architectural Environments

SocietySphere employs a four-tier environment structure designed to ensure zero downtime, high security, and verified tenant isolation:

| Environment | Purpose | Infrastructure Strategy | Autoscaling Limits |
|---|---|---|---|
| **dev** | Developer feature testing & integration | Single-AZ, cost-optimized (`t4g`), ephemeral | Min 1, Max 2 tasks |
| **qa** | Automated regression & QA validation | Multi-AZ data tier, synthetic test pipelines | Min 1, Max 4 tasks |
| **staging** | Production mirror & pre-release testing | Full Multi-AZ parity, realistic scale | Min 2, Max 6 tasks |
| **production** | Live multi-tenant SaaS operations | Multi-AZ, strict deletion protection, 35-day backup | Min 2, Max 10 tasks |

---

## 2. Local Development Setup

### 2.1 Prerequisites
- Python 3.12+
- Node.js 20+ LTS & npm 10+
- Docker Desktop 24+
- OpenTofu v1.9.0 or Terraform >= 1.10.x
- AWS CLI v2 (for cloud operations)

### 2.2 Quick Start via Docker Compose (Recommended)
```powershell
# 1. Initialize environment file from clean template
cp .env.example .env

# 2. Launch the full local application stack
docker-compose up -d

# 3. View service status
docker-compose ps
```
Services exposed locally:
- **FastAPI Backend:** [http://localhost:8000](http://localhost:8000) (Swagger Docs: `/docs`)
- **Next.js Web Portal:** [http://localhost:3000](http://localhost:3000)
- **PostgreSQL Database:** `localhost:5432` (`postgres:postgres`)
- **Redis Cache:** `localhost:6379`
- **RabbitMQ Broker:** `localhost:5672` (Management Dashboard: [http://localhost:15672](http://localhost:15672), guest:guest)
- **MinIO S3 Storage:** `localhost:9000` (Console: [http://localhost:9001](http://localhost:9001), minioadmin:minioadmin)

### 2.3 Standalone Local Development
```powershell
# --- Backend Setup ---
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r apps/api/requirements-dev.txt

# Run database migrations to head
alembic -c apps/api/alembic.ini upgrade head

# Launch backend API with hot-reloading
uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8000 --reload

# --- Background Worker Runner (Separate Terminal) ---
python -m apps.api.src.workers.runner

# --- Frontend Setup (Separate Terminal) ---
cd apps/web
npm install
npm run dev
```

---

## 3. Database Migration Management (Alembic)

SocietySphere utilizes Alembic with asynchronous PostgreSQL connections.
- **Current Migration Head:** `20261102_0025_saas_billing_automation.py`

### Key Migration Commands:
```powershell
# Check current migration status
alembic -c apps/api/alembic.ini current

# Inspect migration history
alembic -c apps/api/alembic.ini history --verbose

# Apply pending migrations
alembic -c apps/api/alembic.ini upgrade head

# Roll back a single revision (caution in production)
alembic -c apps/api/alembic.ini downgrade -1
```

> [!CAUTION]
> Never create or alter migrations without Principal Architect authorization. Ensure all migrations are backward-compatible with zero table locks on multi-million row tables.

---

## 4. AWS Infrastructure Deployment (OpenTofu / Terraform)

### 4.1 Deployment Safety Rule
> [!IMPORTANT]
> **No cloud infrastructure may be modified or provisioned without explicit, documented client/architect authorization.** Never run `apply` in unapproved phases.

### 4.2 Bootstrap Remote State
Before provisioning environments, remote state backend infrastructure must be deployed once per account:
```powershell
cd infrastructure/terraform/bootstrap
tofu init
tofu plan -out=bootstrap.tfplan
tofu apply bootstrap.tfplan
```
This creates:
- S3 Remote State Bucket: `societysphere-tfstate-<account_id>` (SSE-KMS, Versioning, Public Access Blocked).
- DynamoDB Lock Table: `societysphere-tfstate-lock` (Pay-per-request, KMS encrypted).

### 4.3 Environment Deployment Sequence
To deploy an environment (e.g., `staging` or `production`), navigate to its directory:
```powershell
cd infrastructure/terraform/environments/<environment>
tofu init
tofu plan -var-file="terraform.tfvars" -out="infra.tfplan"
```

The underlying modules deploy in strict dependency order:
1. **`modules/networking`**: VPC, Internet Gateway, 3 Public Subnets, 3 App Subnets, 3 Data Subnets, NAT Gateways, Route Tables, VPC Flow Logs, VPC Endpoints.
2. **`modules/security`**: Customer Managed KMS Keys, Security Groups (`sg_alb`, `sg_web`, `sg_api`, `sg_worker`, `sg_rds`, `sg_redis`, `sg_rabbitmq`, `sg_endpoints`), IAM Execution & Task Roles.
3. **`modules/storage`**: Private S3 Document Storage (`societysphere-<env>-documents-<account_id>`) with SSE-KMS, Object Lock, 7-year Glacier lifecycle, and CORS.
4. **`modules/monitoring`**: CloudWatch Log Groups with KMS CMK encryption and environment retention.
5. **`modules/rds`**: Multi-AZ PostgreSQL 16, Parameter Groups, Enhanced Monitoring, and Amazon RDS Proxy transaction pooling.
6. **`modules/redis`**: ElastiCache Redis 7.1 Multi-AZ replication group with in-transit/at-rest encryption.
7. **`modules/rabbitmq`**: Amazon MQ RabbitMQ 3.13 Multi-AZ cluster with AWS Secrets Manager credentials.
8. **`modules/ecs`**: ECR Repositories, Application Load Balancer with path-based routing, ECS Fargate Cluster, Task Definitions, and Service Autoscaling.

---

## 5. Secrets Management Architecture

SocietySphere adheres to a **zero plaintext secrets** standard. Secrets are never stored in Git repositories, Docker images, or unencrypted configuration files.

### 5.1 Cloud Secrets (AWS Secrets Manager)
In AWS environments, tasks retrieve credentials at container startup via ECS Task Definition secret injection:
- `societysphere/<env>/db-credentials`: Managed automatically by RDS master password management.
- `societysphere/<env>/rabbitmq-credentials`: Generated during Terraform provisioning and stored in Secrets Manager.
- `societysphere/<env>/api-secrets`: Stores `SECRET_KEY`, JWT signing keys, and external service tokens.

### 5.2 Local Secrets
- Developers copy `.env.example` to `.env`.
- `.env` and `.env.*` are strictly excluded from source control via `.gitignore`.
- Dummy/mock credentials (`minioadmin`, `postgres:postgres`) are used exclusively for local sandbox environments.

---

## 6. Continuous Integration & Deployment (CI/CD)

Automated GitHub Actions workflows are defined in `.github/workflows/`:
1. **`infrastructure-validate.yml`**: Runs on every pull request targeting `infrastructure/**`. Executes syntax validation, formatting check, TFLint, and tfsec.
2. **`infrastructure-terraform-compat.yml`**: Verifies compatibility against HashiCorp Terraform >= 1.10.x.
3. **`security-scan.yml`**: Executes Checkov static security analysis across all modules.

### Pull Request & Approval Control
- Merges to `main` require linear Git history and passing status checks.
- Production deployments require manual approval from designated DevSecOps and Architect approvers.
