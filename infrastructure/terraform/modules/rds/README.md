# SocietySphere — Amazon RDS PostgreSQL 16 Module

## Overview
Provisions a production-hardened PostgreSQL 16 Multi-AZ database cluster on AWS RDS:
* **Multi-AZ Replication:** Physical block-level synchronous replication across Availability Zones with automated failover (< 60s).
* **Storage & Encryption:** General Purpose gp3 with provisioned storage autoscaling up to 500 GB, encrypted using KMS CMK.
* **Master Credentials Protection:** Uses AWS native `manage_master_user_password = true`, storing master passwords directly in AWS Secrets Manager without any plaintext variables or state file exposure.
* **Performance Insights & Audit:** CloudWatch query log exports enabled; slow queries (> 250ms) logged.
* **RLS & Parameter Tuning:** Configured with `rds.force_ssl = 1` and tuned memory pools for tenant Row-Level Security transactions.

## Inputs
| Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `environment` | string | n/a | Environment name |
| `data_subnet_ids` | list(string) | n/a | Isolated data subnet IDs |
| `sg_rds_id` | string | n/a | Security group ID for database |
| `kms_key_arn` | string | n/a | KMS CMK ARN for storage encryption |
| `instance_class` | string | `"db.m6g.large"` | RDS compute instance class |
| `multi_az` | bool | `true` | Multi-AZ high availability |
| `backup_retention_period` | number | `35` | Backup retention days |
| `deletion_protection` | bool | `true` | Prevent accidental DB deletion |

## Outputs
* `db_endpoint`: Database connection string (`hostname:port`).
* `db_address`: Database hostname.
* `master_user_secret_arn`: Secrets Manager ARN containing database credentials.
