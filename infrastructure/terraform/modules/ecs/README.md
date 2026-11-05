# SocietySphere — Amazon ECS Fargate Module

## Overview
Provisions the serverless container compute infrastructure on AWS ECS with Fargate:
* **Container Insights:** CloudWatch Container Insights enabled for CPU, memory, and network metrics.
* **Three Decoupled Services:**
  1. `societysphere-web`: Next.js 14 Standalone SSR frontend container.
  2. `societysphere-api`: FastAPI backend API container attached to ALB target group `/health/ready`.
  3. `societysphere-workers`: Background workers executing the supervised `asyncio.TaskGroup` (Scheduler leader, Billing consumer, Outbox dispatcher, Stale job sweeper).
* **Zero Host Vulnerability:** AWS Fargate eliminates underlying EC2 host patching and root breakout vectors. All tasks execute under unprivileged user `1001:1001`.
* **Zero-Downtime Rolling Updates:** Enforces `minimum_healthy_percent = 100` and `maximum_percent = 200`.

## Incomplete Functionality / Provisioning Dependencies
* Target Group ARNs default to empty strings during Phase 22B and will be wired to ALB listeners in Phase 22D.
* Container images default to local placeholders until ECR image push is configured in Phase 22F.
