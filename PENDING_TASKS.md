# SocietySphere — Pending Tasks & Architectural Roadmap

**Document Version:** 1.0.0  
**Date:** November 5, 2026  
**Audience:** Incoming Lead Developer, Principal Cloud Architect, Database Specialist, DevSecOps Engineer  
**Baseline Status:** Phase 22F Complete (Pending Architectural Approval) | Phases 22G–22J Unstarted  
**Current Migration Head:** `20261102_0025_saas_billing_automation.py`  

---

## 1. Governance & Handover Notice

Every engineering phase in SocietySphere adheres to the strict **Four-Stage Governance Model**:
$$\text{Implementation} \longrightarrow \text{Automated Validation} \longrightarrow \text{Principal Architect Review} \longrightarrow \text{Formal Approval \& Lock}$$

> [!WARNING]
> **Phase 22F implementation is reported complete and empirically validated (144 Checkov checks passed, 76 compliance tests passed, 13/13 dual IaC passed), but FINAL PRINCIPAL ARCHITECT APPROVAL IS PENDING.**
>
> The items below represent active blocking items that must be reviewed, audited, and signed off before Phase 22F can be locked and before Phase 22G may begin. Do not silently mark any item resolved.

---

## 2. Phase 22F — Pending Principal Architect Approval Items

### Task 22F-1: Verify PostgreSQL RDS Proxy Session-Pinning Compatibility with asyncpg
- **Status:** `PENDING REVIEW`
- **Required Action:**
  - Audit asyncpg connection pool initialization parameters in `apps/api/src/database/session.py`.
  - Ensure asyncpg client connection string specifies `statement_cache_size=0` (or `prepared_statement_cache_size=0`) when connecting through RDS Proxy.
  - Verify that query preparation does not trigger persistent session pinning (`EXCLUDE_VARIABLE_SETS` filter behavior under burst prepared statement execution).
- **Dependencies:**
  - `modules/rds/main.tf` RDS Proxy configuration.
  - Live AWS RDS Proxy staging endpoint.
- **Validation Criteria:**
  - RDS Proxy CloudWatch metric `DatabaseConnectionsCurrentlyPinned` remains at `0` under high concurrent query loads.
  - No `DuplicatePreparedStatementError` or `PreparedStatementDoesNotExistError` exceptions logged by asyncpg.
- **Evidence Required:**
  - CloudWatch metric dashboard screenshot/logs showing zero connection pinning under concurrent synthetic traffic.
  - Profiling report of asyncpg connection pool execution.
- **Approval Required:** Principal Database Architect & Senior Backend Engineer.

---

### Task 22F-2: Document RDS Proxy versus PgBouncer Architecture Decision Record (ADR)
- **Status:** `PENDING REVIEW`
- **Required Action:**
  - Draft an Architectural Decision Record (`docs/adr/ADR-012-RDS-Proxy-vs-PgBouncer.md`) documenting the trade-off evaluation.
  - Compare AWS RDS Proxy (managed, native Secrets Manager integration, IAM DB authentication, automatic failover awareness) against self-hosted PgBouncer on ECS Fargate (sub-millisecond latency, lower AWS endpoint cost, explicit fine-grained `pool_mode = transaction`).
- **Dependencies:**
  - Phase 22A Architecture Assessment.
  - Phase 22F preliminary cost modeling ($15/mo per proxy endpoint).
- **Validation Criteria:**
  - Comprehensive comparison matrix covering cost, operational overhead, failover latency, session pinning behavior, and connection capacity.
  - Clear rationale approved for the selected production approach.
- **Evidence Required:**
  - Published and reviewed `docs/adr/ADR-012-RDS-Proxy-vs-PgBouncer.md`.
- **Approval Required:** Principal Solutions Architect & Lead Cloud Architect.

---

### Task 22F-3: Perform Actual RDS Proxy-Path Tenant RLS Isolation Testing
- **Status:** `PENDING REVIEW`
- **Required Action:**
  - Perform live integration testing against an actual RDS Proxy instance using two distinct tenant sessions (`Society A` and `Society B`).
  - Verify that `SELECT set_config('app.current_society_id', :val, true)` with `is_local = true` completely clears tenant state upon connection return to the pool.
  - Attempt forced connection recycling between interleaved transactions to verify that Tenant B can never observe uncommitted or committed data belonging to Tenant A.
- **Dependencies:**
  - Staging environment deployment of RDS PostgreSQL + RDS Proxy.
  - Automated integration test suite simulating interleaved multi-tenant transactions.
- **Validation Criteria:**
  - 100% tenant boundary isolation across 10,000 interleaved concurrent transactions.
  - Zero cross-tenant data leakage detected.
  - Automatic purging of `app.current_society_id` verified via transaction completion hooks.
- **Evidence Required:**
  - Integration test execution logs demonstrating interleaved concurrent transactions with zero data contamination.
  - PostgreSQL server query audit log proving session sanitization.
- **Approval Required:** Principal Security Architect & Database Specialist.

---

### Task 22F-4: Review S3 Seven-Year Object Lock Compliance Mode & Obtain CA/Legal Approval
- **Status:** `PENDING REVIEW`
- **Required Action:**
  - Review the operational and regulatory consequences of S3 Object Lock configured in `COMPLIANCE` mode with a 2,555-day (7-year) retention period for billing PDFs.
  - Obtain formal confirmation from SocietySphere Legal Counsel and Chartered Accountant (CA) on Indian GST statutory compliance requirements (Section 36 of CGST Act requires preservation of records for 72 months from the due date of furnishing annual returns).
  - Determine whether `dev`, `qa`, and `staging` environments should use `GOVERNANCE` mode (allowing deletion with special IAM permissions) to avoid accumulating non-deletable test artifacts.
- **Dependencies:**
  - `modules/storage/main.tf` S3 bucket Object Lock configuration.
  - Legal & Financial Audit review.
- **Validation Criteria:**
  - Formal sign-off on retention periods for production vs non-production environments.
  - Staging/Dev environment updated to `GOVERNANCE` mode if full `COMPLIANCE` mode is deemed too restrictive for testing.
- **Evidence Required:**
  - Signed Legal/CA compliance approval memo attached to project records.
  - Environment variable matrix documenting retention modes per environment.
- **Approval Required:** General Legal Counsel, Advisory Chartered Accountant, and Lead Cloud Architect.

---

### Task 22F-5: Review RabbitMQ Classic Mirrored versus Quorum Queues Decision
- **Status:** `PENDING REVIEW`
- **Required Action:**
  - Re-examine the queue topology in `apps/api/src/events/queue_topology.py` where `billing-operations-queue` uses message priorities (`x-max-priority: 10`).
  - Because RabbitMQ Quorum Queues do not support message priorities, classic mirrored queues are provisioned on Amazon MQ `CLUSTER_MULTI_AZ`.
  - Evaluate RabbitMQ 3.13 / 4.0 deprecation roadmap for classic mirrored queues and evaluate whether priority queues can be redesigned as separate dedicated FIFO queues (e.g., `billing-high-priority`, `billing-standard`) to enable Quorum Queue adoption.
- **Dependencies:**
  - `apps/api/src/events/queue_topology.py` queue declarations.
  - Amazon MQ RabbitMQ 3.13 deprecation schedule.
- **Validation Criteria:**
  - Architectural agreement on whether to keep classic queues with `x-max-priority` or refactor worker topology into multi-queue tiering before production launch.
- **Evidence Required:**
  - Technical memorandum documenting classic queue longevity and failover performance under node failure.
- **Approval Required:** Principal Messaging Architect & Senior Backend Engineer.

---

### Task 22F-6: Verify Mandatory Production Redis Authentication & Secrets Manager Rotation
- **Status:** `PENDING REVIEW`
- **Required Action:**
  - Verify that `auth_token` input is populated in `environments/production/terraform.tfvars` from AWS Secrets Manager.
  - Confirm Redis authentication handshake in `apps/api/src/cache/redis_client.py` when `REDIS_AUTH_TOKEN` is supplied.
  - Test dynamic secret rotation for Redis AUTH without causing downtime in running API and background worker tasks.
- **Dependencies:**
  - `modules/redis/main.tf` replication group configuration.
  - AWS Secrets Manager secret definition for Redis token.
- **Validation Criteria:**
  - Connecting to production Redis without AUTH token fails immediately (`NOAUTH Authentication required`).
  - Connecting with valid AUTH token succeeds.
  - Scheduled rotation process documented and verified.
- **Evidence Required:**
  - Successful authentication trace log and Secrets Manager rotation audit log.
- **Approval Required:** DevSecOps Specialist & Lead Cloud Architect.

---

## 3. Future Roadmap: Phases 22G through 22J

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   UPCOMING ROADMAP PHASES                                        │
├─────────────────────┬─────────────────────┬─────────────────────┬────────────────────────────────┤
│ Phase 22G           │ Phase 22H           │ Phase 22I           │ Phase 22J                      │
│ Observability,      │ Security Assessment │ Performance &       │ UAT & Commercial               │
│ Backup & DR         │ & Hardening         │ Scalability         │ Launch                         │
│ [NOT STARTED]       │ [NOT STARTED]       │ [NOT STARTED]       │ [NOT STARTED]                  │
└─────────────────────┴─────────────────────┴─────────────────────┴────────────────────────────────┘
```

---

### Phase 22G — Observability, Backup & Disaster Recovery
- **Status:** `NOT STARTED` (Blocked on Phase 22F sign-off)
- **Objectives:** Establish comprehensive telemetry, automated monitoring, alerting fanout, multi-tier backup strategies, and documented disaster recovery runbooks.
- **Implementation Tasks:**
  1. Create CloudWatch Metric Alarms for ECS (CPU > 80%, Memory > 80%, container restart count).
  2. Create CloudWatch Alarms for RDS PostgreSQL (CPU > 75%, FreeStorageSpace < 10GB, DatabaseConnections > 80% pool, ReplicaLag > 30s).
  3. Create CloudWatch Alarms for ElastiCache Redis (EngineCPUUtilization > 75%, SwapUsage > 0, CacheHitRate < 80%).
  4. Create CloudWatch Alarms for RabbitMQ (MessageCount in `dead-letter-queue` > 0, consumer count == 0).
  5. Create ALB Metric Alarms (HTTP 5xx rate > 1%, TargetResponseTime > 1.5s).
  6. Deploy unified CloudWatch Dashboard visualizing all service tiers.
  7. Configure AWS SNS topic with KMS CMK encryption and notification fanout to Slack/PagerDuty.
  8. Define AWS Backup plans for RDS daily snapshots (35-day retention) and cross-region replication to `ap-south-2` (Hyderabad).
  9. Author Disaster Recovery Runbook documenting RTO (< 15 min) and RPO (< 5 min).
- **Validation Criteria:**
  - Synthetic alarm triggers verified in staging with automated alerts received on SNS endpoints.
  - Backup restore drills successfully restoring PostgreSQL snapshot to an isolated staging database within 15 minutes.
- **Completion Conditions:**
  - Complete CloudWatch telemetry active across all environments.
  - Phase 22G Implementation & Verification Report approved and locked.

---

### Phase 22H — Security Assessment & Hardening
- **Status:** `NOT STARTED`
- **Objectives:** Perform end-to-end cloud security assessment, integrate AWS WAFv2 perimeter filtering, enable automated threat intelligence, and enforce cryptographic key rotation.
- **Implementation Tasks:**
  1. Deploy AWS WAFv2 on the Application Load Balancer with AWS Managed Rule Sets:
     - Common Rule Set (`AWSManagedRulesCommonRuleSet`).
     - Known Bad Inputs (`AWSManagedRulesKnownBadInputsRuleSet`).
     - SQL Database Rule Set (`AWSManagedRulesSQLiRuleSet`).
     - IP Reputation List (`AWSManagedRulesAmazonIpReputationList`).
     - Rate-based rule limiting requests to 2,000 per 5 minutes per IP.
  2. Enable AWS GuardDuty in `ap-south-1` for intelligent threat and anomaly detection.
  3. Configure AWS Config rules for continuous compliance auditing (encrypted EBS volumes, S3 public access blocks, restricted security groups).
  4. Enable automated annual rotation on all AWS KMS Customer Managed Keys.
  5. Conduct authenticated API vulnerability scanning (OWASP Top 10, JWT replay, CSRF, IDOR).
  6. Perform container vulnerability scanning with Trivy and Amazon Inspector.
- **Validation Criteria:**
  - WAF blocks synthetic SQL injection and high-rate brute force probes with 403 Forbidden.
  - Zero high or critical vulnerabilities identified in container images and API endpoints.
- **Completion Conditions:**
  - Formal Security Architecture Assessment and Penetration Testing Report signed off by Security Lead.

---

### Phase 22I — Performance & Scalability Calibration
- **Status:** `NOT STARTED`
- **Objectives:** Validate system performance under peak concurrent user loads, calibrate autoscaling policies, and eliminate database query bottlenecks.
- **Implementation Tasks:**
  1. Author synthetic load testing suites in k6 / Locust simulating:
     - Peak morning gatekeeper check-ins (100 concurrent visitor check-ins/sec).
     - Month-end automated invoice generation across 50 societies (10,000 invoices in < 5 minutes).
     - Concurrent resident mobile app usage (500 concurrent active users).
  2. Calibrate ECS Fargate autoscaling target tracking policies:
     - Scale out at 70% CPU or 1,000 requests/target; scale in with 300s stabilization window.
  3. Profile slow queries using `pg_stat_statements` on PostgreSQL 16.
  4. Optimize database indexes on `billing_invoices`, `ledger_entries`, `visitor_logs`, and `resident_profiles`.
  5. Calibrate Redis connection pool bounds and RabbitMQ prefetch counts (`prefetch_count = 10`).
- **Validation Criteria:**
  - 95th percentile API response time ($p95$) remains $< 250\text{ ms}$ under peak simulated load.
  - Zero dropped connections or 5xx server errors during container scale-out events.
- **Completion Conditions:**
  - Performance & Load Testing Benchmark Report approved and locked.

---

### Phase 22J — User Acceptance Testing (UAT) & Commercial Launch
- **Status:** `NOT STARTED`
- **Objectives:** Final pre-flight verification, Route 53 production DNS cutover, pilot society onboarding, and general availability commercial launch.
- **Implementation Tasks:**
  1. Execute complete staging environment zero-downtime cutover dry run.
  2. Onboard 3 pilot residential housing societies representing varied scales:
     - Society 1: Boutique society (40 units, flat maintenance billing).
     - Society 2: Mid-sized society (250 units, area-based sq.ft. billing + amenities).
     - Society 3: Large gated community (1,200 units, multi-tower, complex rule-based billing + visitor kiosks).
  3. Conduct end-to-end UAT with designated pilot Society Treasurers, Gatekeepers, and Residents.
  4. Configure Route 53 public hosted zones with latency-based and health-checked DNS routing.
  5. Provision and validate production ACM TLS certificates for `*.societysphere.com`.
  6. Finalize production operations runbook and hand over to customer support and operations team.
- **Validation Criteria:**
  - 100% acceptance sign-off from all 3 pilot society committees.
  - Zero critical defects reported during the 14-day pilot operational period.
- **Completion Conditions:**
  - Commercial launch authorization signed by Executive Leadership.
