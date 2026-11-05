# SocietySphere — Production Environment (Option B High-Availability Baseline)

## Architecture Overview

The `production` environment implements the full High-Availability and Multi-AZ topology designed and approved in **Phase 22A: Production Infrastructure & Architecture Assessment**.

* **Region:** AWS `ap-south-1` (Mumbai, India).
* **VPC CIDR:** `10.0.0.0/16`.
* **AZs:** 3 Availability Zones (`ap-south-1a`, `ap-south-1b`, `ap-south-1c`).
* **Subnets:**
  - 3 Public Subnets (`10.0.1.0/24`, `10.0.2.0/24`, `10.0.3.0/24`) with Internet Gateway.
  - 3 NAT Gateways (one per AZ) for high-availability outbound egress without cross-AZ failure domains.
  - 3 Application Subnets (`10.0.10.0/22`, `10.0.14.0/22`, `10.0.18.0/22`) hosting ECS Fargate tasks across AZs.
  - 3 Data Subnets (`10.0.30.0/24`, `10.0.31.0/24`, `10.0.32.0/24`) completely isolated with zero internet routes.

## Component Sizing & Redundancy

| Component | Architecture Specification | Redundancy & HA Mode |
|---|---|---|
| **Database (RDS)** | PostgreSQL 16 on `db.m6g.xlarge` (4 vCPU, 16 GiB RAM) | Multi-AZ synchronous standby, automated failover |
| **Storage (RDS)** | 100 GiB gp3 (3,000 IOPS, 125 MB/s), autoscaling to 500 GiB | KMS CMK encryption, 35-day backup retention, deletion protection |
| **Cache (Redis)** | Redis 7.x on `cache.m6g.large` (2 vCPU, 6.38 GiB RAM) | Multi-AZ Replication Group with 2 nodes and auto-failover |
| **Message Broker** | Amazon MQ RabbitMQ 3.13 on `mq.m5.large` | `CLUSTER_MULTI_AZ` quorum queue clustering |
| **Compute (ECS)** | Fargate tasks: Web (3), API (3), Workers (3) | Unprivileged non-root containers (`1001:1001`), Multi-AZ spread |
| **Document Storage** | S3 Bucket with KMS encryption and Object Lock | `COMPLIANCE` mode, 2,190 days retention (6-year Indian GST requirement) |
| **Observability** | KMS-encrypted CloudWatch Log Groups & Metric Alarms | 365-day log retention for ISO27001 / DPDP Act compliance |

## Strict Production Safety Guardrail

Deployment to production is protected by an explicit Terraform precondition guardrail:

```hcl
variable "production_apply_authorized" {
  description = "Explicit safety gate. Must be set to true to authorize execution in production."
  type        = bool
  default     = false
}
```

By default, executing `tofu plan` or `tofu apply` will abort execution if `production_apply_authorized` is `false`:
```
Error: Resource Precondition Failed
CRITICAL SAFETY GATE: Production deployment is locked by default. You must explicitly set 'production_apply_authorized = true' (via -var or production.tfvars) after formal Phase 22B architect sign-off.
```

To run a production plan during an authorized maintenance window:
```bash
tofu plan -var="production_apply_authorized=true"
```
