# SocietySphere — Amazon MQ for RabbitMQ Module

## Overview
Provisions a managed RabbitMQ broker running on AWS Amazon MQ:
* **Native AMQP 0-9-1 Compatibility:** Connects directly with SocietySphere's existing `aio-pika` consumer and publisher code over TLS (port 5671) with zero client refactoring.
* **Quorum Queues & Multi-AZ Consensus:** In production, provisions a 3-node managed cluster across three Availability Zones using Raft consensus for queue persistence and zero message loss.
* **Credentials in Secrets Manager:** Generates a secure random administrator password and injects it into AWS Secrets Manager with KMS CMK encryption.
* **Audit & General Logs:** All connection lifecycle events and authentication audits streamed to CloudWatch Logs.

## Inputs
| Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `environment` | string | n/a | Environment name |
| `data_subnet_ids` | list(string) | n/a | Isolated data subnets |
| `sg_rabbitmq_id` | string | n/a | Security group ID for RabbitMQ |
| `kms_key_arn` | string | n/a | KMS CMK ARN for broker encryption |
| `host_instance_type` | string | `"mq.m5.large"` | Broker instance compute class |
| `deployment_mode` | string | `"CLUSTER_MULTI_AZ"` | Mode: SINGLE_INSTANCE or CLUSTER_MULTI_AZ |

## Outputs
* `broker_id`: Amazon MQ broker ID.
* `broker_arn`: Amazon MQ broker ARN.
* `amqp_ssl_endpoints`: AMQPS connection endpoint.
* `credentials_secret_arn`: Secrets Manager secret ARN.
