# SocietySphere — Monitoring & Observability Module

## Overview
Provisions centralized logging and operational alarms for SocietySphere:
* **Encrypted CloudWatch Log Groups:** Dedicated log streams for Web, API, and Workers encrypted via KMS CMK.
* **SLO Metric Alarms:** Tracks container CPU/memory pressure and database storage exhaustion.
* **SNS Alert Routing:** Routes alarms to security and operations teams.

## Inputs
| Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `environment` | string | n/a | Environment name |
| `kms_key_arn` | string | n/a | KMS CMK ARN for log group encryption |
| `log_retention_days` | number | `30` | Log retention period |
| `alert_sns_topic_arn` | string | `""` | SNS topic for critical alerts |

## Outputs
* `web_log_group_name`, `api_log_group_name`, `workers_log_group_name`: Log group names.
* `api_cpu_alarm_arn`, `rds_cpu_alarm_arn`: Alarm ARNs.
