# SocietySphere — Master Project Roadmap

**Document Version:** 1.0.0  
**Current Engineering Baseline:** Phase 22F Complete (Pending Architectural Sign-Off)  
**Current Application Migration Head:** `20261102_0025_saas_billing_automation.py`  
**Primary IaC Engine:** OpenTofu v1.9.0 / HashiCorp Terraform >= 1.10.x  

---

## 1. Executive Summary & Governance Model

SocietySphere is an enterprise-grade multi-tenant SaaS platform built for apartment societies and housing cooperatives. The platform enforces strict multi-tenancy via PostgreSQL Row-Level Security (RLS), defense-in-depth authorization across 13 distinct user personas, deterministic financial accounting, and fully reproducible AWS infrastructure as code.

### The Four-Step Engineering Governance Gate
Every engineering phase must strictly adhere to the following sequence:
1. **Implementation:** Infrastructure or application code written strictly within authorized boundaries.
2. **Automated Validation:** Rigorous execution of syntax checks, unit/integration suites, security scanners (tfsec, Checkov, ruff, mypy), and custom compliance tests.
3. **Independent Principal Architect Review:** Comprehensive architectural and security audit evaluating edge cases, blast radius, failure modes, and compliance.
4. **Formal Sign-Off & Lock:** Architectural approval documented in a permanent report before the next phase is unlocked.

---

## 2. Completed Project Milestones (Phases 1–21)

| Phase | Description | Status | Head Migration / Deliverable |
|---|---|---|---|
| **Phase 1–10** | Core scaffolding, multi-tenant database models, identity & JWT authentication, unit management, resident profiles, visitor gatekeeping, and basic ticketing. | **LOCKED** | Foundation migrations |
| **Phase 11–18** | Facility booking, committee governance, emergency broadcasts, notices, vendor master, and audit logs. | **LOCKED** | Domain models & APIs |
| **Phase 19** | Pre-production security audit, domain isolation, and tenant boundary verification. | **LOCKED** | `PHASE_19_FINAL_ARCHITECT_VALIDATION_REPORT.md` |
| **Phase 20** | Application UAT, end-to-end integration testing, accessibility ("Easy Mode") verification, and browser automation. | **LOCKED** | `PHASE_20_RELEASE_READINESS_REPORT.md` |
| **Phase 21A–21D** | SaaS billing domain redesign, rule-based maintenance fees, interest calculation, payment allocation, and financial report services. | **LOCKED** | Architecture specs & reports |
| **Phase 21E-1–21E-6** | SaaS Billing Engine implementation, tax invoicing, credit notes, PDF generation, worker event queues, and automated browser UAT. | **LOCKED** | `20261102_0025_saas_billing_automation.py` |

---

## 3. Current Phase 22 AWS Infrastructure Foundations

| Stage | Focus Area | Status | Key Deliverables |
|---|---|---|---|
| **Phase 22A** | Production Architecture Assessment & AWS Sizing | **LOCKED** | Reference architecture in `ap-south-1` Mumbai |
| **Phase 22B** | Terraform/OpenTofu Core Foundations | **LOCKED** | Remote S3 backend, DynamoDB locking, KMS CMK, 9 modular components |
| **Phase 22C** | CI/CD Pipeline & Automated Testing | **LOCKED** | GitHub Actions workflows (`infrastructure-validate.yml`, `terraform-compat.yml`, `security-scan.yml`) |
| **Phase 22D** | AWS Networking & Security Infrastructure | **LOCKED** | Dedicated VPC (`10.0.0.0/16`), 3 AZs, public/app/data subnets, NAT Gateways, VPC Endpoints, Flow Logs |
| **Phase 22E** | Application Runtime & Container Infrastructure | **LOCKED** | ECS Fargate clusters, ECR repositories, ALB with path routing, Secrets Manager integration, CloudWatch logging |
| **Phase 22F** | Database, Redis, RabbitMQ & Storage Infrastructure | **PENDING REVIEW** | RDS PostgreSQL 16 Multi-AZ, RDS Proxy, ElastiCache Redis 7.1, Amazon MQ RabbitMQ 3.13, S3 Private Document Storage with Object Lock |

---

## 4. Crucial Phase 22F Handover Notice & Outstanding Review Items

> [!WARNING]
> **Phase 22F implementation is reported complete and validated (144 Checkov checks passed, 76 compliance tests passed, 13/13 dual IaC passed), but FINAL PRINCIPAL ARCHITECT APPROVAL IS PENDING.**
>
> The incoming developer or team **MUST NOT** consider Phase 22F locked or proceed with Phase 22G until the following outstanding architecture review items are formally audited and approved:

### Outstanding Architecture Review Items:
1. **RDS Proxy PostgreSQL Session-Pinning Compatibility:**
   - Audit whether all application queries, custom extensions, and third-party libraries respect transaction-level pooling without triggering unwanted connection pinning.
   - Confirm `session_pinning_filters = ["EXCLUDE_VARIABLE_SETS"]` operates reliably with asyncpg prepared statements (`statement_cache_size = 0`).
2. **RDS Proxy versus PgBouncer Architecture Decision:**
   - Evaluate whether AWS RDS Proxy (fully managed, integrated with Secrets Manager, IAM auth) or self-hosted PgBouncer on ECS provides superior connection multiplexing and transaction throughput under high write contention.
3. **Live Proxy-Path Tenant RLS Isolation Verification:**
   - Conduct empirical integration verification over a real RDS Proxy endpoint ensuring `SELECT set_config('app.current_society_id', :val, true)` with `is_local = true` completely clears tenant state upon connection reuse, preventing cross-tenant data leakage.
4. **Seven-Year S3 Object Lock Compliance Mode Retention Review:**
   - Review regulatory and operational implications of S3 Object Lock in **Compliance Mode** vs **Governance Mode**.
   - Note: In Compliance Mode, objects *cannot* be deleted or modified by ANY AWS account (including root) until the 7-year retention period expires. Evaluate whether test/staging environments require Governance Mode.
5. **RabbitMQ Classic Mirrored versus Quorum Queue Decision:**
   - Because message priority (`x-max-priority: 10`) is required for invoice recalculation in Phase 21, classic mirrored queues are used.
   - Audit RabbitMQ 3.13 quorum queue deprecation timelines and verify classic queue failover resilience in Amazon MQ `CLUSTER_MULTI_AZ`.
6. **Mandatory Production Redis Authentication Verification:**
   - Confirm mandatory token-based Redis AUTH (`auth_token`) enforcement in production environments and seamless token rotation via AWS Secrets Manager.

---

## 5. Remaining Roadmap (Phases 22G – 22J)

### Phase 22G — Observability, Backup & Disaster Recovery
- **CloudWatch Operational Dashboards:** Unified telemetry for ALB (HTTP 5xx, latency, target response time), ECS (CPU, memory, task restart counts), RDS (CPU, free storage, connection count, replica lag), ElastiCache (cache hit ratio, memory pressure), and RabbitMQ (queue depths, message rates).
- **Metric Alarms & Alerting:** Integration with AWS SNS and encrypted notification fanout to Slack/PagerDuty/Email.
- **Automated Backup & Disaster Recovery:** AWS Backup policies across RDS, EFS (if applicable), and S3 cross-region replication for critical ledger archives.
- **Chaos & Failover Runbooks:** Documented recovery time objective (RTO < 15 min) and recovery point objective (RPO < 5 min).

### Phase 22H — Security Assessment & Hardening
- **Penetration Testing & Vulnerability Assessment:** Comprehensive scan across API endpoints, JWT lifecycle, and CORS policies.
- **AWS WAFv2 Rules:** Web Application Firewall rate limiting, IP reputation lists, and OWASP Top 10 managed rules.
- **AWS GuardDuty & AWS Config:** Threat detection, anomaly monitoring, and automated configuration compliance checks.
- **KMS Key Rotation & IAM Credential Expiry:** Automated annual CMK rotation and periodic Secrets Manager password rotation policies.

### Phase 22I — Performance & Scalability
- **Synthetic Load Testing:** High-concurrency benchmarking using Locust or k6 simulating concurrent resident logins, gatekeeper visitor entries, and month-end automated invoice generation.
- **Database Query & Index Optimization:** `pg_stat_statements` analysis, vacuum tuning, and execution plan verification on high-volume tables.
- **ECS Container & RDS Autoscaling Calibration:** Fine-tuning step scaling policies, target tracking thresholds, and connection pool bounds.

### Phase 22J — User Acceptance Testing (UAT) & Commercial Launch
- **Production Staging Deployment:** Full zero-downtime deployment rehearsals.
- **Pilot Society Onboarding:** Onboarding 3 diverse pilot residential societies (50 units, 250 units, 1,000 units).
- **DNS Cutover & SSL Verification:** Final Route 53 health-checked failover routing and zero-downtime certificate issuance.
- **Commercial Go-Live:** General availability release and handover to customer operations.

---

## 6. Handover Documentation & Implementation Tracking

Detailed task tracking, verified commands, and runbooks are maintained across the following documents:
- **[PENDING_TASKS.md](file:///c:/SocApp/PENDING_TASKS.md)**: Active tracking table for Phase 22F pending approvals and implementation plans for Phases 22G–22J.
- **[HANDOVER_COMMANDS.md](file:///c:/SocApp/HANDOVER_COMMANDS.md)**: Verified command reference categorized by safety levels (`[SAFE-LOCAL]`, `[LOCAL-MUTATING]`, `[REQUIRES-LOCAL-STACK]`, `[REQUIRES-AWS-CREDS]`, `[LIVE-INFRASTRUCTURE]`, `[DESTRUCTIVE-APPROVAL-REQUIRED]`).
- **[HANDOVER_GUIDE.md](file:///c:/SocApp/HANDOVER_GUIDE.md)**: Master technical project handover guide.
- **[scripts/handover/README.md](file:///c:/SocApp/scripts/handover/README.md)**: Lightweight, non-destructive helper scripts for developer onboarding and state inspection.
- **[DEPLOYMENT_GUIDE.md](file:///c:/SocApp/DEPLOYMENT_GUIDE.md)**: Multi-environment deployment runbook.
- **[SECURITY.md](file:///c:/SocApp/SECURITY.md)**: Multi-tenant security architecture and compliance standards.
