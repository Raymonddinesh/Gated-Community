# SocietySphere — Development Environment

## Overview
Deploys a cost-optimized, single-AZ baseline topology for SocietySphere development and internal testing:
* **Compute:** 1 task each for Web, API, and Workers on ECS Fargate.
* **Database:** Single-AZ RDS PostgreSQL 16 on `db.t4g.medium` with 7-day backup retention.
* **Cache:** Single-node ElastiCache Redis on `cache.t4g.small`.
* **Broker:** Single-instance Amazon MQ RabbitMQ on `mq.t3.micro`.
* **Network:** Single NAT Gateway to minimize monthly non-production spend.
* **Estimated Cost:** ~$250/month (~₹21,000/month) conforming to Option A.

## Validation
```bash
tofu init -backend=false
tofu validate
```
