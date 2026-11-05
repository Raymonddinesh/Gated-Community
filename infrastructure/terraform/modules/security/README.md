# SocietySphere — Security & Cryptography Module

## Overview
Provisions encryption, IAM least-privilege roles, and secrets management boundaries for SocietySphere:
* **AWS KMS Customer Managed Key (CMK):** Multi-service envelope encryption with annual rotation.
* **AWS Secrets Manager:** Dedicated secret containers for database credentials and runtime application secrets.
* **ECS Task Execution Role:** Restricted to pulling ECR images, creating CloudWatch log streams, and decrypting Secrets Manager values.
* **ECS Task Role:** Restricted to scoped S3 documents access, SES email dispatch, and KMS cryptographic envelope operations.

## Inputs
| Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `environment` | string | n/a | Environment identifier (dev, qa, staging, production) |
| `documents_bucket_arn` | string | `""` | ARN of the documents S3 bucket for least-privilege scoping |
| `ses_sender_email` | string | `"noreply@societysphere.com"` | Verified SES email address |

## Outputs
* `kms_key_arn`: ARN of the CMK.
* `kms_key_alias`: Alias of the CMK.
* `ecs_execution_role_arn`: ARN of the execution role.
* `ecs_task_role_arn`: ARN of the task runtime role.
* `db_secret_arn`: ARN of database secret container.
* `app_secret_arn`: ARN of application secret container.
