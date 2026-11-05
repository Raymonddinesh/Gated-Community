# SocietySphere — Staging Environment

## Overview
Deploys a high-fidelity mirror of the production environment for user acceptance testing (UAT), pre-release verification, and performance benchmarking:
* **Architecture:** Full Multi-AZ across 3 Availability Zones (`ap-south-1a`, `ap-south-1b`, `ap-south-1c`).
* **Compute:** 2 tasks each for Web, API, and Workers on ECS Fargate.
* **Database:** Multi-AZ RDS PostgreSQL 16 on `db.m6g.large` with gp3 storage and 35-day backup retention.
* **Messaging:** Multi-AZ 3-Node Amazon MQ RabbitMQ quorum cluster.
* **Storage:** S3 Object Lock enabled in Governance mode for 30 days.

## Validation
```bash
tofu init -backend=false
tofu validate
```
