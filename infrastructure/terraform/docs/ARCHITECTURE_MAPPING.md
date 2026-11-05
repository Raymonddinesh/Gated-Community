# Phase 22A Architecture Assessment to Phase 22B Terraform Module Mapping

This document provides a comprehensive, component-by-component traceability matrix mapping every architectural decision from **Phase 22A: Production Infrastructure & Architecture Assessment** to its corresponding Terraform/OpenTofu implementation in **Phase 22B**.

---

## 1. Traceability Matrix

| Phase 22A Assessment Component | Approved Architecture Decision | Phase 22B Module / Resource | Configuration Highlights |
|---|---|---|---|
| **VPC & Subnet Topology** | 3 AZs (`ap-south-1a`, `b`, `c`), 9 subnets (3 public, 3 private app, 3 private isolated data). CIDR `10.0.0.0/16` for prod. | `modules/networking` (`aws_vpc`, `aws_subnet`, `aws_route_table`, `aws_internet_gateway`, `aws_nat_gateway`) | - Public: `/24`<br>- App: `/22` (1,022 usable IPs per AZ)<br>- Isolated Data: `/24` (zero IGW/NAT routes)<br>- Multi-AZ NAT Gateways (Option B) vs Single NAT (Option A / Dev). |
| **VPC Flow Logs** | CloudWatch log group with KMS encryption and retention policies. | `modules/networking` (`aws_flow_log`, `aws_cloudwatch_log_group`) | KMS CMK encrypted, 365-day retention in production, 30-day in staging/qa/dev. |
| **Security Groups** | Zero wildcard ingress rules. Strict least-privilege inter-tier access. Standalone acyclic rules. | `modules/networking` (`aws_security_group`, `aws_security_group_rule`) | 8 decoupled security groups (`alb`, `web`, `api`, `workers`, `pgbouncer`, `rds`, `redis`, `rabbitmq`) using separate rule resources to prevent circular dependency deadlocks. |
| **PostgreSQL Database** | RDS PostgreSQL 16 on Graviton (`db.m6g.xlarge` prod, `db.t4g.medium` dev), Multi-AZ, gp3 storage, zero plaintext passwords. | `modules/rds` (`aws_db_instance`, `aws_db_subnet_group`, `aws_db_parameter_group`) | - `manage_master_user_password = true` (delegated to AWS Secrets Manager)<br>- `rds.force_ssl = 1`<br>- gp3 autoscaling (100 GB to 500 GB)<br>- Multi-AZ synchronous replication<br>- 35-day backup retention with KMS encryption<br>- Deletion protection enabled. |
| **Tenant Isolation & RLS** | Row-Level Security enforced at DB engine level. PgBouncer session cleanup. | `modules/rds` (parameters) + `modules/ecs` (task env) | PgBouncer runs in `transaction` mode with `DISCARD ALL` on reset, paired with SQLAlchemy session tenant-context binding (`app.current_society_id`). |
| **Redis Cache & Leases** | ElastiCache Redis 7.x Cluster (`cache.m6g.large` prod), Multi-AZ auto-failover, encryption at rest and in transit. | `modules/redis` (`aws_elasticache_replication_group`, `aws_elasticache_subnet_group`, `aws_elasticache_parameter_group`) | - `transit_encryption_enabled = true`<br>- `at_rest_encryption_enabled = true` with KMS CMK<br>- Multi-AZ automatic failover<br>- `volatile-lru` eviction policy. |
| **Message Broker** | Amazon MQ RabbitMQ 3.13 Quorum Cluster (`mq.m5.large` prod), AMQP 0-9-1 over TLS (port 5671), Multi-AZ. | `modules/rabbitmq` (`aws_mq_broker`, `random_password`, `aws_secretsmanager_secret`) | - `CLUSTER_MULTI_AZ` quorum queue replication<br>- KMS encryption at rest<br>- General & audit logging to CloudWatch<br>- Dynamic credentials stored in AWS Secrets Manager. |
| **Container Compute** | ECS Fargate across private subnets. Next.js 14 web frontend, FastAPI API backend, Python workers. | `modules/ecs` (`aws_ecs_cluster`, `aws_ecs_task_definition`, `aws_ecs_service`) | - Fargate Spot support for non-prod<br>- Container Insights enabled<br>- Non-root container execution (`1001:1001`)<br>- Rolling updates (`min_healthy = 100%`, `max = 200%`). |
| **IAM & Secrets** | Least privilege execution roles. Zero plaintext credentials. KMS envelope encryption. | `modules/security` (`aws_kms_key`, `aws_iam_role`, `aws_secretsmanager_secret`) | - ECS Execution Role: scoped to ECR, CloudWatch, and specific Secrets ARNs<br>- ECS Task Role: scoped to S3 documents, SES, and KMS<br>- KMS CMK with annual rotation (`enable_key_rotation = true`). |
| **Document Storage & Legal Retention** | S3 bucket for invoices/receipts with Object Lock in COMPLIANCE mode (6-year retention for GST Act). | `modules/storage` (`aws_s3_bucket`, `aws_s3_bucket_object_lock_configuration`, `aws_s3_bucket_lifecycle_configuration`) | - Object Lock: `COMPLIANCE` (2,190 days) in production<br>- S3 Block Public Access (all 4 flags true)<br>- TLS-only enforcement policy<br>- Glacier transition after 90 days. |
| **Observability & Alarms** | Centralized CloudWatch logging with KMS CMK, metric alarms for CPU, Memory, RDS storage. | `modules/monitoring` (`aws_cloudwatch_log_group`, `aws_cloudwatch_metric_alarm`) | - ECS API CPU > 75%, Memory > 80%<br>- RDS CPU > 80%, RDS Free Storage Space < 10 GB. |
| **Remote State Architecture** | S3 backend with native S3 lockfile (`use_lockfile = true`), KMS CMK encryption, bucket versioning. | `bootstrap` (`aws_s3_bucket`, `aws_kms_key`) | Dual-compatible with OpenTofu 1.8+ and Terraform 1.10+. |
| **Production Safety Gate** | Production cannot be deployed by accident. Explicit authorization required. | `environments/production` (`terraform_data` lifecycle precondition) | Evaluates `var.production_apply_authorized == true` during plan and apply. |

---

## 2. Security Architecture Alignment

1. **Network Boundary:** All workload instances (ECS tasks, RDS database, Redis cluster, RabbitMQ broker) reside in private or isolated subnets with zero direct public internet accessibility.
2. **Transit Encryption:** TLS 1.2+ is strictly enforced for:
   - Client to ALB (HTTPS / ACM certificate).
   - Interservice ALB to API (HTTPS / TLS).
   - Application to PostgreSQL (`rds.force_ssl = 1`).
   - Application to Redis (`transit_encryption_enabled = true`).
   - Application to RabbitMQ (AMQPS / TLS port 5671).
   - Application to S3 (TLS bucket policy denying insecure transport).
3. **At-Rest Encryption:** All persistent state (RDS storage, Redis volumes, RabbitMQ storage, S3 state/documents, CloudWatch log groups) is encrypted using customer-managed KMS keys with automatic annual rotation.
4. **Secret Management:** Plaintext database credentials, API secrets, and message broker passwords are never committed to version control or Terraform state files. They are managed natively by AWS Secrets Manager with IAM-controlled runtime retrieval.
