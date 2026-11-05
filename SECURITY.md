# SocietySphere — Security & Compliance Architecture

**Document Version:** 1.0.0  
**Security Classification:** Highly Confidential / Enterprise SaaS Baseline  
**Governing Standard:** Zero-Trust Cloud & Multi-Tenant Defense-in-Depth  

---

## 1. Security Policy & Vulnerability Reporting

The SocietySphere platform enforces strict security controls to protect resident privacy, gatehouse security logs, financial ledgers, and multi-tenant data integrity.

### Reporting a Vulnerability
If you discover a security vulnerability or potential credential leak:
- **DO NOT** create a public GitHub issue.
- Report immediately to the security team via: `security@societysphere.com`.
- Encrypt your disclosure using the platform PGP security key if sharing sensitive traces or proof-of-concept exploits.
- Security disclosures will be acknowledged within 24 hours with an initial severity triage.

---

## 2. Multi-Tenant Isolation & Row-Level Security (RLS)

SocietySphere guarantees absolute tenant boundary segregation:

### 2.1 Database-Level Segregation via PostgreSQL RLS
- Every tenant table contains a `society_id` UUID column.
- PostgreSQL Row-Level Security policies restrict `SELECT`, `INSERT`, `UPDATE`, and `DELETE` operations strictly to rows matching the current session variable:
  ```sql
  CREATE POLICY tenant_isolation_policy ON <table_name>
      AS RESTRICTIVE
      USING (society_id = NULLIF(current_setting('app.current_society_id', true), '')::uuid);
  ```

### 2.2 Transaction-Scoped Tenant Context
- In `apps/api/src/database/session.py`, tenant context is set using:
  ```python
  await session.execute(
      text("SELECT set_config('app.current_society_id', :val, true)"),
      {"val": str(society_id)},
  )
  ```
- The third parameter (`is_local = true`) guarantees that the setting is strictly scoped to the active transaction. Upon `COMMIT` or `ROLLBACK`, the setting is automatically purged by PostgreSQL.
- In conjunction with Amazon RDS Proxy configured with `session_pinning_filters = ["EXCLUDE_VARIABLE_SETS"]`, physical database connections in the connection pool are sanitized between transactions, eliminating any risk of cross-tenant data leakage.

---

## 3. Network Architecture & Perimeter Defense

```
  [Internet]
      │
      ▼ (Port 443 HTTPS only)
  [AWS Application Load Balancer] (Public Subnets: 10.0.1.0/24, 10.0.2.0/24, 10.0.3.0/24)
      │
      ▼ (Security Group: sg_alb -> sg_api / sg_web)
  [ECS Fargate Tasks] (Private App Subnets: 10.0.8.0/22, 10.0.12.0/22, 10.0.16.0/22)
      │
      ▼ (Security Group: sg_api / sg_worker -> sg_rds / sg_redis / sg_rabbitmq)
  [Data Tier: RDS / Redis / RabbitMQ] (Isolated Data Subnets: 10.0.20.0/22, 10.0.24.0/22, 10.0.28.0/22)
```

### Perimeter Controls:
1. **Three-Tier Subnet Hierarchy:**
   - **Public Tier:** Houses only the Application Load Balancer. No databases or containers reside here.
   - **Private App Tier:** Houses Next.js web, FastAPI API, and worker Fargate tasks. Outbound internet access flows exclusively through NAT Gateways.
   - **Isolated Data Tier:** Houses RDS PostgreSQL, ElastiCache Redis, and Amazon MQ RabbitMQ. Subnets have **zero route to the Internet Gateway or NAT Gateways**.
2. **Security Groups as Micro-Perimeters:**
   - Database (port 5432) accepts traffic ONLY from `sg_api` and `sg_worker`.
   - Redis (port 6379) accepts traffic ONLY from `sg_api` and `sg_worker`.
   - RabbitMQ (port 5671) accepts traffic ONLY from `sg_api` and `sg_worker`.
   - Ingress from `0.0.0.0/0` is strictly rejected across all internal tiers.
3. **VPC Endpoints:**
   - Internal traffic to AWS services (ECR API, ECR Docker, CloudWatch Logs, Secrets Manager, S3 Gateway) travels entirely over AWS private network links without traversing the public internet.

---

## 4. Encryption & Data Protection Standards

### 4.1 Data in Transit
- **External Traffic:** TLS 1.3 / TLS 1.2 enforced on the Application Load Balancer with secure cipher suites.
- **Internal Database:** `rds.force_ssl = 1` enforces mandatory SSL/TLS encryption for all PostgreSQL client connections.
- **Internal Cache:** ElastiCache Redis replication groups enforce `transit_encryption_enabled = true`.
- **Message Broker:** Amazon MQ enforces AMQPS (port 5671) over TLS.

### 4.2 Data at Rest (AWS KMS Customer Managed Keys)
- Dedicated KMS CMKs are provisioned per functional domain with automatic annual key rotation.
- **RDS PostgreSQL:** Volume storage, automated snapshots, and Performance Insights are KMS CMK encrypted.
- **S3 Document Storage:** Encrypted with SSE-KMS using dedicated CMK. S3 Bucket Keys are enabled to reduce KMS API overhead.
- **CloudWatch Logs:** Container logs and VPC Flow Logs are KMS CMK encrypted.

### 4.3 S3 Object Lock & GST Compliance
- Billing documents (invoices, receipts, credit notes) are archived with S3 Object Lock enabled.
- Lifecycle rules transition non-current records to Glacier after 30 days and enforce a 7-year (2,555-day) retention period in compliance with statutory financial and tax audit obligations.

---

## 5. Identity, Authentication & RBAC

1. **Authentication:**
   - Stateless JWT tokens with short-lived access tokens (15 minutes) and cryptographically bound refresh tokens (7 days).
   - Refresh token rotation and instant revocation via Redis denylist.
2. **Granular RBAC / ABAC across 13 Personas:**
   - Super Admin, Society Admin, Committee Member, Secretary, Treasurer, Auditor, Facility Manager, Gatekeeper, Resident (Owner), Resident (Tenant), Family Member, Daily Help/Staff, and System Worker.
   - Authorization is verified exclusively on the server side at the domain and application layers; client claims are never trusted blindly.

---

## 6. Secrets Management & Zero-Plaintext Standard

- **No Secrets in Source Control:** `.gitignore` excludes `.env`, `*.env`, `*.pem`, `*.key`, `*.cert`, `*credentials`.
- **AWS Secrets Manager Integration:** ECS containers inject credentials dynamically at launch using ECS secret value references (`secrets = [{ name = "DB_PASSWORD", valueFrom = aws_secretsmanager_secret.db.arn }]`).
- **Emergency Secret Rotation:**
  - If a secret or token is suspected of compromise, rotate it immediately in AWS Secrets Manager and trigger an ECS service rolling update (`tofu apply` or `aws ecs update-service --force-new-deployment`).
  - Redis cache tokens can be rotated dynamically without restarting the replication cluster.

---

## 7. Security Scanning & Continuous Compliance

The repository includes pre-configured security scanning tools integrated into CI/CD:
- **TFLint & tfsec:** Static analysis and security scanning for Terraform/OpenTofu code.
- **Checkov:** Static analysis tool for IaC compliance (144 checks verified in Phase 22F).
- **Ruff & Mypy:** Static Python linter and type-checker enforcing type safety and preventing unsafe syntax.
- **Automated Compliance Suite (`tests/test_compliance.py`):** 76 automated test assertions verifying encryption, IAM boundaries, subnet isolation, and security group sealing.
