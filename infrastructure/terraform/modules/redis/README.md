# SocietySphere — Amazon ElastiCache Redis Module

## Overview
Provisions a high-availability Amazon ElastiCache Redis cluster for session caching, sliding-window rate limiting, and atomic scheduler distributed lease management (`SET NX EX`):
* **In-Transit & At-Rest Encryption:** TLS mandated for all cluster connections; storage encrypted using KMS CMK.
* **Multi-AZ Auto-Failover:** Primary node in AZ-a replicated synchronously to Read Replica in AZ-b with automatic failover (< 15s).
* **Memory Eviction Policy:** Configured with `volatile-lru` to protect permanent lease keys from accidental cache eviction.

## Inputs
| Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `environment` | string | n/a | Environment name |
| `data_subnet_ids` | list(string) | n/a | Isolated data subnet IDs |
| `sg_redis_id` | string | n/a | Security group ID for Redis |
| `kms_key_arn` | string | n/a | KMS CMK ARN for encryption |
| `node_type` | string | `"cache.m6g.large"` | Compute node type |
| `multi_az` | bool | `true` | Multi-AZ auto-failover |

## Outputs
* `primary_endpoint_address`: Primary read/write address.
* `reader_endpoint_address`: Read-only replica address.
* `port`: Connection port (6379).
