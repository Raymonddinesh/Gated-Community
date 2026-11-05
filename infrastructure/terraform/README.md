# SocietySphere — Infrastructure as Code (Terraform / OpenTofu)

## Overview

This repository contains the production-grade Infrastructure as Code (IaC) foundation for **SocietySphere**, an enterprise-grade multi-tenant apartment management SaaS platform deployed on AWS (`ap-south-1` Mumbai).

The design strictly follows the architectural decisions, capacity planning, and security baselines established in **Phase 22A: Production Infrastructure & Architecture Assessment**.

---

## Directory Structure

```
infrastructure/terraform/
├── bootstrap/               # S3 state bucket & KMS CMK initialization
├── modules/                 # Reusable, decoupled infrastructure modules
│   ├── networking/          # VPC, 3 AZ subnets, IGW, NAT Gateways, SG rules, VPC Flow Logs
│   ├── security/            # KMS CMK, Secrets Manager containers, ECS Task Execution/Task IAM Roles
│   ├── storage/             # S3 documents bucket, KMS SSE, Object Lock (GST compliance), Lifecycle
│   ├── monitoring/          # CloudWatch log groups with KMS SSE, Metric alarms (CPU, Memory, Storage)
│   ├── ecs/                 # ECS Fargate Cluster, Task Definitions (Web, API, Workers), Services
│   ├── rds/                 # RDS PostgreSQL 16 Multi-AZ, Subnet Group, Parameter Group (force_ssl)
│   ├── redis/               # ElastiCache Redis 7.x Multi-AZ Replication Group, In-transit/At-rest encryption
│   └── rabbitmq/            # Amazon MQ RabbitMQ 3.13 Quorum Cluster, AMQP 0-9-1 TLS, Secrets Manager
├── environments/            # Tiered environment deployment roots
│   ├── dev/                 # Single-AZ cost-optimized baseline (Option A reference)
│   ├── qa/                  # Multi-tenant test environment
│   ├── staging/             # Exact production mirror for release verification
│   └── production/          # Multi-AZ HA baseline (Option B reference) with safety gate
├── policies/                # Parameterized IAM and bucket policy JSON templates
│   ├── s3_bucket_policy.json.tpl
│   ├── ecs_task_execution_policy.json.tpl
│   └── ecs_task_role_policy.json.tpl
├── scripts/                 # Automated validation and linting test runners
│   ├── validate_all.ps1     # PowerShell validation suite (Windows)
│   └── validate_all.sh      # Bash validation suite (Linux / CI)
└── docs/                    # Technical architecture & operational documentation
    ├── ARCHITECTURE_MAPPING.md
    ├── REMOTE_STATE_AND_BOOTSTRAP.md
    └── UPGRADE_PROCEDURE.md
```

---

## Core Architecture Principles

1. **Dual Engine Support:** Fully validated against **OpenTofu v1.9.0** (MPL-2.0 recommended) and **HashiCorp Terraform >= 1.10.0**.
2. **Native S3 State Locking:** Leverages `use_lockfile = true` within the S3 backend, using native S3 `.tflock` objects and eliminating the operational complexity and cost of DynamoDB lock tables.
3. **Zero Plaintext Secrets:** Master database credentials use RDS native AWS Secrets Manager integration (`manage_master_user_password = true`). RabbitMQ passwords are randomly generated and securely stored in Secrets Manager. No passwords or tokens are stored in `.tfstate` or Git.
4. **Tenant Isolation & RLS:** Network and application layers enforce strict tenant isolation. PostgreSQL parameters mandate SSL (`rds.force_ssl = 1`), and PgBouncer connection pooling uses `transaction` mode with `server_reset_query = DISCARD ALL`.
5. **Decoupled Acyclic Security Groups:** All 8 security groups (`alb`, `web`, `api`, `workers`, `pgbouncer`, `rds`, `redis`, `rabbitmq`) use standalone `aws_security_group_rule` resources to prevent Terraform dependency cycles.
6. **Regulatory & Tax Compliance:** Document storage enforces S3 Object Lock in `COMPLIANCE` mode with 2,190 days retention (6 years) to satisfy Indian GST invoice legal requirements.
7. **Production Safety Gate:** Deployment to `production` requires explicit authorization (`production_apply_authorized = true`) to prevent accidental destruction or provisioning.

---

## Validation & Linting

Run the automated validation suite locally or in CI/CD:

```powershell
# Windows PowerShell
powershell -ExecutionPolicy Bypass -File infrastructure/terraform/scripts/validate_all.ps1

# Linux / CI
./infrastructure/terraform/scripts/validate_all.sh
```

Every module and environment undergoes:
* `tofu fmt -check` (Canonical formatting)
* `tofu validate` (Syntax and configuration schema validation)
* `tflint` (Static code analysis)
* `tfsec` (Static security and compliance analysis)
