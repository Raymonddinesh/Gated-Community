# SocietySphere — Networking Module

## Overview
Provisions a hardened Amazon VPC in `ap-south-1` (Mumbai) across three Availability Zones conforming to the approved Phase 22A production architecture:
* **Public Subnets:** Hosts the Application Load Balancer (ALB) and Managed NAT Gateways.
* **Private Application Subnets:** Hosts ECS Fargate containers (Next.js 14 Web, FastAPI API, Background Workers, and PgBouncer pooler).
* **Isolated Data Subnets:** Hosts RDS PostgreSQL, ElastiCache Redis, and Amazon MQ RabbitMQ with zero internet access or NAT route.
* **VPC Endpoints:** Amazon S3 Gateway Endpoint attached to route tables for direct, free object transfers.
* **Security Groups:** Explicit, least-privilege ingress/egress firewall rules for all tiers.
* **VPC Flow Logs:** Captures all network IP traffic into Amazon CloudWatch Logs for ISO 27001 auditability.

## Inputs
| Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `environment` | string | n/a | Environment name (dev, qa, staging, production) |
| `vpc_cidr` | string | `10.0.0.0/16` | CIDR block for VPC |
| `availability_zones` | list(string) | `["ap-south-1a", "ap-south-1b", "ap-south-1c"]` | Target AZs |
| `single_nat_gateway` | bool | `true` | True for cost-optimization in dev/qa; false for multi-AZ in prod |
| `enable_vpc_flow_logs` | bool | `true` | Enable CloudWatch flow logs |

## Outputs
* `vpc_id`: VPC identifier.
* `public_subnet_ids`, `app_subnet_ids`, `data_subnet_ids`: Subnet ID arrays.
* `sg_*_id`: Security group IDs for ALB, Web, API, Workers, PgBouncer, RDS, Redis, and RabbitMQ.
